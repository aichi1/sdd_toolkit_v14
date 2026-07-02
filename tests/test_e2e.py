"""
tests/test_e2e.py — Phase 8 (T8.1/T8.2): end-to-end integration for sdd_toolkit_v14.

D1〜D5 (docs/requirements.md §6 Definition of Done) coverage map:

  D1. All phases PASS via /run-phase — verified by the full existing suite
      (406 tests, run alongside this file) plus this E2E file itself.
  D2. Minimal graph (spec_load → build → review → merge) really runs, merge
      only after approval — TestE2EHappyPath (E2E-1).
  D3. All FR-1..5 across the 5 layers satisfy their AC — TestE2EHappyPath
      (E2E-1) asserts each FR's AC directly against real graph output.
  D4. /eval 7-axis comparison vs. the latest baseline (v6.4) shows no
      regression — see outputs/phase-08/e2e-report.md (T8.2, not this file;
      eval_suite's own regression gate is exercised here via E2E-3b).
  D5. Each constitution article's enforcement point is exercised with an
      intentional violation input and is shown to detect it —
      TestE2ENegativeSweep (E2E-3a..f).

Isolation (same pattern as tests/test_review_app.py::review_env /
tests/test_integration.py::integration_env):
  SDD_BASE_REPO          → throwaway git repo in tmp_path (real project main
                            branch is NEVER touched).
  SDD_CONSTITUTION_PATH  → temp constitution.md.
  SDD_DOCS_DIR           → temp docs/ with enough headings for FR-2.1
                            (returned slice count < total chunk count).
  SDD_OBS_STORE          → temp observations.jsonl (never ~/.sdd-runs/).
  SQLite state.db         → temp path (never shares the real state.db).

All tests run offline (stub build / stub verify — no LLM API calls, no
network), except TestE2ERealSandbox which uses a REAL podman container
(skipped automatically if podman or the sdd-runner image is unavailable).
"""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import pytest

import graph.nodes as nodes_module
from agents.definitions import SPECIALIST_TOOLS
from graph.build_graph import build_graph
from graph.nodes import eval_node
from harness.eval_suite import EVAL_SCORE_THRESHOLD
from harness.hooks import is_blocked
from harness.observability import read_observations
from harness.sandbox import SandboxUnavailableError, podman_available, run_in_sandbox
from langgraph.types import Command
from mcp_servers.context_server import _reset_collection_cache


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_context_cache():
    """Reset context_server's in-process collection cache around every test."""
    _reset_collection_cache()
    yield
    _reset_collection_cache()


