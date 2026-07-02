"""
tests/test_sandbox_exec.py — Phase 4 (T4.2b) unit tests for podman sandbox.

NFR-3 / 第4条 / 第5条 verification:
  - build_podman_command() produces the correct flags WITHOUT running podman.
  - run_in_sandbox() raises SandboxUnavailableError when podman is absent.
  - No host-direct-execution fallback exists (NFR-3: hard boundary).
  - Real-podman tests are skipped when podman is not on PATH.

Strategy:
  build_podman_command() is a pure function → assert exact flag list without
  running any subprocess.  This is the primary test surface for T4.2b since
  podman is NOT installed on this build machine (WSL2).

  run_in_sandbox() tests monkeypatch podman_available() to False to verify
  SandboxUnavailableError is raised unconditionally — no host exec fallback.

  A @pytest.mark.skipif guard wraps any test that would need real podman.
"""
from __future__ import annotations

import pytest

from harness.sandbox import (
    SandboxUnavailableError,
    _CONTAINER_IMAGE,
    _CONTAINER_MOUNT,
    build_podman_command,
    podman_available,
    run_in_sandbox,
)


# ---------------------------------------------------------------------------
# Tests: build_podman_command() — pure function, no subprocess
# ---------------------------------------------------------------------------

class TestBuildPodmanCommand:
    """
    Verify the podman argument list produced by build_podman_command().

    These tests pass WITHOUT podman installed because build_podman_command()
    is a pure function that returns a list of strings.  Every flag required
    by the architecture documents is asserted here.
    """

    def test_starts_with_podman_run_rm(self):
        """Command must start with 'podman run --rm'."""
        args = build_podman_command(["python", "test.py"], "/tmp/wt")
        assert args[0] == "podman"
        assert args[1] == "run"
        assert "--rm" in args

    def test_network_none_by_default(self):
        """--network=none must appear by default (egress blocked, NFR-3, 第4条)."""
        args = build_podman_command(["python", "test.py"], "/tmp/wt")
        assert "--network=none" in args, (
            "NFR-3: egress must be blocked by default; --network=none missing"
        )

    def test_network_none_explicit_false(self):
        """network=False must produce --network=none."""
        args = build_podman_command(["ls"], "/wt", network=False)
        assert "--network=none" in args

    def test_network_none_absent_when_network_true(self):
        """network=True must NOT add --network=none (allows egress)."""
        args = build_podman_command(["ls"], "/wt", network=True)
        assert "--network=none" not in args, (
            "network=True should not add --network=none"
        )

    def test_read_only_flag_present_by_default(self):
        """--read-only must appear by default (第4条: rootfs is read-only)."""
        args = build_podman_command(["ls"], "/wt")
        assert "--read-only" in args, (
            "第4条: --read-only missing from podman command"
        )

    def test_read_only_absent_when_disabled(self):
        """read_only=False must not add --read-only."""
        args = build_podman_command(["ls"], "/wt", read_only=False)
        assert "--read-only" not in args

    def test_worktree_mounted_readonly_by_default(self):
        """
        The worktree must be mounted with :ro suffix by default.
        第4条: worktree is read-only inside the container to prevent
        container processes from modifying the host worktree.
        """
        worktree = "/home/user/worktrees/my-task"
        args = build_podman_command(["ls"], worktree)

        # Find the -v flag and its argument
        v_idx = args.index("-v")
        mount_spec = args[v_idx + 1]

        assert mount_spec.startswith(worktree), (
            f"Mount must start with worktree path {worktree!r}; got {mount_spec!r}"
        )
        assert ":ro" in mount_spec, (
            f"Worktree mount must include ':ro' suffix; got {mount_spec!r}"
        )
        assert _CONTAINER_MOUNT in mount_spec, (
            f"Mount must include container mount point {_CONTAINER_MOUNT!r}; got {mount_spec!r}"
        )

    def test_worktree_mounted_rw_when_read_only_false(self):
        """When read_only=False, the worktree mount must NOT have :ro."""
        args = build_podman_command(["ls"], "/wt", read_only=False)
        v_idx = args.index("-v")
        mount_spec = args[v_idx + 1]
        assert ":ro" not in mount_spec

    def test_memory_flag_present_with_default_512m(self):
        """--memory=512m must appear by default (第5条 ハード境界: cgroups MemoryMax)."""
        args = build_podman_command(["ls"], "/wt")
        assert "--memory=512m" in args, (
            "第5条: --memory=512m missing (cgroups MemoryMax)"
        )

    def test_memory_flag_custom_value(self):
        """Custom memory_max must appear in --memory flag."""
        args = build_podman_command(["ls"], "/wt", memory_max="1g")
        assert "--memory=1g" in args

    def test_image_in_command(self):
        """The container image must appear in the argument list."""
        args = build_podman_command(["ls"], "/wt")
        assert _CONTAINER_IMAGE in args

    def test_custom_image(self):
        """Custom image name must appear in the argument list."""
        args = build_podman_command(["ls"], "/wt", image="myrepo/myimage:1.0")
        assert "myrepo/myimage:1.0" in args

    def test_cmd_appended_after_image(self):
        """The user's cmd must appear AFTER the image name."""
        cmd = ["python", "-m", "pytest", "tests/"]
        args = build_podman_command(cmd, "/wt")
        image_idx = args.index(_CONTAINER_IMAGE)
        remaining = args[image_idx + 1:]
        assert remaining == cmd, (
            f"cmd not correctly appended after image; got {remaining!r}"
        )

    def test_full_command_all_required_flags(self):
        """
        Integration check: all required flags appear in a single call.

        Required by design:
          --rm            (disposable container)
          --network=none  (egress blocked, NFR-3)
          --read-only     (rootfs protection, 第4条)
          :ro             (worktree mount read-only, 第4条)
          --memory=...    (cgroups MemoryMax, 第5条)
        """
        worktree = "/tmp/worktrees/task-abc"
        args = build_podman_command(
            ["python", "run_tests.py"],
            worktree,
            memory_max="256m",
        )

        assert "--rm" in args, "Missing --rm"
        assert "--network=none" in args, "Missing --network=none (NFR-3)"
        assert "--read-only" in args, "Missing --read-only (第4条)"
        assert any(":ro" in a for a in args), "Missing :ro mount suffix (第4条)"
        assert "--memory=256m" in args, "Missing --memory flag (第5条)"

    def test_returns_list_of_strings(self):
        """build_podman_command must return a list[str]."""
        args = build_podman_command(["echo", "hello"], "/wt")
        assert isinstance(args, list)
        assert all(isinstance(a, str) for a in args), (
            "All elements must be str"
        )


