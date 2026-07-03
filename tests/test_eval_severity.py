"""
tests/test_eval_severity.py — severity-weighted eval_suite (T-3/T-4).

Verifies severity/role parsing of findings, severity-weighted scoring driven by
eval/rubric.json weights (no hardcode), the "any HIGH → regressed" gate, the
eval_breakdown observability record, and strict backward compatibility with the
pre-loading (severity-less) behavior.

OFFLINE: pure functions + eval_node with evaluate() monkeypatched.
"""

import os

import pytest

from harness import eval_suite
from harness.eval_suite import (
    evaluate,
    _compute_axis_scores,
    _finding_role,
    _finding_severity,
    _finding_breakdown,
)


# ---------------------------------------------------------------------------
# T-3: severity / role parsing (AC-3.2, AC-3.3)
# ---------------------------------------------------------------------------

class TestFindingParsing:
    def test_extracts_high(self):
        assert _finding_severity("[security] [HIGH] sql injection (根拠: db.py:12)") == "HIGH"

    def test_extracts_low(self):
        assert _finding_severity("[reviewer] [LOW] rename var (根拠: a.py:3)") == "LOW"

    def test_severityless_defaults_med(self):
        """AC-3.3: old-format finding (no severity token) defaults to MED."""
        assert _finding_severity("[validator] AC-2 not covered") == "MED"

    def test_role_extracted(self):
        assert _finding_role("[security] [HIGH] x") == "security"

    def test_role_missing_is_unknown(self):
        assert _finding_role("[HIGH] no role prefix") == "unknown"

    def test_breakdown_counts(self):
        role_counts, sev_counts = _finding_breakdown(
            ["[security] [HIGH] a", "[security] [MED] b", "[tester] c"]
        )
        assert role_counts == {"security": 2, "tester": 1}
        assert sev_counts == {"HIGH": 1, "MED": 2, "LOW": 0}


# ---------------------------------------------------------------------------
# T-4: severity-weighted scoring (AC-3.3 backward compat, AC-4.2 no hardcode)
# ---------------------------------------------------------------------------

class TestSeverityWeightedScoring:
    def test_med_equals_pre_loading(self):
        """AC-3.3: two MED (=severity-less) findings reproduce the pre-loading score.

        Pre-loading baseline (eval/history/2026-07-03_v14-pre-loading.json):
        two_plain_findings → correctness 0.4, robustness 0.48.
        """
        scores = _compute_axis_scores(
            ["[validator] AC-2 not covered", "[tester] no test for error path"], []
        )
        assert scores["correctness"] == 0.4
        assert scores["robustness"] == 0.48

    def test_high_deducts_more_than_low(self):
        high = _compute_axis_scores(["[security] [HIGH] x"], [])
        low = _compute_axis_scores(["[security] [LOW] x"], [])
        assert high["correctness"] < low["correctness"]

    def test_weights_from_rubric_are_honored(self, monkeypatch):
        """AC-4.2: changing the rubric weights changes the score (no hardcode)."""
        base = _compute_axis_scores(["[x] [HIGH] y"], [])

        def _bigger_weights():
            return {
                "verify_finding": {"HIGH": {"correctness": 3.0, "robustness": 0.9}},
                "security_finding": {"safety": 1.5, "correctness": 0.5},
                "default_severity": "MED",
            }

        monkeypatch.setattr(eval_suite, "_load_weights", _bigger_weights)
        heavier = _compute_axis_scores(["[x] [HIGH] y"], [])
        assert heavier["correctness"] < base["correctness"]


# ---------------------------------------------------------------------------
# T-4: HIGH → regressed gate (AC-4.1)
# ---------------------------------------------------------------------------

class TestHighRegressionGate:
    def test_single_high_marks_regressed(self):
        result = evaluate("def f(): pass\n", ["[reviewer] [HIGH] god object (根拠: a.py)"])
        assert result["regressed"] is True
        assert result["severity_counts"]["HIGH"] == 1

    def test_med_only_not_regressed_by_severity(self):
        """A couple of MED findings do not trip the HIGH gate (score still >= threshold)."""
        result = evaluate("def f(): pass\n", ["[reviewer] [MED] minor (根拠: a.py)"])
        assert result["severity_counts"]["HIGH"] == 0

    def test_high_routes_eval_node_to_build(self, monkeypatch, tmp_path):
        """AC-4.1: a HIGH finding makes eval_node route back to build."""
        from graph import nodes

        monkeypatch.setenv("SDD_OBS_STORE", str(tmp_path / "obs.jsonl"))
        # real evaluate() with a HIGH finding
        cmd = nodes.eval_node({
            "task_id": "sev-1",
            "attempt": 0,
            "verify_findings": ["[security] [HIGH] hardcoded secret (根拠: cfg.py:4)"],
            "build_artifact_ref": "",
        })
        assert cmd.goto == "build"


# ---------------------------------------------------------------------------
# T-4: eval_breakdown observability (AC-4.3)
# ---------------------------------------------------------------------------

class TestEvalBreakdownRecord:
    def test_breakdown_recorded(self, monkeypatch, tmp_path):
        from graph import nodes
        from harness.observability import read_observations

        store = tmp_path / "obs.jsonl"
        monkeypatch.setenv("SDD_OBS_STORE", str(store))
        nodes.eval_node({
            "task_id": "bd-1",
            "attempt": 0,
            "verify_findings": ["[security] [HIGH] a (根拠: x)", "[tester] [MED] b (根拠: y)"],
            "build_artifact_ref": "",
        })
        breakdowns = [
            r for r in read_observations(store)
            if r.get("record_type") == "eval_breakdown"
        ]
        assert len(breakdowns) == 1
        bd = breakdowns[0]
        assert bd["role_counts"] == {"security": 1, "tester": 1}
        assert bd["severity_counts"]["HIGH"] == 1
        assert bd["severity_counts"]["MED"] == 1

    def test_breakdown_excluded_from_cost_sums(self, monkeypatch, tmp_path):
        """eval_breakdown must not be counted as an agent_call cost row."""
        from harness.observability import sum_agent_costs, record_eval_breakdown

        store = tmp_path / "obs.jsonl"
        monkeypatch.setenv("SDD_OBS_STORE", str(store))
        record_eval_breakdown("r1", {"security": 1}, {"HIGH": 1, "MED": 0, "LOW": 0})
        cost, tokens = sum_agent_costs("r1", store_path=store)
        assert cost == 0.0
        assert tokens == {"input": 0, "output": 0}