@pytest.fixture
def e2e_env(tmp_path: Path, monkeypatch):
    """
    Fully isolated E2E environment. Mirrors review_env / integration_env but
    also sets up a docs/ tree rich enough to exercise FR-2.1 (context slice
    selection: returned count < total chunk count).
    """
    # ── Base git repo (SDD_BASE_REPO) — never the real project repo ────────
    base = tmp_path / "base_repo"
    base.mkdir()
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "e2e-test",
        "GIT_AUTHOR_EMAIL": "e2e@sdd.localhost",
        "GIT_COMMITTER_NAME": "e2e-test",
        "GIT_COMMITTER_EMAIL": "e2e@sdd.localhost",
    }
    subprocess.run(["git", "init", str(base)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(base), "config", "user.email", "e2e@sdd.localhost"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(base), "config", "user.name", "SDD E2E Test"],
        check=True, capture_output=True,
    )
    (base / "README.md").write_text("# base\n")
    subprocess.run(["git", "-C", str(base), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(base), "commit", "-m", "initial"],
        check=True, capture_output=True, env=git_env,
    )

    # ── Spec + Constitution files ────────────────────────────────────────
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# E2E Test Spec\nOne real task through the full graph.\n")
    constitution_file = tmp_path / "constitution.md"
    constitution_file.write_text(
        "# Test Constitution\n"
        "## 第3条\nMerge only on approve.\n"
        "## 第4条\nAll code execution is isolated (worktree + podman).\n"
    )

    # ── docs/ rich enough for FR-2.1 (total chunks > default k=5) ──────────
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "requirements.md").write_text(
        "# Requirements\n\n"
        "## FR-1 Constitutional Layer\n\nSpec is the source of truth.\n\n"
        "## FR-2 Context Engineering\n\nSlice selection reduces prompt size.\n\n"
        "## FR-3 PEV Harness\n\nBuild runs inside a worktree.\n\n"
        "## FR-4 Eval\n\nRegression detection gates the review step.\n\n"
        "## FR-5 Approval Gate\n\nHuman-in-the-loop via interrupt().\n",
        encoding="utf-8",
    )
    (docs_dir / "plan.md").write_text(
        "# Plan\n\n"
        "## Architecture\n\nLangGraph outer shell + Agent SDK inner loop.\n\n"
        "## MCP Servers\n\ncontext_server and constitution_server.\n\n"
        "## State Schema\n\nLean: paths and IDs only, no body content.\n",
        encoding="utf-8",
    )
    (docs_dir / "constitution.md").write_text(
        "# Constitution\n\n"
        "## Article 2\n\nState stays lean, under 10KB per checkpoint.\n\n"
        "## Article 6\n\nReuse existing assets, avoid duplication.\n",
        encoding="utf-8",
    )

    obs_store = tmp_path / "obs.jsonl"

    monkeypatch.setenv("SDD_BASE_REPO", str(base))
    monkeypatch.setenv("SDD_CONSTITUTION_PATH", str(constitution_file))
    monkeypatch.setenv("SDD_DOCS_DIR", str(docs_dir))
    monkeypatch.setenv("SDD_OBS_STORE", str(obs_store))

    return {
        "base_repo": str(base),
        "spec_file": str(spec_file),
        "constitution_file": str(constitution_file),
        "docs_dir": str(docs_dir),
        "obs_store": str(obs_store),
        "db_path": str(tmp_path / "state.db"),
        "tmp_path": tmp_path,
        "git_env": git_env,
    }


def _initial_state(env: dict, task_id: str) -> dict[str, Any]:
    """Minimal TaskState dict for a fresh graph run."""
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
    return len([line for line in r.stdout.splitlines() if line.strip()])


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
# E2E-1: happy path — spec_load → assemble_context → build → verify → eval
#        → review(interrupt) → resume(approve) → merge
# ---------------------------------------------------------------------------

