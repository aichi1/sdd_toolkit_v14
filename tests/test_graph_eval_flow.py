"""
tests/test_graph_eval_flow.py — Integration tests for Phase 6 eval flow (FR-4.1).

AC(T6.1) / AC(T6.2) / FR-4.1:
  - Intentional regression input → eval conditional edge routes to 'build' (retry).
  - Happy path (clean artifact) → eval routes to 'review'.
  - Attempt cap: after MAX_EVAL_ATTEMPTS retries, graph terminates (no infinite loop).

Phase 4 Deferral 1 (resolved):
  - verify node is now wired in the topology: build → verify → eval → review.
  - Tests verify that build → verify → eval → review is the actual path.

Tests use the following strategies:
  A. Direct eval_node(state) → Command assertion (fast, no graph overhead).
  B. Full graph integration with monkeypatched nodes (topology verification).
  C. Stub/offline mode only — no real API calls, no network.

IMPORTANT: All Phase 1–5 integration tests still pass (verified in CI).
           The new topology (adding verify + eval) is transparent to the
           existing tests because the stub path (stub verify → clean artifact →
           eval_score=0.60 ≥ 0.40) always reaches the review interrupt.
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import pytest

import graph.nodes as nodes_module
from graph.build_graph import MAX_EVAL_ATTEMPTS, MAX_TURNS, build_graph
from graph.nodes import eval_node
from harness.eval_suite import EVAL_SCORE_THRESHOLD, MAX_EVAL_ATTEMPTS as ES_MAX
from langgraph.types import Command


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def redirect_obs_store(tmp_path: Path, monkeypatch):
    """Redirect observability store to avoid polluting ~/.sdd-runs/ in tests."""
    monkeypatch.setenv("SDD_OBS_STORE", str(tmp_path / "obs.jsonl"))


@pytest.fixture
def clean_artifact_path(tmp_path: Path) -> str:
    """Clean artifact file (no security issues)."""
    art = tmp_path / "artifact.txt"
    art.write_text("STUB artifact for test-task, attempt 0\n")
    return str(art)


@pytest.fixture
def vuln_artifact_path(tmp_path: Path) -> str:
    """Vulnerable artifact file (CWE-78 → security_findings → regressed=True)."""
    art = tmp_path / "vuln_artifact.py"
    art.write_text("import os\nos.system(user_input)\n")
    return str(art)


def _base_state(artifact_ref: str = "", attempt: int = 0, **overrides) -> dict:
    """Minimal TaskState dict for graph flow tests."""
    state: dict[str, Any] = {
        "task_id": "graph-eval-test",
        "spec_path": "/tmp/spec.md",
        "constitution_digest": "sha256:abc",
        "context_slice_ids": [],
        "worktree_path": "/tmp/wt",
        "build_artifact_ref": artifact_ref,
        "verify_findings": [],
        "eval_score": None,
        "attempt": attempt,
        "decision": None,
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# Tests: conditional edge — direct eval_node Command assertion (FR-4.1)
# ---------------------------------------------------------------------------

class TestConditionalEdgeViaCommand:
    """
    FR-4.1 AC: intentional regression input → edge routes to 'build'.
    Tests verify by calling eval_node() directly and checking Command.goto.

    This tests the routing logic without graph overhead, making it fast and
    reliably deterministic (no random state, no network).
    """

    def test_regression_routes_to_build(self, vuln_artifact_path: str):
        """
        FR-4.1 (primary assertion):
        Intentional regression input (CWE-78 vuln artifact) → eval_node returns
        Command(goto='build').  This is the conditional edge firing on regression.
        """
        state = _base_state(artifact_ref=vuln_artifact_path, attempt=0)
        cmd = eval_node(state)

        assert cmd.goto == "build", (
            f"FR-4.1: regression input must route eval→build; got goto={cmd.goto!r}. "
            "The conditional edge must fire for intentional regression."
        )

    def test_happy_path_routes_to_review(self, clean_artifact_path: str):
        """
        FR-4.1 (positive case): clean artifact → Command(goto='review').
        The happy-path default MUST reach review (integration test alignment).
        """
        state = _base_state(artifact_ref=clean_artifact_path, attempt=0)
        cmd = eval_node(state)

        assert cmd.goto == "review", (
            f"FR-4.1: happy path must route eval→review; got goto={cmd.goto!r}"
        )

    def test_low_score_below_threshold_routes_to_build(self, monkeypatch):
        """
        Low eval_score (below THRESHOLD) also routes to build (not just security findings).
        """
        def mock_low_score(state_or_artifact, findings=None):
            return {
                "eval_score": 0.1,  # well below THRESHOLD=0.4
                "regressed": True,
                "axis_scores": {},
                "security_findings": [],
            }

        monkeypatch.setattr(nodes_module, "_eval_suite_evaluate", mock_low_score)

        state = _base_state()
        cmd = eval_node(state)
        assert cmd.goto == "build", (
            f"Low score ({0.1} < {EVAL_SCORE_THRESHOLD}) must route to 'build'"
        )

    def test_score_exactly_at_threshold_routes_to_review(self, monkeypatch):
        """
        score == EVAL_SCORE_THRESHOLD is a PASS (not regressed → review).
        The condition is eval_score < THRESHOLD (strict less-than).
        """
        threshold = EVAL_SCORE_THRESHOLD

        def mock_at_threshold(state_or_artifact, findings=None):
            return {
                "eval_score": threshold,
                "regressed": False,
                "axis_scores": {},
                "security_findings": [],
            }

        monkeypatch.setattr(nodes_module, "_eval_suite_evaluate", mock_at_threshold)

        state = _base_state()
        cmd = eval_node(state)
        assert cmd.goto == "review", (
            f"eval_score == THRESHOLD ({threshold}) must route to 'review' (pass, not fail)"
        )

    def test_score_just_above_threshold_routes_to_review(self, monkeypatch):
        """score slightly above THRESHOLD → review (pass)."""
        def mock_above(state_or_artifact, findings=None):
            return {
                "eval_score": EVAL_SCORE_THRESHOLD + 0.01,
                "regressed": False,
                "axis_scores": {},
                "security_findings": [],
            }

        monkeypatch.setattr(nodes_module, "_eval_suite_evaluate", mock_above)

        state = _base_state()
        cmd = eval_node(state)
        assert cmd.goto == "review"

    def test_score_just_below_threshold_routes_to_build(self, monkeypatch):
        """score slightly below THRESHOLD → build (fail)."""
        def mock_below(state_or_artifact, findings=None):
            return {
                "eval_score": EVAL_SCORE_THRESHOLD - 0.01,
                "regressed": True,  # below threshold sets regressed
                "axis_scores": {},
                "security_findings": [],
            }

        monkeypatch.setattr(nodes_module, "_eval_suite_evaluate", mock_below)

        state = _base_state(attempt=0)
        cmd = eval_node(state)
        assert cmd.goto == "build"


# ---------------------------------------------------------------------------
# Tests: attempt cap — no infinite loop (NFR-4)
# ---------------------------------------------------------------------------

class TestAttemptCap:
    """
    NFR-4: eval_node must terminate the retry loop at MAX_EVAL_ATTEMPTS.
    After MAX_EVAL_ATTEMPTS retries, eval_node must route to 'review'
    even if the artifact consistently fails evaluation.
    """

    def test_cap_at_max_eval_attempts(self, vuln_artifact_path: str):
        """
        NFR-4 (primary assertion): attempt == MAX_EVAL_ATTEMPTS → goto='review'.
        Prevents infinite eval→build→verify→eval loop.
        """
        state = _base_state(
            artifact_ref=vuln_artifact_path,
            attempt=MAX_EVAL_ATTEMPTS,  # exactly at cap
        )
        cmd = eval_node(state)
        assert cmd.goto == "review", (
            f"NFR-4: attempt={MAX_EVAL_ATTEMPTS} must cap and route to 'review'; "
            f"got {cmd.goto!r}"
        )

    def test_no_infinite_loop_in_eval_node_sequence(self, vuln_artifact_path: str):
        """
        NFR-4: simulate MAX_EVAL_ATTEMPTS+1 calls to eval_node and verify
        the cap fires before any hypothetical infinite loop.

        Simulates: build → eval (fail, attempt=1) → build → eval (fail, attempt=2)
                   → build → eval (fail, attempt=3=MAX) → review (cap)
        """
        attempt = 0
        routes: list[str] = []

        for _ in range(MAX_EVAL_ATTEMPTS + 2):
            state = _base_state(artifact_ref=vuln_artifact_path, attempt=attempt)
            cmd = eval_node(state)
            routes.append(cmd.goto)

            if cmd.goto == "build":
                attempt = cmd.update.get("attempt", attempt + 1)
            else:
                # Reached review → stop
                break

        assert routes[-1] == "review", (
            f"Final route must be 'review' (cap); got routes={routes!r}"
        )
        assert routes.count("build") <= MAX_EVAL_ATTEMPTS, (
            f"Must not exceed {MAX_EVAL_ATTEMPTS} 'build' routes; routes={routes!r}"
        )

    def test_attempt_increments_on_each_retry(self, vuln_artifact_path: str):
        """
        Each retry must increment attempt in Command.update so the cap is reachable.
        """
        attempt = 0
        for i in range(MAX_EVAL_ATTEMPTS):
            state = _base_state(artifact_ref=vuln_artifact_path, attempt=attempt)
            cmd = eval_node(state)
            if cmd.goto == "build":
                new_attempt = cmd.update.get("attempt")
                assert new_attempt == attempt + 1, (
                    f"Iteration {i}: attempt must increment; "
                    f"got {new_attempt}, expected {attempt + 1}"
                )
                attempt = new_attempt

    def test_max_eval_attempts_constant_positive(self):
        """MAX_EVAL_ATTEMPTS must be a positive integer > 0."""
        assert isinstance(MAX_EVAL_ATTEMPTS, int) and MAX_EVAL_ATTEMPTS > 0
        assert isinstance(ES_MAX, int) and ES_MAX == MAX_EVAL_ATTEMPTS

    def test_max_turns_constant_defined(self):
        """MAX_TURNS (NFR-4 cost ceiling) must be exported from build_graph."""
        assert isinstance(MAX_TURNS, int) and MAX_TURNS > 0


# ---------------------------------------------------------------------------
# Tests: new graph topology (Phase 4 Deferral 1 resolved)
# ---------------------------------------------------------------------------

class TestGraphTopologyWithVerify:
    """
    Phase 4 Deferral 1 resolved: verify is now wired in the graph topology.
    Tests verify that the graph includes the verify node and it is called.
    """

    def test_verify_node_is_in_graph(self):
        """
        build_graph() must include a 'verify' node (Phase 4 Deferral 1 resolved).
        """
        import sqlite3
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        g = build_graph(conn=conn)
        node_names = set(g.get_graph().nodes.keys())
        assert "verify" in node_names, (
            f"Phase 4 Deferral 1: 'verify' must be in graph nodes; got {node_names}"
        )

    def test_eval_node_is_in_graph(self):
        """build_graph() must include an 'eval' node (Phase 6 T6.2)."""
        import sqlite3
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        g = build_graph(conn=conn)
        node_names = set(g.get_graph().nodes.keys())
        assert "eval" in node_names, (
            f"Phase 6: 'eval' must be in graph nodes; got {node_names}"
        )

    def test_verify_node_precedes_eval_in_topology(self):
        """
        Phase 4 Deferral 1: verify must come before eval in the graph topology.
        Verified by checking that verify→eval edge exists (not eval→verify).
        """
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        g = build_graph(conn=conn)
        graph_def = g.get_graph()
        edges = {(e.source, e.target) for e in graph_def.edges}

        assert ("verify", "eval") in edges, (
            "Phase 4 Deferral 1: verify→eval edge must exist (verify runs before eval)"
        )
        assert ("eval", "verify") not in edges, (
            "eval must NOT come before verify in the topology"
        )


# ---------------------------------------------------------------------------
# Tests: build→verify→eval sequence edge verification
# ---------------------------------------------------------------------------

class TestGraphEdgeSequence:
    """Verify the Phase 6 edge sequence is correct in the compiled graph."""

    def test_build_to_verify_edge_exists(self):
        """build → verify edge must exist in the graph."""
        import sqlite3
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        g = build_graph(conn=conn)
        graph_def = g.get_graph()
        edges = {(e.source, e.target) for e in graph_def.edges}
        assert ("build", "verify") in edges, (
            f"Phase 4 Deferral 1: build→verify edge must exist; edges={edges}"
        )

    def test_verify_to_eval_edge_exists(self):
        """verify → eval edge must exist in the graph."""
        import sqlite3
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        g = build_graph(conn=conn)
        graph_def = g.get_graph()
        edges = {(e.source, e.target) for e in graph_def.edges}
        assert ("verify", "eval") in edges, (
            f"Phase 6: verify→eval edge must exist; edges={edges}"
        )

    def test_no_direct_build_to_review_edge(self):
        """
        Phase 6: there must NOT be a direct build→review edge anymore.
        The path is now build→verify→eval→(Command)→review.
        """
        import sqlite3
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        g = build_graph(conn=conn)
        graph_def = g.get_graph()
        edges = {(e.source, e.target) for e in graph_def.edges}
        assert ("build", "review") not in edges, (
            "Phase 6: direct build→review edge must NOT exist; "
            "routing goes through verify→eval now"
        )
