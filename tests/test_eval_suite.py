"""
tests/test_eval_suite.py — Unit tests for harness/eval_suite.py (Phase 6 / T6.1).

Coverage:
  第6条: eval_suite reuses eval/rubric.json (7 axes) and eval/aggregate.py (mean).
  第10条 / S-#1: scan_code is integrated — a vuln artifact yields security_findings.
  第7条: evaluate() computes eval_score; EVAL_SCORE_THRESHOLD is respected.
  FR-4.1: regression input (security finding) triggers regressed=True.

All tests are offline and deterministic (no network, no LLM calls).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import pytest

from harness.eval_suite import (
    MAX_EVAL_ATTEMPTS,
    EVAL_SCORE_THRESHOLD,
    _RUBRIC_PATH,
    _compute_axis_scores,
    _check_baseline_regression,
    evaluate,
)
from harness.security_checks import Finding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_code() -> str:
    """Minimal code with no security issues."""
    return "def add(a, b):\n    return a + b\n"


def _vuln_code_cwe78() -> str:
    """CWE-78: OS command injection via os.system."""
    return "import os\nos.system(user_input)\n"


def _vuln_code_cwe95() -> str:
    """CWE-95: dynamic eval of untrusted input."""
    return "result = eval(user_expression)\n"


def _vuln_code_cwe798() -> str:
    """CWE-798: hard-coded credential."""
    return "password = 'hunter2'\n"


# ---------------------------------------------------------------------------
# Tests: 第6条 — eval/rubric.json 7 axes are reused
# ---------------------------------------------------------------------------

class TestRubricReuse:
    """
    第6条: evaluate() must read eval/rubric.json and use its axis keys.
    eval/aggregate.py mean() must be the scoring function (no reimplementation).
    """

    def test_rubric_file_exists(self):
        """eval/rubric.json must exist (dependency for eval_suite)."""
        assert _RUBRIC_PATH.exists(), f"eval/rubric.json not found at {_RUBRIC_PATH}"

    def test_rubric_has_seven_axes(self):
        """eval/rubric.json must define exactly 7 axes."""
        rubric = json.loads(_RUBRIC_PATH.read_text())
        axes = [a["key"] for a in rubric["axes"]]
        assert len(axes) == 7, f"Expected 7 axes, got {len(axes)}: {axes}"

    def test_axis_scores_uses_all_rubric_keys(self):
        """
        第6条: axis_scores in evaluate() must include ALL 7 keys from rubric.json.
        No axis should be added or removed relative to the rubric.
        """
        rubric = json.loads(_RUBRIC_PATH.read_text())
        expected_keys = {a["key"] for a in rubric["axes"]}

        result = evaluate(_clean_code(), findings=[])
        returned_keys = set(result["axis_scores"].keys())

        assert returned_keys == expected_keys, (
            f"第6条: axis_scores keys {returned_keys} must match rubric.json keys {expected_keys}"
        )

    def test_axis_scores_normalized_to_0_1(self):
        """Each axis score must be in the [0.0, 1.0] range (normalized)."""
        result = evaluate(_clean_code(), findings=[])
        for key, score in result["axis_scores"].items():
            assert 0.0 <= score <= 1.0, (
                f"Axis '{key}' score {score} is outside [0,1] range"
            )

    def test_eval_score_is_mean_of_axis_scores(self):
        """
        第6条: eval_score must equal the mean of axis_scores (reuses aggregate.mean).
        """
        result = evaluate(_clean_code(), findings=[])
        axis_values = list(result["axis_scores"].values())
        expected_mean = round(sum(axis_values) / len(axis_values), 4)

        assert abs(result["eval_score"] - expected_mean) < 1e-3, (
            f"eval_score {result['eval_score']} ≠ mean({axis_values}) = {expected_mean}"
        )


# ---------------------------------------------------------------------------
# Tests: 第10条 / S-#1 — scan_code is integrated in evaluate()
# ---------------------------------------------------------------------------

class TestScanCodeIntegrated:
    """
    第10条 / S-#1: eval_suite must call scan_code internally.
    A deliberately vulnerable artifact must yield security_findings.
    This resolves the Phase 5 pending issue S-#1.
    """

    def test_clean_code_has_no_security_findings(self):
        """A clean artifact must produce zero security_findings."""
        result = evaluate(_clean_code(), findings=[])
        assert result["security_findings"] == [], (
            f"Expected [] for clean code, got {result['security_findings']!r}"
        )

    def test_cwe78_detected(self):
        """CWE-78 (OS command injection) must be detected by scan_code in evaluate()."""
        result = evaluate(_vuln_code_cwe78(), findings=[])
        cwe_ids = {f.cwe_id for f in result["security_findings"]}
        assert "CWE-78" in cwe_ids, (
            f"第10条: CWE-78 not detected; findings: {result['security_findings']!r}"
        )

    def test_cwe95_detected(self):
        """CWE-95 (eval/exec injection) must be detected."""
        result = evaluate(_vuln_code_cwe95(), findings=[])
        cwe_ids = {f.cwe_id for f in result["security_findings"]}
        assert "CWE-95" in cwe_ids, (
            f"第10条: CWE-95 not detected; findings: {result['security_findings']!r}"
        )

    def test_cwe798_detected(self):
        """CWE-798 (hard-coded credentials) must be detected."""
        result = evaluate(_vuln_code_cwe798(), findings=[])
        cwe_ids = {f.cwe_id for f in result["security_findings"]}
        assert "CWE-798" in cwe_ids, (
            f"第10条: CWE-798 not detected; findings: {result['security_findings']!r}"
        )

    def test_security_findings_are_finding_objects(self):
        """security_findings must be a list of Finding objects (not plain strings)."""
        result = evaluate(_vuln_code_cwe78(), findings=[])
        for f in result["security_findings"]:
            assert isinstance(f, Finding), (
                f"security_findings must contain Finding objects, got {type(f)}"
            )
            assert hasattr(f, "cwe_id")
            assert hasattr(f, "owasp_cat")
            assert hasattr(f, "description")
            assert hasattr(f, "location")

    def test_scan_on_file_path(self, tmp_path: Path):
        """evaluate() accepts a file Path and scans its content."""
        vuln_file = tmp_path / "vuln.py"
        vuln_file.write_text(_vuln_code_cwe78())

        result = evaluate(vuln_file, findings=[])
        assert len(result["security_findings"]) > 0, (
            "第10条: file path scan must detect CWE-78 in vuln.py"
        )

    def test_scan_on_artifact_in_state(self, tmp_path: Path):
        """evaluate() reads build_artifact_ref from a TaskState dict."""
        art = tmp_path / "artifact.py"
        art.write_text(_vuln_code_cwe78())

        state = {
            "build_artifact_ref": str(art),
            "task_id": "test-state-scan",
        }
        result = evaluate(state, findings=[])
        assert len(result["security_findings"]) > 0, (
            "第10条: state dict scan (via build_artifact_ref) must detect CWE-78"
        )

    def test_scan_on_missing_artifact_ref_does_not_raise(self, tmp_path: Path):
        """evaluate() with a missing artifact_ref must not raise — returns empty findings."""
        state = {
            "build_artifact_ref": str(tmp_path / "nonexistent.py"),
        }
        result = evaluate(state, findings=[])  # must not raise
        # No artifact text → no security findings
        assert isinstance(result["security_findings"], list)


# ---------------------------------------------------------------------------
# Tests: regression detection
# ---------------------------------------------------------------------------

class TestRegressionDetection:
    """
    第7条: regressed=True triggers the conditional edge back to build.
    FR-4.1: an intentional regression input (low score OR security finding)
            makes the post-eval conditional edge route to build.
    """

    def test_security_finding_triggers_regression(self):
        """
        FR-4.1: a vuln artifact (CWE hit) → regressed=True, regardless of score.
        第10条: security_findings non-empty always → regressed.
        """
        result = evaluate(_vuln_code_cwe78(), findings=[])
        assert result["regressed"] is True, (
            "FR-4.1 / 第10条: security finding must set regressed=True"
        )

    def test_clean_artifact_not_regressed(self):
        """A clean artifact with no findings → regressed=False."""
        result = evaluate(_clean_code(), findings=[])
        assert result["regressed"] is False, (
            "Clean artifact must NOT be regressed"
        )

    def test_below_threshold_triggers_regression(self):
        """
        If eval_score < EVAL_SCORE_THRESHOLD, regressed must be True.
        Use many findings to push score below threshold.

        Note: 10 findings reduce correctness and robustness to 0 → total score
        drops well below EVAL_SCORE_THRESHOLD (0.4).
        """
        # 10 findings → correctness=0, robustness=0 → mean drops significantly
        many_findings = [f"finding-{i}" for i in range(10)]
        result = evaluate(_clean_code(), findings=many_findings)
        # With 10 findings: correctness=0, robustness=0, others=0.6
        # mean = (0+0.6+0.6+0+0.6+0.6+0.6)/7 ≈ 0.343 < 0.4 → regressed
        if result["eval_score"] < EVAL_SCORE_THRESHOLD:
            assert result["regressed"] is True, (
                f"eval_score={result['eval_score']} < THRESHOLD={EVAL_SCORE_THRESHOLD} "
                "must set regressed=True"
            )

    def test_many_findings_lower_score_vs_clean(self):
        """
        More verify_findings must produce a lower eval_score than no findings.
        """
        result_clean = evaluate(_clean_code(), findings=[])
        result_findings = evaluate(_clean_code(), findings=["f1", "f2", "f3"])
        assert result_findings["eval_score"] < result_clean["eval_score"], (
            "3 verify_findings must lower eval_score vs 0 findings"
        )

    def test_regressed_always_true_with_security_finding(self):
        """
        regressed=True when security_findings present, EVEN IF score ≥ THRESHOLD.
        This ensures CWE/OWASP hits always trigger the retry gate.
        """
        result = evaluate(_vuln_code_cwe798(), findings=[])
        # CWE-798 → security_findings non-empty → regressed=True
        assert result["regressed"] is True, (
            "CWE-798 finding must set regressed=True regardless of numeric score"
        )

    def test_no_baseline_file_means_threshold_only(self, tmp_path: Path, monkeypatch):
        """
        If no eval-suite-baseline.json exists, _check_baseline_regression returns False.
        Regression detection falls back to threshold-only mode.
        """
        import harness.eval_suite as es_module
        # Point baseline path to a nonexistent file
        monkeypatch.setattr(es_module, "_BASELINE_PATH", tmp_path / "no-baseline.json")
        result = _check_baseline_regression(0.5)
        assert result is False, "No baseline file must return False (threshold-only mode)"

    def test_with_baseline_file_detects_drop(self, tmp_path: Path, monkeypatch):
        """
        If eval-suite-baseline.json exists, a large drop below baseline triggers regression.
        """
        import harness.eval_suite as es_module

        baseline_file = tmp_path / "eval-suite-baseline.json"
        baseline_file.write_text(json.dumps({"eval_score": 0.8}))
        monkeypatch.setattr(es_module, "_BASELINE_PATH", baseline_file)

        # Current score 0.8 - 0.3 = 0.5, tolerance is 0.15 → 0.8 - 0.15 = 0.65 > 0.5 → regressed
        result = _check_baseline_regression(0.5)
        assert result is True, (
            "Score 0.5 vs baseline 0.8 (tolerance 0.15) must be regressed"
        )

    def test_with_baseline_file_no_regression_within_tolerance(
        self, tmp_path: Path, monkeypatch
    ):
        """Score within tolerance of baseline → no baseline regression."""
        import harness.eval_suite as es_module

        baseline_file = tmp_path / "eval-suite-baseline.json"
        baseline_file.write_text(json.dumps({"eval_score": 0.6}))
        monkeypatch.setattr(es_module, "_BASELINE_PATH", baseline_file)

        # current 0.5 vs baseline 0.6, tolerance 0.15 → threshold = 0.45 < 0.5 → NOT regressed
        result = _check_baseline_regression(0.5)
        assert result is False, (
            "Score 0.5 vs baseline 0.6 (tolerance 0.15) must NOT be regressed"
        )


# ---------------------------------------------------------------------------
# Tests: evaluate() return structure
# ---------------------------------------------------------------------------

class TestEvaluateReturnStructure:
    """Verify the evaluate() return dict has the required keys and types."""

    def test_returns_dict_with_required_keys(self):
        """evaluate() must return a dict with exactly the required keys."""
        result = evaluate(_clean_code(), findings=[])
        required = {"eval_score", "regressed", "axis_scores", "security_findings"}
        assert required.issubset(result.keys()), (
            f"Missing keys: {required - result.keys()}"
        )

    def test_eval_score_is_float(self):
        result = evaluate(_clean_code(), findings=[])
        assert isinstance(result["eval_score"], float), (
            f"eval_score must be float, got {type(result['eval_score'])}"
        )

    def test_regressed_is_bool(self):
        result = evaluate(_clean_code(), findings=[])
        assert isinstance(result["regressed"], bool), (
            f"regressed must be bool, got {type(result['regressed'])}"
        )

    def test_axis_scores_is_dict_of_floats(self):
        result = evaluate(_clean_code(), findings=[])
        assert isinstance(result["axis_scores"], dict)
        for k, v in result["axis_scores"].items():
            assert isinstance(v, float), f"axis_scores[{k!r}] must be float, got {type(v)}"

    def test_security_findings_is_list(self):
        result = evaluate(_clean_code(), findings=[])
        assert isinstance(result["security_findings"], list)

    def test_findings_none_treated_as_empty(self):
        """evaluate(text, findings=None) must behave identically to findings=[]."""
        r_none = evaluate(_clean_code(), findings=None)
        r_empty = evaluate(_clean_code(), findings=[])
        assert r_none["eval_score"] == r_empty["eval_score"]
        assert r_none["regressed"] == r_empty["regressed"]

    def test_happy_path_score_above_threshold(self):
        """
        第7条: a clean artifact with no findings must score ≥ EVAL_SCORE_THRESHOLD.
        Ensures the happy-path (stub build) always passes the gate.
        """
        result = evaluate(_clean_code(), findings=[])
        assert result["eval_score"] >= EVAL_SCORE_THRESHOLD, (
            f"Clean artifact must score ≥ {EVAL_SCORE_THRESHOLD}; "
            f"got {result['eval_score']}"
        )
        assert not result["regressed"]

    def test_happy_path_with_stub_artifact_text(self):
        """
        The stub build writes 'STUB artifact for {task_id}, attempt {n}' as content.
        This text must also score ≥ THRESHOLD (integration path for the test graph).
        """
        stub_text = "STUB artifact for integ-task-1, attempt 0\nBuild task: integ-task-1\n"
        result = evaluate(stub_text, findings=[])
        assert result["eval_score"] >= EVAL_SCORE_THRESHOLD, (
            f"Stub build artifact must pass threshold; got {result['eval_score']}"
        )
        assert not result["regressed"]


# ---------------------------------------------------------------------------
# Tests: compute_axis_scores directly
# ---------------------------------------------------------------------------

class TestComputeAxisScores:
    """Unit tests for _compute_axis_scores (internal helper)."""

    def test_no_findings_returns_base_score(self):
        """With no findings, each axis should be at the neutral base (0.6)."""
        scores = _compute_axis_scores([], [])
        for ax, score in scores.items():
            assert abs(score - 0.6) < 1e-3, (
                f"Axis {ax!r} base score should be 0.6, got {score}"
            )

    def test_verify_findings_reduce_correctness(self):
        """verify_findings must reduce the correctness and robustness scores."""
        scores_0 = _compute_axis_scores([], [])
        scores_3 = _compute_axis_scores(["f1", "f2", "f3"], [])
        assert scores_3["correctness"] < scores_0["correctness"]
        assert scores_3["robustness"] < scores_0["robustness"]
        # Other axes should be unchanged
        assert scores_3["safety"] == scores_0["safety"]

    def test_security_findings_reduce_safety_and_correctness(self):
        """Security findings must reduce safety and correctness, but not other axes."""
        dummy_finding = Finding(
            cwe_id="CWE-78",
            owasp_cat="A03:2021",
            description="test",
            location="line 1",
        )
        scores_0 = _compute_axis_scores([], [])
        scores_sec = _compute_axis_scores([], [dummy_finding])
        assert scores_sec["safety"] < scores_0["safety"]
        assert scores_sec["correctness"] < scores_0["correctness"]
        # efficiency, completeness, maintainability, usability unchanged
        for ax in ("efficiency", "completeness", "maintainability", "usability"):
            assert scores_sec[ax] == scores_0[ax], (
                f"Axis {ax!r} should be unchanged by security finding"
            )

    def test_scores_never_below_zero(self):
        """Deductions must floor at 0 (never negative)."""
        many_findings = [f"f{i}" for i in range(100)]
        many_security = [
            Finding("CWE-78", "A03", "desc", "loc") for _ in range(100)
        ]
        scores = _compute_axis_scores(many_findings, many_security)
        for ax, score in scores.items():
            assert score >= 0.0, f"Axis {ax!r} score {score} went below 0"