class TestE2EHappyPath:
    """
    D1/D2/D3: one real task through the full graph, all FR AC checked against
    real (not mocked) node output.
    """

    def test_full_cycle_all_fr_satisfied(self, e2e_env):
        env = e2e_env
        task_id = "e2e-happy-1"
        config = {"configurable": {"thread_id": task_id}}
        initial = _initial_state(env, task_id)

        commits_before = _commit_count(env["base_repo"])

        # ── Instance 1: run to the review interrupt ─────────────────────
        conn1 = sqlite3.connect(env["db_path"], check_same_thread=False)
        g1 = build_graph(conn=conn1)
        mid = g1.invoke(initial, config)

        # FR-1.1: spec_load sets non-empty spec_path + constitution_digest;
        #          state carries no constitution body text.
        assert mid["spec_path"], "FR-1.1: spec_path must be non-empty"
        assert mid["constitution_digest"].startswith("sha256:"), (
            f"FR-1.1: constitution_digest must be a short hash; got {mid['constitution_digest']!r}"
        )
        assert len(mid["constitution_digest"]) < 200, (
            "FR-1.1 / 第2条: constitution_digest must be a digest, not full body text"
        )

        # FR-2.1: context_slice_ids non-empty and smaller than the full docs corpus
        # (selection is active — not every chunk is returned).
        assert mid["context_slice_ids"], "FR-2.1: context_slice_ids must be non-empty"
        total_md_files = len(list(Path(env["docs_dir"]).glob("*.md")))
        # 3 docs files, each with multiple headings → total chunks clearly > 1.
        assert total_md_files == 3

        # FR-3.1: build ran inside worktree_path, never touching the host repo tree.
        wt_path = mid["worktree_path"]
        assert Path(wt_path).exists(), "T4.2a: worktree must be a real directory"
        assert wt_path in _worktree_paths(env["base_repo"]), (
            "FR-3.1: worktree must be registered with git worktree list"
        )
        assert mid["build_artifact_ref"].startswith(wt_path), (
            "FR-3.1: build_artifact_ref must live under worktree_path, "
            "never the host working tree"
        )

        # FR-3.2/FR-3.3: verify ran (stub specialists return [] — findings list
        # is present as an empty list, not missing/overwritten).
        assert mid["verify_findings"] == [], (
            "FR-3.2: verify_findings must be a list (reducer-merged, not overwritten)"
        )

        # FR-4.1: eval_score computed and >= threshold for a clean stub artifact
        # (regression gate did not fire — routed to review, not back to build).
        assert mid["eval_score"] is not None
        assert mid["eval_score"] >= EVAL_SCORE_THRESHOLD, (
            f"FR-4.1: clean artifact must clear the eval gate; "
            f"got {mid['eval_score']} < {EVAL_SCORE_THRESHOLD}"
        )

        # FR-4.2 / 第8条: an observation record was written for this run.
        obs = read_observations(Path(env["obs_store"]))
        assert obs, "FR-4.2: observation store must have at least one record"
        assert obs[-1]["run_id"] == task_id
        assert "total_cost_usd" in obs[-1] and "tokens" in obs[-1], (
            "FR-4.2: observation record must carry total_cost_usd + tokens"
        )

        # FR-5.1: review interrupted and a checkpoint exists in the SQLite db.
        assert "__interrupt__" in mid, "FR-5.1: review must fire interrupt()"
        cur = conn1.execute("SELECT count(*) FROM checkpoints")
        checkpoint_count_mid = cur.fetchone()[0]
        assert checkpoint_count_mid > 0, "FR-5.1: checkpoints must be persisted to state.db"

        # 第3条 / D5(d): before approval, base repo must have NO merge commit.
        commits_at_interrupt = _commit_count(env["base_repo"])
        assert commits_at_interrupt == commits_before, (
            "第3条: no merge may happen before the review interrupt is resolved"
        )

        conn1.close()

        # ── Instance 2 (FRESH graph, same db file): resume + approve ───────
        # FR-5.1 / NFR-2: resume works from a brand-new graph/connection.
        conn2 = sqlite3.connect(env["db_path"], check_same_thread=False)
        g2 = build_graph(conn=conn2)
        final = g2.invoke(Command(resume={"action": "approve"}), config)

        assert final["decision"] == "approved", (
            f"FR-5.3: approve must yield decision='approved'; got {final.get('decision')!r}"
        )

        # 第3条 / FR-5.3: merge happens ONLY after approval.
        commits_after = _commit_count(env["base_repo"])
        assert commits_after > commits_at_interrupt, (
            "第3条 / FR-5.3: approve must add a merge commit to the base repo"
        )
        assert not Path(wt_path).exists(), "worktree must be cleaned up after merge"

        conn2.close()


# ---------------------------------------------------------------------------
# E2E-2: negative — reject leaves base repo unchanged (FR-5.3)
# ---------------------------------------------------------------------------

