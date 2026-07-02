"""
tests/test_integration.py — Integration tests for the full Phase-1 graph.

AC(T1.2) / FR-5.1 / NFR-2: resume across fresh graph instances on the same DB.
AC(T1.3) / FR-5.3 / 第3条: reject must not touch base repo; approve merges.
T4.2a:  worktrees are real git worktrees, cleaned up after approve.

IMPORTANT: all tests set SDD_BASE_REPO / SDD_CONSTITUTION_PATH to temporary
paths so the REAL project main branch is never touched.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import pytest

from graph.build_graph import build_graph
from langgraph.types import Command


# ---------------------------------------------------------------------------
# Fixture: full integration environment
# ---------------------------------------------------------------------------

@pytest.fixture
def integration_env(tmp_path: Path):
    """
    Isolated environment for integration tests:
      - base_repo: throwaway git repo (used as SDD_BASE_REPO)
      - spec_file / constitution_file: real temp files
      - db_path: temp SQLite path (never :memory:)
    """
    # Base repo
    base = tmp_path / "base_repo"
    base.mkdir()
    env_git = {**os.environ,
               "GIT_AUTHOR_NAME": "integration-test",
               "GIT_AUTHOR_EMAIL": "test@sdd.localhost",
               "GIT_COMMITTER_NAME": "integration-test",
               "GIT_COMMITTER_EMAIL": "test@sdd.localhost"}

    subprocess.run(["git", "init", str(base)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(base), "config", "user.email", "test@sdd.localhost"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(base), "config", "user.name", "SDD Integration Test"],
        check=True, capture_output=True,
    )
    (base / "README.md").write_text("# base\n")
    subprocess.run(["git", "-C", str(base), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(base), "commit", "-m", "initial"],
        check=True, capture_output=True, env=env_git,
    )

    # Spec + constitution
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# Integration Test Spec\n")
    constitution_file = tmp_path / "constitution.md"
    constitution_file.write_text("# Test Constitution\n## Article 1\nDo good.\n")

    return {
        "base_repo": str(base),
        "spec_file": str(spec_file),
        "constitution_file": str(constitution_file),
        "db_path": str(tmp_path / "state.db"),
        "tmp_path": tmp_path,
        "env_git": env_git,
    }


def _initial_state(env: dict, task_id: str = "integ-task-1") -> dict[str, Any]:
    return {
        "task_id": task_id,
        "spec_path": env["spec_file"],
        "constitution_digest": "",
        "context_slice_ids": [],
        "worktree_path": "",
        "build_artifact_ref": "",
        "verify_findings": [],
        "eval_score": None,
        "attempt": 0,
        "decision": None,
    }


def _commit_count(repo: str) -> int:
    r = subprocess.run(
        ["git", "-C", repo, "log", "--oneline"],
        capture_output=True, text=True, check=True,
    )
    return len([l for l in r.stdout.splitlines() if l.strip()])


def _worktree_paths(repo: str) -> list[str]:
    r = subprocess.run(
        ["git", "-C", repo, "worktree", "list", "--porcelain"],
        capture_output=True, text=True, check=True,
    )
    return [
        line[len("worktree "):].strip()
        for line in r.stdout.splitlines()
        if line.startswith("worktree ")
    ]


# ---------------------------------------------------------------------------
# Test 1: resume across fresh instances (FR-5.1 / NFR-2)
# ---------------------------------------------------------------------------

class TestResumeAcrossInstances:
    def test_resume_from_second_connection(self, integration_env, monkeypatch):
        """
        AC(T1.2) / FR-5.1 / NFR-2:
        Close conn1 after interrupt, open conn2 on same DB, approve succeeds,
        and final state has decision=="approved".
        """
        env = integration_env
        monkeypatch.setenv("SDD_BASE_REPO", env["base_repo"])
        monkeypatch.setenv("SDD_CONSTITUTION_PATH", env["constitution_file"])

        config = {"configurable": {"thread_id": "resume-test-1"}}
        initial = _initial_state(env, task_id="resume-test-1")

        # --- Instance 1: run until interrupt ---
        conn1 = sqlite3.connect(env["db_path"], check_same_thread=False)
        g1 = build_graph(conn=conn1)
        g1.invoke(initial, config)  # pauses at review interrupt
        conn1.close()

        # --- Instance 2: fresh connection, same DB file ---
        conn2 = sqlite3.connect(env["db_path"], check_same_thread=False)
        g2 = build_graph(conn=conn2)
        final = g2.invoke(Command(resume={"action": "approve"}), config)
        conn2.close()

        assert final["decision"] == "approved", (
            f"Expected decision='approved' after resume+approve; got {final.get('decision')!r}"
        )


# ---------------------------------------------------------------------------
# Test 2: reject does not merge into base (FR-5.3 / 第3条)
# ---------------------------------------------------------------------------

class TestRejectLeavesBaseUnchanged:
    def test_reject_no_merge_into_base(self, integration_env, monkeypatch):
        """
        AC(T1.3) / FR-5.3 / 第3条:
        After a reject, the base repo must not gain new merge commits.
        Worktree commits stay on wt/* branch; base main is unchanged.
        """
        env = integration_env
        monkeypatch.setenv("SDD_BASE_REPO", env["base_repo"])
        monkeypatch.setenv("SDD_CONSTITUTION_PATH", env["constitution_file"])

        config = {"configurable": {"thread_id": "reject-test-1"}}
        initial = _initial_state(env, task_id="reject-test-1")

        commits_before = _commit_count(env["base_repo"])

        conn = sqlite3.connect(env["db_path"], check_same_thread=False)
        g = build_graph(conn=conn)

        # First run → interrupt at review
        g.invoke(initial, config)

        # Reject → back to build → interrupt at review again
        g.invoke(Command(resume={"action": "reject"}), config)

        commits_after_reject = _commit_count(env["base_repo"])
        assert commits_after_reject == commits_before, (
            f"Base repo gained commits after reject "
            f"({commits_before} → {commits_after_reject}); merge must NOT happen on reject"
        )

        # Clean up: approve to end the graph and merge worktree
        g.invoke(Command(resume={"action": "approve"}), config)
        conn.close()


# ---------------------------------------------------------------------------
# Test 3: full end-to-end — worktree real and cleaned up after approve
# ---------------------------------------------------------------------------

class TestFullE2E:
    def test_full_e2e_approve_cleans_worktree(self, integration_env, monkeypatch):
        """
        T4.2a / D2: complete spec_load→build→review(approve)→merge cycle.
          - worktree is a real git worktree during execution
          - after approve: worktree directory removed, artifact in base repo
        """
        env = integration_env
        monkeypatch.setenv("SDD_BASE_REPO", env["base_repo"])
        monkeypatch.setenv("SDD_CONSTITUTION_PATH", env["constitution_file"])

        config = {"configurable": {"thread_id": "e2e-test-1"}}
        initial = _initial_state(env, task_id="e2e-test-1")

        conn = sqlite3.connect(env["db_path"], check_same_thread=False)
        g = build_graph(conn=conn)

        # Phase 1: run to interrupt; verify worktree exists
        mid = g.invoke(initial, config)
        wt_path = mid["worktree_path"]

        assert Path(wt_path).exists(), "worktree must exist at interrupt point"
        assert wt_path in _worktree_paths(env["base_repo"]), (
            "worktree must be registered with git at interrupt point (T4.2a)"
        )

        # Phase 2: approve → merge → cleanup
        final = g.invoke(Command(resume={"action": "approve"}), config)
        conn.close()

        assert final["decision"] == "approved"

        # Worktree should be cleaned up
        assert not Path(wt_path).exists(), (
            "worktree directory must be removed after approve+merge"
        )

        # Artifact should be in base repo
        artifact_in_base = Path(env["base_repo"]) / "artifact.txt"
        assert artifact_in_base.exists(), (
            "artifact.txt must appear in base repo after merge"
        )