# ---------------------------------------------------------------------------
# Tests: podman_available()
# ---------------------------------------------------------------------------

class TestPodmanAvailable:
    """podman_available() is a boolean shutil.which check."""

    def test_returns_bool(self):
        """podman_available() must return a bool."""
        result = podman_available()
        assert isinstance(result, bool)

    def test_false_when_monkeypatched_not_found(self, monkeypatch):
        """When shutil.which returns None, podman_available() must return False."""
        monkeypatch.setattr("harness.sandbox.shutil.which", lambda _: None)
        assert podman_available() is False

    def test_true_when_monkeypatched_found(self, monkeypatch):
        """When shutil.which returns a path, podman_available() must return True."""
        monkeypatch.setattr("harness.sandbox.shutil.which", lambda _: "/usr/bin/podman")
        assert podman_available() is True


# ---------------------------------------------------------------------------
# Tests: run_in_sandbox() — NFR-3 no-host-exec guarantee
# ---------------------------------------------------------------------------

class TestRunInSandboxNoHostExec:
    """
    Verify NFR-3: run_in_sandbox raises SandboxUnavailableError when podman
    is absent — NEVER executes cmd on the host.

    These tests monkeypatch podman_available() to False so they run
    regardless of whether podman is actually installed.
    """

    def test_raises_sandbox_unavailable_when_podman_absent(self, monkeypatch):
        """
        NFR-3 / 第4条: run_in_sandbox must raise SandboxUnavailableError when
        podman is not available.  It must NOT fall back to host execution.
        """
        monkeypatch.setattr("harness.sandbox.podman_available", lambda: False)

        with pytest.raises(SandboxUnavailableError) as exc_info:
            run_in_sandbox(["python", "--version"], "/tmp/wt")

        # Exception message must explain the situation
        assert "podman" in str(exc_info.value).lower(), (
            "SandboxUnavailableError message must mention 'podman'"
        )

    def test_raises_not_runs_on_host(self, monkeypatch):
        """
        NFR-3: confirm cmd is NOT executed on host when podman is absent.
        If run_in_sandbox fell back to host exec, the counter would increment.
        """
        host_exec_counter = {"count": 0}

        def fake_subprocess_run(cmd, **kwargs):
            host_exec_counter["count"] += 1
            raise AssertionError("run_in_sandbox must not call subprocess.run without podman")

        monkeypatch.setattr("harness.sandbox.podman_available", lambda: False)
        monkeypatch.setattr("harness.sandbox.subprocess.run", fake_subprocess_run)

        with pytest.raises(SandboxUnavailableError):
            run_in_sandbox(["ls", "/tmp"], "/tmp/wt")

        assert host_exec_counter["count"] == 0, (
            "NFR-3 violated: subprocess.run was called even though podman is absent"
        )

    def test_error_message_mentions_no_fallback(self, monkeypatch):
        """SandboxUnavailableError message must reference the no-fallback policy."""
        monkeypatch.setattr("harness.sandbox.podman_available", lambda: False)

        with pytest.raises(SandboxUnavailableError) as exc_info:
            run_in_sandbox(["python", "test.py"], "/tmp/wt")

        msg = str(exc_info.value)
        # Must communicate that no fallback exists
        assert any(
            kw in msg.lower()
            for kw in ("fallback", "no host", "by design", "install")
        ), f"Exception message should explain no-fallback policy; got: {msg!r}"

    def test_sandbox_unavailable_error_is_runtime_error(self):
        """SandboxUnavailableError must be a RuntimeError subclass."""
        assert issubclass(SandboxUnavailableError, RuntimeError)