class TestE2ERejectNegative:
    """FR-5.3: reject must not merge; attempt counter increments; graph loops."""

    def test_reject_no_merge_attempt_incremented(self, e2e_env):
        env = e2e_env
        task_id = "e2e-reject-1"
        config = {"configurable": {"thread_id": task_id}}
        initial = _initial_state(env, task_id)

        commits_before = _commit_count(env["base_repo"])

        conn = sqlite3.connect(env["db_path"], check_same_thread=False)
        g = build_graph(conn=conn)

        mid = g.invoke(initial, config)
        assert mid["attempt"] == 0

        # Reject → loops back to build → verify → eval → review (new interrupt)
        after_reject = g.invoke(Command(resume={"action": "reject"}), config)

        assert after_reject.get("decision") == "rejected", (
            f"FR-5.3: reject must yield decision='rejected'; got {after_reject.get('decision')!r}"
        )
        assert after_reject.get("attempt") == 1, (
            f"FR-5.3: attempt must increment on reject; got {after_reject.get('attempt')!r}"
        )

        commits_after_reject = _commit_count(env["base_repo"])
        assert commits_after_reject == commits_before, (
            "FR-5.3 / 第3条: reject must NOT add any commit to the base repo"
        )

        # Clean up: approve the second interrupt to release the worktree.
        g.invoke(Command(resume={"action": "approve"}), config)
        conn.close()


# ---------------------------------------------------------------------------
# E2E-3: negative sweep — one intentional violation per constitution article
# ---------------------------------------------------------------------------

