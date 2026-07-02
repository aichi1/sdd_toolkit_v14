"""
harness/sandbox.py — Execution isolation for sdd_toolkit_v14 (Phase 1 + Phase 4).

Phase 1 (T4.2a): git worktree management.
  carve_worktree / merge_worktree / cleanup_worktree for the build→review cycle.

Phase 4 (T4.2b): podman rootless execution isolation.
  run_in_sandbox  — execute a command inside a podman container (hard boundary).
  build_podman_command — pure function returning the podman arg list (testable).
  podman_available    — shutil.which guard; run_in_sandbox raises if absent.
  SandboxUnavailableError — raised when podman is not installed (no host fallback).

第3条: merge_worktree is the ONLY irreversible operation; it must be called
       exclusively from the approve branch of review() — never before interrupt().
第4条: all build activity stays inside the worktree (physical isolation from main).
       Code EXECUTION goes through podman rootless (T4.2b) — no host-direct path.
第5条: podman provides the hard boundary (cgroups MemoryMax + egress by default
       blocked); hooks.py PreToolUse guard provides the soft boundary.
NFR-3: run_in_sandbox NEVER falls back to host execution when podman is absent.
       It raises SandboxUnavailableError instead.

Environment note (WSL2 / this build machine, updated 2026-07-02):
  podman IS installed and localhost/sdd-runner:latest is built — real container
  execution, egress blocking (--network=none) and read-only mounts are PROVEN
  by tests (test_sandbox_exec.py real-podman tests + test_e2e.py E2E-4).
  cgroups v2 unified remains UNAVAILABLE on this host (corporate WSL cannot be
  updated), so rootless --memory real enforcement is unverifiable here; the
  command construction is fully tested. See outputs/phase-08/e2e-report.md §4.2.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _slug(task_id: str) -> str:
    """Return a filesystem/branch-safe slug (<=40 chars, lowercase, hyphens)."""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", task_id).strip("-").lower()
    return (s or "task")[:40]


def _worktree_path(task_id: str, base_repo: str) -> Path:
    """
    Sibling directory: {base_repo}/../worktrees/{slug}
    Never placed inside the repo to avoid polluting git's working tree.
    """
    base = Path(base_repo).resolve()
    return (base.parent / "worktrees" / _slug(task_id)).resolve()


def _branch_name(task_id: str) -> str:
    return f"wt/{_slug(task_id)}"


def _git_env() -> dict[str, str]:
    """Minimal git identity env vars for test/CI contexts with no global git config."""
    env = os.environ.copy()
    if "GIT_AUTHOR_NAME" not in env:
        env["GIT_AUTHOR_NAME"] = "sdd-bot"
        env["GIT_AUTHOR_EMAIL"] = "sdd@localhost"
        env["GIT_COMMITTER_NAME"] = "sdd-bot"
        env["GIT_COMMITTER_EMAIL"] = "sdd@localhost"
    return env


def _ensure_initial_commit(base_repo: str) -> None:
    """
    If base_repo has no commits yet (e.g. a freshly initialised test repo),
    create one empty commit so that `git worktree add` can proceed.
    """
    result = subprocess.run(
        ["git", "-C", base_repo, "log", "--oneline", "-1"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 or not result.stdout.strip():
        subprocess.run(
            [
                "git", "-C", base_repo,
                "commit", "--allow-empty",
                "-m", "chore: initial commit (sdd-init)",
            ],
            check=True,
            capture_output=True,
            env=_git_env(),
        )


def _list_worktree_paths(base_repo: str) -> list[str]:
    """Return the absolute paths of all registered worktrees for base_repo."""
    result = subprocess.run(
        ["git", "-C", base_repo, "worktree", "list", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [
        line[len("worktree "):].strip()
        for line in result.stdout.splitlines()
        if line.startswith("worktree ")
    ]


def _branch_exists(base_repo: str, branch: str) -> bool:
    result = subprocess.run(
        ["git", "-C", base_repo, "branch", "--list", branch],
        capture_output=True,
        text=True,
    )
    return bool(result.stdout.strip())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def carve_worktree(task_id: str, base_repo: str = ".") -> str:
    """
    Create (or return existing) git worktree for task_id.

    Branch:  wt/{slug(task_id)}
    Path:    {base_repo}/../worktrees/{slug}   (sibling of repo, never inside)

    Idempotent: if the worktree path is already registered with git,
    return the existing path without re-adding.

    Returns resolved absolute path as str.
    """
    base_repo = str(Path(base_repo).resolve())
    target = _worktree_path(task_id, base_repo)
    branch = _branch_name(task_id)

    # --- Idempotency: check existing worktrees ---
    existing = _list_worktree_paths(base_repo)
    if str(target) in existing:
        return str(target)

    # --- Ensure base repo has at least one commit ---
    _ensure_initial_commit(base_repo)

    # --- Create parent directory ---
    target.parent.mkdir(parents=True, exist_ok=True)

    # --- Add worktree (create branch if needed) ---
    if _branch_exists(base_repo, branch):
        # Branch already exists (e.g. stale); re-attach worktree without -b
        subprocess.run(
            ["git", "-C", base_repo, "worktree", "add", str(target), branch],
            check=True,
            capture_output=True,
        )
    else:
        subprocess.run(
            [
                "git", "-C", base_repo,
                "worktree", "add", "-b", branch, str(target),
            ],
            check=True,
            capture_output=True,
        )

    return str(target)


def merge_worktree(worktree_path: str, base_repo: str = ".") -> None:
    """
    Merge wt/{slug} into base_repo's current branch, then clean up.

    Steps (irreversible — 第3条: call ONLY from review()'s approve branch):
      1. git merge --no-ff wt/{slug}   into base_repo
      2. git worktree remove --force   {worktree_path}
      3. git branch -d                 wt/{slug}
    """
    base_repo = str(Path(base_repo).resolve())
    slug = Path(worktree_path).name
    branch = f"wt/{slug}"

    env = _git_env()

    # 1. Merge
    subprocess.run(
        [
            "git", "-C", base_repo,
            "merge", "--no-ff", branch,
            "-m", f"merge: {branch}",
        ],
        check=True,
        capture_output=True,
        env=env,
    )

    # 2. Remove worktree (must be called with -C base_repo for git to find the registry)
    subprocess.run(
        ["git", "-C", base_repo, "worktree", "remove", "--force", worktree_path],
        check=True,
        capture_output=True,
    )

    # 3. Delete branch
    subprocess.run(
        ["git", "-C", base_repo, "branch", "-d", branch],
        check=True,
        capture_output=True,
    )


def cleanup_worktree(task_id: str, base_repo: str = ".") -> None:
    """
    Best-effort teardown of a worktree and its branch (for test teardown).
    Does not raise if the worktree or branch no longer exists.
    """
    base_repo = str(Path(base_repo).resolve())
    target = _worktree_path(task_id, base_repo)
    branch = _branch_name(task_id)

    subprocess.run(
        ["git", "-C", base_repo, "worktree", "remove", "--force", str(target)],
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", base_repo, "worktree", "prune"],
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", base_repo, "branch", "-D", branch],
        capture_output=True,
    )


# ---------------------------------------------------------------------------
# Phase 4 (T4.2b): podman rootless execution isolation
# ---------------------------------------------------------------------------

#: Default container image for sandbox execution.
#: Must be pre-built and available on the host (not pulled from a registry
#: since egress is blocked by default — 第4条).
_CONTAINER_IMAGE: str = os.environ.get(
    "SDD_SANDBOX_IMAGE", "localhost/sdd-runner:latest"
)

#: Mount point inside the container where the worktree is exposed.
_CONTAINER_MOUNT: str = "/workspace"


class SandboxUnavailableError(RuntimeError):
    """
    Raised when run_in_sandbox is called but podman is not available.

    第4条 / NFR-3: There is NO fallback to host execution.
    Install podman or ensure it is on PATH before calling run_in_sandbox.

    On this build machine (WSL2 without cgroups v2 unified), podman is not
    installed.  Tests verify the interface via build_podman_command (pure
    function) without needing a running podman daemon.
    """


def podman_available() -> bool:
    """
    Return True if podman is on the system PATH.

    Uses shutil.which for a portable, side-effect-free check.
    This is the capability gate for run_in_sandbox.
    """
    return shutil.which("podman") is not None


def build_podman_command(
    cmd: list[str],
    worktree_path: str,
    *,
    memory_max: str = "512m",
    network: bool = False,
    read_only: bool = True,
    image: str = _CONTAINER_IMAGE,
) -> list[str]:
    """
    Pure function: build the podman argument list for sandboxed execution.

    Does NOT execute anything.  Tests can assert exact flags without running
    podman.  Use run_in_sandbox to actually execute.

    第4条 flags applied:
      --rm              : throw-away container (no state persists).
      --network=none    : egress blocked by default (network=False, NFR-3).
                          Pass network=True to allow (non-default; used only
                          for explicit test/fetch scenarios).
      --read-only       : root filesystem is read-only (read_only=True).
      -v {wt}:{mount}:ro: worktree mounted read-only inside container.
      --memory={max}    : cgroups MemoryMax — hard memory cap (第5条 ハード境界).

    Args:
        cmd:           Command + arguments to run inside the container.
        worktree_path: Host path of the git worktree to mount.
        memory_max:    cgroups memory limit string (e.g. "512m", "1g").
        network:       If False (default), append --network=none (egress blocked).
        read_only:     If True (default), append --read-only and mount as :ro.
        image:         Container image to use (default: SDD_SANDBOX_IMAGE env var
                       or "localhost/sdd-runner:latest").

    Returns:
        Fully-formed podman argument list ready for subprocess.run().

    Example::

        args = build_podman_command(["python", "test.py"], "/tmp/wt")
        # → ["podman", "run", "--rm", "--network=none", "--read-only",
        #    "-v", "/tmp/wt:/workspace:ro", "--memory=512m",
        #    "localhost/sdd-runner:latest", "python", "test.py"]
    """
    args: list[str] = ["podman", "run", "--rm"]

    # Egress control: block by default (NFR-3, 第4条)
    if not network:
        args.append("--network=none")

    # Read-only rootfs (第4条: container cannot modify host filesystem)
    if read_only:
        args.append("--read-only")

    # Mount worktree (read-only or read-write depending on read_only flag)
    mount_suffix = ":ro" if read_only else ""
    args.extend(["-v", f"{worktree_path}:{_CONTAINER_MOUNT}{mount_suffix}"])

    # cgroups MemoryMax (第5条 ハード境界)
    args.append(f"--memory={memory_max}")

    # Container image + command
    args.append(image)
    args.extend(cmd)

    return args


def run_in_sandbox(
    cmd: list[str],
    worktree_path: str,
    *,
    memory_max: str = "512m",
    network: bool = False,
    read_only: bool = True,
    image: str = _CONTAINER_IMAGE,
) -> "subprocess.CompletedProcess[str]":
    """
    Execute ``cmd`` inside a podman rootless container with the worktree mounted.

    第4条: ALL code execution goes through podman — there is NO host-direct path.
    第5条: podman provides the hard boundary complementing the PreToolUse soft
           boundary in harness/hooks.py.
    NFR-3: If podman is absent, raises SandboxUnavailableError.
           NEVER falls back to executing cmd on the host.

    Args:
        cmd:           Command to run (e.g. ["python", "-m", "pytest"]).
        worktree_path: Path to the git worktree to mount in the container.
        memory_max:    cgroups memory limit (第5条 ハード境界).
        network:       If False (default), network egress is blocked (NFR-3).
        read_only:     If True (default), rootfs + worktree mount are read-only.
        image:         Container image to run.

    Returns:
        subprocess.CompletedProcess with stdout, stderr, returncode.

    Raises:
        SandboxUnavailableError: if podman is not on PATH.
            No host fallback — callers must handle this exception.
    """
    if not podman_available():
        raise SandboxUnavailableError(
            "podman is not installed or not on PATH. "
            "Cannot execute code in the sandbox. "
            "Install podman to enable sandboxed execution. "
            "第4条 / NFR-3: no host-direct-execution fallback exists by design."
        )

    podman_cmd = build_podman_command(
        cmd,
        worktree_path,
        memory_max=memory_max,
        network=network,
        read_only=read_only,
        image=image,
    )

    return subprocess.run(podman_cmd, capture_output=True, text=True)
