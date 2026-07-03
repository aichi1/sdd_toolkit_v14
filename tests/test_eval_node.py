"""
tests/test_eval_node.py — Unit tests for eval_node in graph/nodes.py (Phase 6 / T6.2).

Coverage:
  第7条: eval_node routes based on eval_score threshold.
  第8条 / FR-4.2: record_run is called for every eval_node invocation.
  第10条: security findings (via eval_suite) set eval_score=0.0 (regressed).
  NFR-4: attempt cap routes to review even when score is below threshold.

All tests are offline — no real API calls.  The observability store is redirected
to a temp path via SDD_OBS_STORE env var to avoid writing to ~/.sdd-runs/.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

import graph.nodes as nodes_module
from graph.nodes import eval_node
from harness.eval_suite import EVAL_SCORE_THRESHOLD, MAX_EVAL_ATTEMPTS
from langgraph.types import Command


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def redirect_obs_store(tmp_path: Path, monkeypatch):
    """Redirect the observability JSONL store to a temp path for all tests."""
    obs_path = tmp_path / "observations.jsonl"
    monkeypatch.setenv("SDD_OBS_STORE", str(obs_path))
    return obs_path


@pytest.fixture
def clean_artifact(tmp_path: Path) -> str:
    """Write a clean artifact (no security issues) and return its path."""
    art = tmp_path / "artifact.txt"
    art.write_text("def add(a, b):\n    return a + b\n")
    return str(art)


@pytest.fixture
def vuln_artifact(tmp_path: Path) -> str:
    """Write a vulnerable artifact (CWE-78) and return its path."""
    art = tmp_path / "artifact_vuln.py"
    art.write_text("import os\nos.system(user_input)\n")
    return str(art)


def _base_state(**overrides: Any) -> dict:
    """Minimal TaskState dict for eval_node tests."""
    state: dict[str, Any] = {
        "task_id": "eval-node-test",
        "spec_path": "/tmp/spec.md",
        "constitution_digest": "sha256:abc123",
        "context_slice_ids": [],
        "worktree_path": "/tmp/wt",
        "build_artifact_ref": "",
        "verify_findings": [],
        "eval_score": None,
        "attempt": 0,
        "decision": None,
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# Tests: return type
# ---------------------------------------------------------------------------

class TestEvalNodeReturnType:
    def test_returns_command(self, clean_artifact: str):
        """eval_node must return a LangGraph Command."""
        state = _base_state(build_artifact_ref=clean_artifact)
        result = eval_node(state)
        assert isinstance(result, Command), (
            f"eval_node must return Command, got {type(result)}"
        )

    def test_command_goto_is_string(self, clean_artifact: str):
        """Command.goto must be a string (node name)."""
        state = _base_state(build_artifact_ref=clean_artifact)
        cmd = eval_node(state)
        assert isinstance(cmd.goto, str), f"Command.goto must be str, got {type(cmd.goto)}"

    def test_command_update_has_eval_score(self, clean_artifact: str):
        """Command.update must contain 'eval_score'."""
        state = _base_state(build_artifact_ref=clean_artifact)
        cmd = eval_node(state)
        assert "eval_score" in cmd.update, (
            f"Command.update must contain 'eval_score'; got keys: {cmd.update.keys()}"
        )


# ---------------------------------------------------------------------------
# Tests: happy path routing (第7条)
# ---------------------------------------------------------------------------

class TestEvalNodeHappyPath:
    """
    第7条: a clean artifact with no findings must score ≥ THRESHOLD and route to review.
    """

    def test_clean_artifact_routes_to_review(self, clean_artifact: str):
        """
        FR-4.1 (positive case): clean artifact → eval_score ≥ THRESHOLD → goto="review".
        """
        state = _base_state(build_artifact_ref=clean_artifact, attempt=0)
        cmd = eval_node(state)
        assert cmd.goto == "review", (
            f"第7条: clean artifact must route to 'review'; got {cmd.goto!r}"
        )

    def test_clean_eval_score_at_least_threshold(self, clean_artifact: str):
        """eval_score in Command.update must be ≥ EVAL_SCORE_THRESHOLD."""
        state = _base_state(build_artifact_ref=clean_artifact)
        cmd = eval_node(state)
        assert cmd.update["eval_score"] >= EVAL_SCORE_THRESHOLD, (
            f"Clean artifact eval_score {cmd.update['eval_score']} < "
            f"threshold {EVAL_SCORE_THRESHOLD}"
        )

    def test_stub_artifact_text_routes_to_review(self, tmp_path: Path):
        """
        The stub build produces 'STUB artifact for {task_id}, attempt N'.
        This text must pass the eval gate (integration alignment).
        """
        art = tmp_path / "artifact.txt"
        art.write_text("STUB artifact for stub-task, attempt 0\nBuild task: stub-task\n")

        state = _base_state(
            task_id="stub-task",
            build_artifact_ref=str(art),
            attempt=0,
        )
        cmd = eval_node(state)
        assert cmd.goto == "review", (
            "Stub artifact (no findings, no security) must route to review"
        )


# ---------------------------------------------------------------------------
# Tests: regression path routing (第7条 / FR-4.1)
# ---------------------------------------------------------------------------

class TestEvalNodeRegressionPath:
    """
    FR-4.1: an intentional regression input makes the post-eval conditional edge
    route to 'build' (retry).
    第10条: security findings (scan_code) cause regressed=True → eval_score=0.0.
    """

    def test_vuln_artifact_routes_to_build(self, vuln_artifact: str):
        """
        FR-4.1: vulnerable artifact (CWE-78) → regressed=True → goto="build".
        This is the key FR-4.1 AC: the conditional edge fires on regression.
        """
        state = _base_state(build_artifact_ref=vuln_artifact, attempt=0)
        cmd = eval_node(state)
        assert cmd.goto == "build", (
            f"FR-4.1: vuln artifact must route to 'build' (regression retry); "
            f"got goto={cmd.goto!r}"
        )

    def test_vuln_artifact_sets_eval_score_to_zero(self, vuln_artifact: str):
        """
        When regressed=True (security finding), eval_node must set eval_score=0.0
        so the review node sees a clear failure signal.
        """
        state = _base_state(build_artifact_ref=vuln_artifact, attempt=0)
        cmd = eval_node(state)
        assert cmd.update["eval_score"] == 0.0, (
            f"Regressed artifact must have eval_score=0.0 in state; "
            f"got {cmd.update['eval_score']}"
        )

    def test_vuln_artifact_increments_attempt(self, vuln_artifact: str):
        """
        When routing to 'build' (retry), attempt must be incremented in Command.update.
        """
        initial_attempt = 0
        state = _base_state(build_artifact_ref=vuln_artifact, attempt=initial_attempt)
        cmd = eval_node(state)
        assert cmd.goto == "build"
        assert cmd.update.get("attempt") == initial_attempt + 1, (
            f"attempt must increment on retry; expected {initial_attempt + 1}, "
            f"got {cmd.update.get('attempt')}"
        )

    def test_multiple_security_cwe_types_route_to_build(self, tmp_path: Path):
        """
        Any CWE hit (not just CWE-78) must trigger regression routing.
        Test with CWE-798 (hard-coded credentials).
        """
        art = tmp_path / "cred.py"
        art.write_text("password = 'hunter2'\nAPI_KEY = 'abc123'\n")

        state = _base_state(build_artifact_ref=str(art), attempt=0)
        cmd = eval_node(state)
        assert cmd.goto == "build", (
            "CWE-798 (hard-coded credentials) must route to 'build'"
        )

    def test_monkeypatched_regression_routes_to_build(self, clean_artifact: str, monkeypatch):
        """
        Verify routing by monkeypatching _eval_suite_evaluate to return regressed=True.
        Decoupled from the actual scoring logic.
        """
        def mock_evaluate(state_or_artifact, findings=None):
            return {
                "eval_score": 0.2,  # below threshold
                "regressed": True,
                "axis_scores": {},
                "security_findings": [],
            }

        monkeypatch.setattr(nodes_module, "_eval_suite_evaluate", mock_evaluate)

        state = _base_state(build_artifact_ref=clean_artifact, attempt=0)
        cmd = eval_node(state)
        assert cmd.goto == "build", (
            "Monkeypatched regression (regressed=True) must route to 'build'"
        )

    def test_monkeypatched_pass_routes_to_review(self, clean_artifact: str, monkeypatch):
        """
        Verify routing by monkeypatching _eval_suite_evaluate to return pass.
        """
        def mock_evaluate(state_or_artifact, findings=None):
            return {
                "eval_score": 0.8,
                "regressed": False,
                "axis_scores": {},
                "security_findings": [],
            }

        monkeypatch.setattr(nodes_module, "_eval_suite_evaluate", mock_evaluate)

        state = _base_state(build_artifact_ref=clean_artifact, attempt=0)
        cmd = eval_node(state)
        assert cmd.goto == "review", (
            "Monkeypatched pass (regressed=False, score=0.8) must route to 'review'"
        )


# ---------------------------------------------------------------------------
# Tests: attempt cap (NFR-4)
# ---------------------------------------------------------------------------

class TestEvalNodeAttemptCap:
    """
    NFR-4: eval_node must stop retrying when attempt ≥ MAX_EVAL_ATTEMPTS.
    Prevents infinite retry loops even when artifact consistently fails eval.
    """

    def test_at_max_attempts_routes_to_review(self, vuln_artifact: str):
        """
        NFR-4: when attempt == MAX_EVAL_ATTEMPTS, eval_node must route to 'review'
        even if the artifact has security findings (regressed=True).
        """
        state = _base_state(
            build_artifact_ref=vuln_artifact,
            attempt=MAX_EVAL_ATTEMPTS,  # exactly at the cap
        )
        cmd = eval_node(state)
        assert cmd.goto == "review", (
            f"NFR-4: attempt={MAX_EVAL_ATTEMPTS} (cap) must route to 'review'; "
            f"got {cmd.goto!r}"
        )

    def test_above_max_attempts_routes_to_review(self, vuln_artifact: str):
        """attempt > MAX_EVAL_ATTEMPTS must also route to review (belt-and-suspenders)."""
        state = _base_state(
            build_artifact_ref=vuln_artifact,
            attempt=MAX_EVAL_ATTEMPTS + 5,
        )
        cmd = eval_node(state)
        assert cmd.goto == "review", (
            f"attempt > MAX_EVAL_ATTEMPTS must still route to 'review'"
        )

    def test_one_below_cap_still_retries(self, vuln_artifact: str):
        """Just below cap (MAX_EVAL_ATTEMPTS - 1): must still retry (goto='build')."""
        attempt = MAX_EVAL_ATTEMPTS - 1
        state = _base_state(build_artifact_ref=vuln_artifact, attempt=attempt)
        cmd = eval_node(state)
        assert cmd.goto == "build", (
            f"attempt={attempt} < MAX_EVAL_ATTEMPTS={MAX_EVAL_ATTEMPTS} "
            "must still retry (goto='build')"
        )

    def test_capped_eval_still_records_observability(self, vuln_artifact: str, tmp_path: Path):
        """
        Even when the attempt cap fires, record_run() must still be called (第8条).
        """
        from harness.observability import read_observations

        obs_path = tmp_path / "cap_obs.jsonl"
        os.environ["SDD_OBS_STORE"] = str(obs_path)

        state = _base_state(
            build_artifact_ref=vuln_artifact,
            attempt=MAX_EVAL_ATTEMPTS,
        )
        eval_node(state)

        obs = read_observations(obs_path)
        assert len(obs) >= 1, "record_run must be called even at attempt cap"

    def test_attempt_cap_is_max_eval_attempts_constant(self):
        """MAX_EVAL_ATTEMPTS constant must be positive integer."""
        assert isinstance(MAX_EVAL_ATTEMPTS, int)
        assert MAX_EVAL_ATTEMPTS > 0


# ---------------------------------------------------------------------------
# Tests: observability (第8条 / FR-4.2)
# ---------------------------------------------------------------------------

class TestEvalNodeObservability:
    """
    第8条 / FR-4.2: eval_node must call record_run() for every invocation.
    Verified by checking that the record exists after eval_node runs.
    """

    def test_eval_node_writes_observation_record(
        self, clean_artifact: str, tmp_path: Path
    ):
        """
        FR-4.2: after eval_node runs, at least one record must exist in the store.
        """
        from harness.observability import read_observations

        obs_path = tmp_path / "obs_test.jsonl"
        os.environ["SDD_OBS_STORE"] = str(obs_path)

        state = _base_state(build_artifact_ref=clean_artifact)
        eval_node(state)

        records = read_observations(obs_path)
        assert len(records) >= 1, (
            "FR-4.2 / 第8条: eval_node must write at least one record to the store"
        )

    def test_eval_node_record_has_required_fields(
        self, clean_artifact: str, tmp_path: Path
    ):
        """
        FR-4.2: the record must contain total_cost_usd and tokens.
        """
        from harness.observability import read_observations

        obs_path = tmp_path / "obs_fields.jsonl"
        os.environ["SDD_OBS_STORE"] = str(obs_path)

        state = _base_state(task_id="obs-field-test", build_artifact_ref=clean_artifact)
        eval_node(state)

        records = read_observations(obs_path)
        assert len(records) >= 1
        # eval_node now writes an eval_breakdown row too (T-4); the FR-4.2 cost
        # record is the run record, uniquely identified by having no record_type.
        rec = next(r for r in records if r.get("record_type") is None)
        assert "total_cost_usd" in rec, "FR-4.2: record must have total_cost_usd"
        assert "tokens" in rec, "FR-4.2: record must have tokens"
        assert "run_id" in rec, "record must have run_id"
        assert rec["run_id"] == "obs-field-test"

    def test_eval_node_record_has_eval_score(self, clean_artifact: str, tmp_path: Path):
        """The observation record must include eval_score for traceability."""
        from harness.observability import read_observations

        obs_path = tmp_path / "obs_score.jsonl"
        os.environ["SDD_OBS_STORE"] = str(obs_path)

        state = _base_state(build_artifact_ref=clean_artifact)
        eval_node(state)

        records = read_observations(obs_path)
        assert records[0].get("eval_score") is not None, (
            "Observation record must include eval_score"
        )
