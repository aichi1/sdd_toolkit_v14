"""
tests/test_build_node.py — Phase 2 unit tests for the build node injectable seam.

Tests verify that build() correctly uses _invoke_builder as an injectable seam:
  FR-3.1 (AC T2.1): Builder runs with cwd=worktree_path, never the host working tree.
  第2条  (AC T2.2): build_artifact_ref is a path string, not body content.
  Mockable seam:    _invoke_builder is monkeypatched — no real API calls in any test.

Strategy:
  - Set SDD_RUN_REAL_BUILDER=1 per-test to exercise the real-SDK code path in build().
  - Monkeypatch graph.nodes._invoke_builder with an async spy to avoid API calls.
  - Use real git worktrees (tmp_git_repo fixture from conftest.py) so FR-3.1 cwd
    assertions are meaningful (not a plain temp dir).

No real API call is made in any test in this file.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

import graph.nodes as nodes_module
from graph.nodes import build
from harness.sandbox import carve_worktree, cleanup_worktree


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_state(**overrides) -> dict[str, Any]:
    """Minimal valid TaskState dict for build node tests."""
    state: dict[str, Any] = {
        "task_id": "p2-build-task",
        "spec_path": "/tmp/spec.md",
        "constitution_digest": "sha256:aabbccdd",
        "context_slice_ids": [],
        "worktree_path": "",
        "build_artifact_ref": "",
        "verify_findings": [],
        "eval_score": None,
        "attempt": 0,
        "decision": None,
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# Fixture: real git worktree (carved from tmp_git_repo)
# ---------------------------------------------------------------------------

@pytest.fixture
def worktree(tmp_git_repo: str):
    """
    Carve a real git worktree from tmp_git_repo for FR-3.1 isolation tests.

    Yields (worktree_path: str, base_repo: str).
    Cleans up the worktree after the test completes.

    Using a real worktree (not a plain temp dir) ensures that:
      1. worktree_path != os.getcwd() (different from host process CWD)
      2. worktree_path != base_repo   (sibling of repo, not inside it)
    """
    task_id = "p2-build-task"
    wt_path = carve_worktree(task_id, base_repo=tmp_git_repo)
    yield wt_path, tmp_git_repo
    cleanup_worktree(task_id, base_repo=tmp_git_repo)


# ---------------------------------------------------------------------------
# Tests: real SDK path (SDD_RUN_REAL_BUILDER=1, _invoke_builder monkeypatched)
# ---------------------------------------------------------------------------

class TestBuildNodeRealSDKPath:
    """
    Tests for build()'s real-SDK code path.
    SDD_RUN_REAL_BUILDER=1 activates the sdk branch; _invoke_builder is monkeypatched
    so no actual API call is made.
    """

    def test_invoke_builder_receives_worktree_as_cwd(self, worktree, monkeypatch):
        """
        FR-3.1 / AC T2.1: _invoke_builder must be called with cwd=worktree_path.

        The worktree is a real git worktree (sibling of base_repo), ensuring
        this test is meaningful — not just checking cwd equals some temp dir.
        """
        wt_path, _ = worktree
        invoked: list[dict] = []

        async def spy(prompt: str, options, cwd: str) -> str:
            invoked.append({"cwd": cwd})
            artifact = Path(cwd) / "artifact.txt"
            artifact.write_text("mock artifact")
            return str(artifact)

        monkeypatch.setenv("SDD_RUN_REAL_BUILDER", "1")
        monkeypatch.setattr(nodes_module, "_invoke_builder", spy)

        build(_base_state(task_id="p2-build-task", worktree_path=wt_path))

        assert len(invoked) == 1, (
            f"_invoke_builder must be called exactly once; called {len(invoked)} times"
        )
        assert invoked[0]["cwd"] == wt_path, (
            f"FR-3.1: _invoke_builder cwd must be worktree_path={wt_path!r}, "
            f"got {invoked[0]['cwd']!r}"
        )

    def test_cwd_is_not_host_working_directory(self, worktree, monkeypatch):
        """
        FR-3.1: cwd passed to _invoke_builder must NOT be the host process CWD.

        The host CWD is the project root (building_sdd_v14_by_v12), which is the
        main working tree. Build must run isolated in the worktree.
        """
        wt_path, _ = worktree
        invoked_cwd: list[str] = []

        async def spy(prompt: str, options, cwd: str) -> str:
            invoked_cwd.append(cwd)
            artifact = Path(cwd) / "artifact.txt"
            artifact.write_text("mock")
            return str(artifact)

        monkeypatch.setenv("SDD_RUN_REAL_BUILDER", "1")
        monkeypatch.setattr(nodes_module, "_invoke_builder", spy)

        build(_base_state(worktree_path=wt_path))

        host_cwd = os.getcwd()
        assert invoked_cwd[0] != host_cwd, (
            f"FR-3.1: _invoke_builder cwd must not be host CWD {host_cwd!r}"
        )

    def test_build_artifact_ref_is_path_not_body(self, worktree, monkeypatch):
        """
        第2条 / AC T2.2: build_artifact_ref in the returned dict must be a path,
        not body content (code, text, diff, etc.).

        第2条: TaskState holds path/ID references only. The artifact body lives on disk.
        """
        wt_path, _ = worktree

        async def mock_invoke(prompt: str, options, cwd: str) -> str:
            artifact = Path(cwd) / "artifact.txt"
            artifact.write_text(
                "generated code body content that must NOT appear in state"
            )
            return str(artifact)

        monkeypatch.setenv("SDD_RUN_REAL_BUILDER", "1")
        monkeypatch.setattr(nodes_module, "_invoke_builder", mock_invoke)

        result = build(_base_state(worktree_path=wt_path))
        ref = result["build_artifact_ref"]

        assert isinstance(ref, str), "build_artifact_ref must be a str"
        assert Path(ref).is_absolute(), (
            f"第2条: build_artifact_ref must be an absolute path; got {ref!r}"
        )
        assert "generated code body content" not in ref, (
            "第2条: build_artifact_ref must be a path reference, "
            "not the artifact body content"
        )

    def test_build_artifact_ref_points_inside_worktree(self, worktree, monkeypatch):
        """
        AC T2.2 / FR-3.1: build_artifact_ref must point to a file inside the worktree.
        """
        wt_path, _ = worktree

        async def mock_invoke(prompt: str, options, cwd: str) -> str:
            artifact = Path(cwd) / "artifact.txt"
            artifact.write_text("mock")
            return str(artifact)

        monkeypatch.setenv("SDD_RUN_REAL_BUILDER", "1")
        monkeypatch.setattr(nodes_module, "_invoke_builder", mock_invoke)

        result = build(_base_state(worktree_path=wt_path))
        ref = result["build_artifact_ref"]

        assert ref.startswith(wt_path), (
            f"AC T2.2: artifact_ref {ref!r} must be inside worktree {wt_path!r}"
        )

    def test_no_new_files_written_to_base_repo(self, worktree, monkeypatch):
        """
        FR-3.1: build() must not write any files into the base (host) repo.

        The mock writes only inside cwd (the worktree). We assert the base repo
        file set is unchanged after the build call.
        """
        wt_path, base_repo = worktree
        before = set(Path(base_repo).rglob("*"))

        async def mock_invoke(prompt: str, options, cwd: str) -> str:
            # Write ONLY inside the worktree (cwd), never in base_repo
            artifact = Path(cwd) / "artifact.txt"
            artifact.write_text("mock artifact — worktree only")
            return str(artifact)

        monkeypatch.setenv("SDD_RUN_REAL_BUILDER", "1")
        monkeypatch.setattr(nodes_module, "_invoke_builder", mock_invoke)

        build(_base_state(worktree_path=wt_path))

        after = set(Path(base_repo).rglob("*"))
        new_in_base = after - before
        assert not new_in_base, (
            f"FR-3.1: build() must not write to base (host) repo. "
            f"Unexpected new files: {new_in_base}"
        )

    def test_options_have_cwd_set_to_worktree(self, worktree, monkeypatch):
        """
        FR-3.1: ClaudeAgentOptions passed to _invoke_builder must have cwd=worktree_path.
        """
        wt_path, _ = worktree
        captured_options: list = []

        async def spy(prompt: str, options, cwd: str) -> str:
            captured_options.append(options)
            artifact = Path(cwd) / "artifact.txt"
            artifact.write_text("mock")
            return str(artifact)

        monkeypatch.setenv("SDD_RUN_REAL_BUILDER", "1")
        monkeypatch.setattr(nodes_module, "_invoke_builder", spy)

        build(_base_state(worktree_path=wt_path))

        from claude_agent_sdk import ClaudeAgentOptions
        assert len(captured_options) == 1
        opts = captured_options[0]
        assert isinstance(opts, ClaudeAgentOptions), (
            f"options must be ClaudeAgentOptions, got {type(opts)}"
        )
        assert str(opts.cwd) == wt_path, (
            f"FR-3.1: ClaudeAgentOptions.cwd must be {wt_path!r}, got {opts.cwd!r}"
        )


# ---------------------------------------------------------------------------
# Tests: seam is injectable (not called in stub mode)
# ---------------------------------------------------------------------------

class TestBuildNodeStubMode:
    """
    Tests confirming that _invoke_builder is the seam:
    in stub mode (no SDD_RUN_REAL_BUILDER), the stub behavior runs.
    Stub mode is backward-compatible with Phase 1 tests (no API required).
    """

    def test_stub_mode_does_not_call_spy_when_patched(
        self, tmp_path, monkeypatch
    ):
        """
        In stub mode (default, no SDD_RUN_REAL_BUILDER), _invoke_builder's
        internal stub branch runs. If SDD_RUN_REAL_BUILDER is absent, even a
        monkeypatched spy would run its OWN stub branch — but we verify the
        original _invoke_builder itself takes the stub path by NOT setting the env var
        and observing that the seam runs without API errors.

        This confirms the seam design: the real SDK path is gated by SDD_RUN_REAL_BUILDER.
        """
        # Create a minimal git repo that _invoke_builder (stub mode) can commit into
        import subprocess
        repo = tmp_path / "stub-repo"
        repo.mkdir()
        env = {
            **__import__("os").environ,
            "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "t@t",
        }
        subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "t@t"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "T"],
            check=True, capture_output=True,
        )
        # Initial commit (required for committing artifact.txt)
        (repo / ".gitkeep").write_text("")
        subprocess.run(
            ["git", "-C", str(repo), "add", "."], check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "init"],
            check=True, capture_output=True, env=env,
        )

        # No SDD_RUN_REAL_BUILDER → stub mode
        monkeypatch.delenv("SDD_RUN_REAL_BUILDER", raising=False)

        result = build(
            _base_state(
                task_id="stub-test",
                worktree_path=str(repo),
                attempt=1,
            )
        )

        # Stub mode produces artifact.txt in the repo
        artifact = repo / "artifact.txt"
        assert artifact.exists(), "stub mode must write artifact.txt"
        assert "STUB artifact for stub-test" in artifact.read_text()
        assert "attempt 1" in artifact.read_text()
        assert "build_artifact_ref" in result
        assert result["build_artifact_ref"] == str(artifact)
