"""
tests/test_sandbox.py — Unit tests for harness/sandbox.py (git worktree ops).

T4.2a: worktree_path must be a real git worktree visible in `git worktree list`.
All tests use the tmp_git_repo fixture (throwaway repo) — never the project repo.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from harness.sandbox import carve_worktree, cleanup_worktree, merge_worktree


def _worktree_paths(repo: str) -> list[str]:
    """Return absolute paths of all worktrees registered for repo."""
    r = subprocess.run(
        ["git", "-C", repo, "worktree", "list", "--porcelain"],
        capture_output=True, text=True, check=True,
    )
    return [
        line[len("worktree "):].strip()
        for line in r.stdout.splitlines()
        if line.startswith("worktree ")
    ]


def _worktree_count(repo: str) -> int:
    return len(_worktree_paths(repo))


def _branch_list(repo: str) -> list[str]:
    r = subprocess.run(
        ["git", "-C", repo, "branch", "--list"],
        capture_output=True, text=True, check=True,
    )
    return [b.strip().lstrip("* ") for b in r.stdout.splitlines() if b.strip()]


class TestCarveWorktree:
    def test_creates_real_worktree(self, tmp_git_repo: str, tmp_path: Path):
        """
        T4.2a: carve_worktree must produce a path that appears in
        `git worktree list --porcelain`.
        """
        wt_path = carve_worktree("my-feature", base_repo=tmp_git_repo)

        assert Path(wt_path).exists(), "worktree directory must exist on disk"
        assert wt_path in _worktree_paths(tmp_git_repo), (
            "worktree path must appear in `git worktree list`"
        )

    def test_carve_idempotent_returns_same_path(self, tmp_git_repo: str):
        """Second carve with same task_id returns the identical path."""
        path1 = carve_worktree("idempotent-task", base_repo=tmp_git_repo)
        path2 = carve_worktree("idempotent-task", base_repo=tmp_git_repo)
        assert path1 == path2

    def test_carve_idempotent_count_unchanged(self, tmp_git_repo: str):
        """Second carve with same task_id does NOT register a new worktree."""
        carve_worktree("count-test", base_repo=tmp_git_repo)
        count_before = _worktree_count(tmp_git_repo)

        carve_worktree("count-test", base_repo=tmp_git_repo)
        count_after = _worktree_count(tmp_git_repo)

        assert count_before == count_after, (
            f"Worktree count changed on second carve: {count_before} → {count_after}"
        )


class TestMergeWorktree:
    def _commit_in_worktree(self, wt_path: str, filename: str, content: str) -> None:
        """Helper: write + commit a file inside the worktree."""
        f = Path(wt_path) / filename
        f.write_text(content)
        env = {
            "GIT_AUTHOR_NAME": "test",
            "GIT_AUTHOR_EMAIL": "t@t.com",
            "GIT_COMMITTER_NAME": "test",
            "GIT_COMMITTER_EMAIL": "t@t.com",
        }
        import os
        full_env = {**os.environ, **env}
        subprocess.run(
            ["git", "-C", wt_path, "add", filename],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", wt_path, "commit", "-m", f"add {filename}"],
            check=True, capture_output=True, env=full_env,
        )

    def test_merge_cleans_up_worktree_directory(self, tmp_git_repo: str):
        """After merge, the worktree directory must be removed from disk."""
        wt_path = carve_worktree("cleanup-test", base_repo=tmp_git_repo)
        self._commit_in_worktree(wt_path, "file.txt", "hello")

        merge_worktree(wt_path, base_repo=tmp_git_repo)

        assert not Path(wt_path).exists(), "worktree dir should be gone after merge"

    def test_merge_removes_branch(self, tmp_git_repo: str):
        """After merge, the wt/{slug} branch must be deleted."""
        wt_path = carve_worktree("branch-cleanup", base_repo=tmp_git_repo)
        self._commit_in_worktree(wt_path, "x.txt", "x")

        merge_worktree(wt_path, base_repo=tmp_git_repo)

        branches = _branch_list(tmp_git_repo)
        assert "wt/branch-cleanup" not in branches, (
            "wt/branch-cleanup branch should be deleted after merge"
        )

    def test_artifact_integrated_into_base_after_merge(self, tmp_git_repo: str):
        """
        After merge, the artifact committed in the worktree must appear
        in the base repo's working tree.
        """
        wt_path = carve_worktree("integrate-test", base_repo=tmp_git_repo)
        self._commit_in_worktree(wt_path, "artifact.txt", "STUB artifact content")

        merge_worktree(wt_path, base_repo=tmp_git_repo)

        integrated = Path(tmp_git_repo) / "artifact.txt"
        assert integrated.exists(), "artifact.txt must appear in base repo after merge"
        assert integrated.read_text() == "STUB artifact content"