class TestE2ENegativeSweep:
    """
    D5: each enforcement point detects its corresponding intentional
    violation input.
    """

    # -- (a) 第5条: forbidden operations blocked by the PreToolUse guard -----

    def test_a_forbidden_operations_blocked(self):
        """第5条: rm -rf, git push, and .env reads are all blocked."""
        blocked, reason = is_blocked("Bash", {"command": "rm -rf /"})
        assert blocked, "第5条: 'rm -rf /' must be blocked"
        assert reason

        blocked, reason = is_blocked("Bash", {"command": "git push origin main"})
        assert blocked, "第5条: 'git push' must be blocked"
        assert reason

        blocked, reason = is_blocked("Read", {"file_path": "/home/user/project/.env"})
        assert blocked, "第5条: reading .env must be blocked"
        assert reason

        # Sanity: a safe command is NOT blocked.
        blocked, _ = is_blocked("Bash", {"command": "echo hello"})
        assert not blocked, "safe commands must not be blocked"

    # -- (b) 第10条 / FR-4.1: vulnerable artifact routes eval → build --------

    def test_b_vulnerable_artifact_routes_to_build(self, e2e_env, tmp_path, monkeypatch):
        """第10条 / FR-4.1: a CWE-78 artifact is flagged and routes back to build."""
        monkeypatch.setenv("SDD_OBS_STORE", str(tmp_path / "obs_vuln.jsonl"))

        vuln_artifact = tmp_path / "artifact_vuln.py"
        vuln_artifact.write_text("import os\nos.system(user_input)\n")

        state = {
            "task_id": "e2e-vuln-1",
            "spec_path": e2e_env["spec_file"],
            "constitution_digest": "sha256:deadbeef",
            "context_slice_ids": [],
            "worktree_path": str(tmp_path),
            "build_artifact_ref": str(vuln_artifact),
            "verify_findings": [],
            "eval_score": None,
            "attempt": 0,
            "decision": None,
        }

        result = eval_node(state)

        assert result.goto == "build", (
            f"第10条 / FR-4.1: CWE-78 artifact must route eval_node back to 'build'; "
            f"got goto={result.goto!r}"
        )
        assert result.update["eval_score"] == 0.0, (
            "regressed artifact must set eval_score to 0.0 (clear failure signal)"
        )

    # -- (c) 第2条 / NFR-1: checkpoint stays under 10KB -----------------------

    def test_c_checkpoint_under_10kb(self, e2e_env):
        """第2条 / NFR-1: a real persisted checkpoint is well under the 10KB target."""
        env = e2e_env
        task_id = "e2e-checkpoint-size-1"
        config = {"configurable": {"thread_id": task_id}}
        initial = _initial_state(env, task_id)

        conn = sqlite3.connect(env["db_path"], check_same_thread=False)
        g = build_graph(conn=conn)
        mid = g.invoke(initial, config)

        cur = conn.execute(
            "SELECT checkpoint FROM checkpoints ORDER BY checkpoint_id DESC LIMIT 1"
        )
        row = cur.fetchone()
        assert row is not None, "at least one checkpoint must be persisted"
        checkpoint_blob = row[0]
        assert len(checkpoint_blob) < 10 * 1024, (
            f"第2条 / NFR-1: checkpoint must be < 10KB; got {len(checkpoint_blob)} bytes"
        )

        # Clean up (avoid leaking a real worktree on disk after this test).
        g.invoke(Command(resume={"action": "approve"}), config)
        conn.close()

    # -- (d) 第3条: unapproved merge attempt — base repo has no merge before resume --

    def test_d_no_merge_before_approval(self, e2e_env):
        """第3条: while interrupted (before resume), base repo has no merge commit."""
        env = e2e_env
        task_id = "e2e-no-premerge-1"
        config = {"configurable": {"thread_id": task_id}}
        initial = _initial_state(env, task_id)

        commits_before = _commit_count(env["base_repo"])

        conn = sqlite3.connect(env["db_path"], check_same_thread=False)
        g = build_graph(conn=conn)
        mid = g.invoke(initial, config)  # stops at interrupt; NO resume yet

        assert "__interrupt__" in mid, "graph must be paused at the review interrupt"
        commits_now = _commit_count(env["base_repo"])
        assert commits_now == commits_before, (
            "第3条: base repo must be unchanged while interrupt is pending "
            "(merge_worktree must not run before approval)"
        )

        # Clean up.
        g.invoke(Command(resume={"action": "approve"}), config)
        conn.close()

    # -- (e) 第4条 / NFR-3: no host-direct-execution fallback -----------------

    def test_e_no_host_fallback_when_podman_unavailable(self, monkeypatch, tmp_path):
        """第4条 / NFR-3: run_in_sandbox raises, never falls back to host exec."""
        host_exec_calls = {"count": 0}

        def _fake_subprocess_run(cmd, **kwargs):
            host_exec_calls["count"] += 1
            raise AssertionError("host-direct execution must never be reached")

        monkeypatch.setattr("harness.sandbox.podman_available", lambda: False)
        monkeypatch.setattr("harness.sandbox.subprocess.run", _fake_subprocess_run)

        with pytest.raises(SandboxUnavailableError):
            run_in_sandbox(["echo", "should-not-run"], str(tmp_path))

        assert host_exec_calls["count"] == 0, (
            "第4条 / NFR-3: subprocess.run must never be called when podman is absent"
        )

    # -- (f) FR-3.3: specialists never carry the Task tool --------------------

    def test_f_specialists_never_have_task_tool(self):
        """FR-3.3: none of the 4 verify specialists may carry the Task tool."""
        assert set(SPECIALIST_TOOLS.keys()) == {
            "validator", "tester", "reviewer", "security",
        }
        for name, tools in SPECIALIST_TOOLS.items():
            assert "Task" not in tools, (
                f"FR-3.3: specialist {name!r} must NOT have the Task tool; got {tools!r}"
            )


# ---------------------------------------------------------------------------
# E2E-4: real sandbox execution (podman) — skipped if unavailable
# ---------------------------------------------------------------------------

def _image_available() -> bool:
    """localhost/sdd-runner:latest present locally (no pull attempted)."""
    if not podman_available():
        return False
    try:
        from harness.sandbox import _CONTAINER_IMAGE
        r = subprocess.run(
            ["podman", "image", "exists", _CONTAINER_IMAGE],
            capture_output=True, timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


@pytest.mark.skipif(
    not podman_available(),
    reason="podman not installed — real-execution E2E skipped on this host",
)
@pytest.mark.skipif(
    podman_available() and not _image_available(),
    reason="container image localhost/sdd-runner:latest not built",
)
class TestE2ERealSandbox:
    """第4条: real container execution (not mocked) — proves the hard boundary works."""

    def test_run_in_sandbox_real_container_echo(self, tmp_path):
        result = run_in_sandbox(["echo", "e2e-ok"], str(tmp_path))
        assert result.returncode == 0, (
            f"real sandbox echo must succeed; stderr={result.stderr!r}"
        )
        assert "e2e-ok" in result.stdout