# ---------------------------------------------------------------------------
# Tests: real podman (skipped when podman is absent)
# ---------------------------------------------------------------------------

def _image_available() -> bool:
    """localhost/sdd-runner:latest がローカルに存在するか（pull は試みない）。"""
    if not podman_available():
        return False
    import subprocess
    try:
        r = subprocess.run(
            ["podman", "image", "exists", _CONTAINER_IMAGE],
            capture_output=True, timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


@pytest.mark.skipif(
    not podman_available(),
    reason="podman not installed — real-execution test skipped (WSL2 / this host)",
)
@pytest.mark.skipif(
    podman_available() and not _image_available(),
    reason=(
        "container image localhost/sdd-runner:latest not built — build with: "
        "printf 'FROM docker.io/library/alpine:3.20\\nRUN apk add --no-cache curl\\n'"
        " | podman build -t localhost/sdd-runner:latest -"
    ),
)
class TestRunInSandboxRealPodman:
    """
    Tests that actually execute podman.  Only run when podman AND the
    localhost/sdd-runner:latest image are available.

    Note (2026-07-02): podman was installed on the build machine (WSL2;
    cgroups v2 unified is NOT available there, so --memory enforcement is
    unverifiable on that host — command construction is covered by the
    mocked tests above).
    """

    def test_successful_execution_returns_completed_process(self, tmp_path):
        """
        run_in_sandbox with a simple command returns CompletedProcess.
        Requires: localhost/sdd-runner:latest image to be available.
        """
        import subprocess
        result = run_in_sandbox(
            ["echo", "hello-from-sandbox"],
            str(tmp_path),
            image=_CONTAINER_IMAGE,
        )
        assert isinstance(result, subprocess.CompletedProcess)
        assert "hello-from-sandbox" in result.stdout

    def test_network_none_blocks_egress(self, tmp_path):
        """
        With network=False (default), egress must be blocked.
        Attempting to reach an external host must fail.
        """
        result = run_in_sandbox(
            ["curl", "--max-time", "2", "https://example.com"],
            str(tmp_path),
            network=False,
        )
        # 偽陽性ガード: 125=イメージ/podman エラー, 127=curl 不在。
        # これらは「egress 遮断」の証明にならないので明示的に失敗させる。
        assert result.returncode not in (125, 127), (
            f"container/image error (rc={result.returncode}), not an egress test: "
            f"{result.stderr[-300:]}"
        )
        # curl must fail (non-zero return) — egress blocked
        assert result.returncode != 0, (
            "Egress should be blocked with --network=none but curl succeeded"
        )
