"""
tests/conftest.py — Shared pytest fixtures.

All git-repo fixtures use throwaway directories; the real project repo is
never touched by any test (SDD_BASE_REPO / SDD_CONSTITUTION_PATH are
overridden per-test via monkeypatch or the integration_env fixture).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Shared: minimal throwaway git repo (used by sandbox + nodes + integration)
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_git_repo(tmp_path: Path) -> str:
    """
    Create a throwaway git repo with one commit in a subdirectory of tmp_path.
    Returns the absolute path string of the repo root.

    The test runner's global git config is used; if absent, env-var fallbacks
    are set in the sandbox/nodes helpers.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@sdd.localhost"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "SDD Test"],
        check=True, capture_output=True,
    )

    # Initial commit so worktree add works
    (repo / "README.md").write_text("# test repo\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "initial"],
        check=True, capture_output=True,
    )

    return str(repo)
