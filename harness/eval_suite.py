"""
harness/eval_suite.py — Regression detection + scoring (Phase 6 / T6.1).

第7条: 評価でリリースをゲートする
  eval_score が EVAL_SCORE_THRESHOLD 未満なら eval_node がリトライを指示する。

第10条: セキュリティは構築時から (S-#1 resolved)
  scan_code を import することで eval_suite に CWE/OWASP 検査項目が存在する
  (第10条の「既知脆弱性クラスの検査項目が eval_suite に存在すること」を満たす)。

第6条: 既存資産を再利用し、二重化しない
  - eval/rubric.json   — 7 軸の軸キー・ラベル・スケールを読む (再利用)
  - eval/aggregate.py  — mean() / load_json() を import (再実装しない)
  - harness/security_checks.py — scan_code / Finding を import (再実装しない)

Public API
──────────
    from harness.eval_suite import evaluate, EVAL_SCORE_THRESHOLD, MAX_EVAL_ATTEMPTS

    result = evaluate(state_or_artifact, findings)
    # result["eval_score"]        float   normalized 0–1
    # result["regressed"]         bool
    # result["axis_scores"]       dict    per-axis normalized 0–1
    # result["security_findings"] list[Finding]

Scoring (offline / deterministic)
──────────────────────────────────
Base score per axis = 3.0 / 5.0 = 0.60 (neutral, no findings).

Deductions (raw, before normalization):
  correctness  -= 0.5 per verify_finding
  robustness   -= 0.3 per verify_finding
  safety       -= 1.5 per security_finding
  correctness  -= 0.5 per security_finding (additional)
All raw deductions are floored at 0.

Final eval_score = mean(normalized_axis_values).

Regression conditions (any one → regressed=True):
  1. security_findings present           (CWE/OWASP hit)
  2. eval_score < EVAL_SCORE_THRESHOLD   (numeric quality gate)
  3. eval_score < baseline - tolerance   (baseline drop; threshold-only if no baseline file)

Attempt cap
───────────
MAX_EVAL_ATTEMPTS  — maximum eval→build retry cycles before forcing review.
                     Imported and checked by eval_node in graph/nodes.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Union

# 第10条 / S-#1: scan_code is the shared CWE/OWASP check bank (Phase 5).
# Its presence here satisfies 第10条の「eval_suite に検査項目が存在すること」.
from harness.security_checks import Finding, scan_code

# 第6条: reuse eval/aggregate.py utilities — do NOT re-implement mean() / load_json().
from eval.aggregate import load_json, mean

# ---------------------------------------------------------------------------
# Paths to eval/ assets
# ---------------------------------------------------------------------------

_RUBRIC_PATH: Path = (
    Path(__file__).resolve().parent.parent / "eval" / "rubric.json"
)
_BASELINE_PATH: Path = (
    Path(__file__).resolve().parent.parent / "eval" / "eval-suite-baseline.json"
)

# ---------------------------------------------------------------------------
# Public constants
# ---------------------------------------------------------------------------

EVAL_SCORE_THRESHOLD: float = 0.4
"""Minimum normalized score for the artifact to pass the eval gate (第7条).

eval_score < THRESHOLD → eval_node returns Command(goto="build") (retry).
eval_score >= THRESHOLD AND not regressed → Command(goto="review").

Chosen so that a clean artifact with no findings scores 0.60 (>= 0.40),
and any security finding forces regressed=True (eval_score → 0.0 in eval_node),
guaranteeing the conditional edge fires on any CWE/OWASP hit.
"""

MAX_EVAL_ATTEMPTS: int = 3
"""Maximum eval→build retry cycles before the attempt cap forces review.

After MAX_EVAL_ATTEMPTS retries, eval_node routes to review regardless of score
(NFR-4 / attempt cap / cost ceiling).  Human reviewer sees the failing eval_score
and can approve or reject.
"""

# ---------------------------------------------------------------------------
# Internal scoring constants
# ---------------------------------------------------------------------------

_AXIS_BASE_RAW: float = 3.0          # raw per-axis base (out of rubric max=5.0)
_DEDUCT_FINDING_CORRECTNESS: float = 0.5   # raw deduction per verify_finding
_DEDUCT_FINDING_ROBUSTNESS: float = 0.3    # raw deduction per verify_finding
_DEDUCT_SECURITY_SAFETY: float = 1.5       # raw deduction per security_finding
_DEDUCT_SECURITY_CORRECTNESS: float = 0.5  # raw deduction per security_finding
_BASELINE_TOLERANCE: float = 0.15          # regression tolerance vs stored baseline


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _load_rubric() -> dict:
    """Load eval/rubric.json.  Raises FileNotFoundError if missing."""
    return load_json(_RUBRIC_PATH)


def _compute_axis_scores(
    findings: list[str],
    security_findings: list[Finding],
) -> dict[str, float]:
    """
    Compute per-axis normalized scores (0–1) from verify_findings and security findings.

    Reads 7 axis keys from eval/rubric.json (第6条: reuse, not reinvention).
    Normalization: raw / rubric["scale"]["max"].

    Returns:
        {axis_key: normalized_score_0_to_1, ...}  — 7 entries.
    """
    rubric = _load_rubric()
    scale_max: float = float(rubric["scale"]["max"])   # 5.0
    axes: list[str] = [a["key"] for a in rubric["axes"]]  # 7 keys

    # Start at neutral base score
    raw: dict[str, float] = {ax: _AXIS_BASE_RAW for ax in axes}

    # Deduct for functional verify_findings (correctness + robustness axes)
    n_f = len(findings)
    if n_f:
        raw["correctness"] = max(
            0.0, raw["correctness"] - n_f * _DEDUCT_FINDING_CORRECTNESS
        )
        raw["robustness"] = max(
            0.0, raw["robustness"] - n_f * _DEDUCT_FINDING_ROBUSTNESS
        )

    # Deduct for security findings (safety + correctness axes)
    n_s = len(security_findings)
    if n_s:
        raw["safety"] = max(0.0, raw["safety"] - n_s * _DEDUCT_SECURITY_SAFETY)
        raw["correctness"] = max(
            0.0, raw["correctness"] - n_s * _DEDUCT_SECURITY_CORRECTNESS
        )

    return {ax: round(raw[ax] / scale_max, 4) for ax in axes}


def _check_baseline_regression(current_score: float) -> bool:
    """
    Compare current_score against a stored eval-suite baseline.

    Loads _BASELINE_PATH if it exists (e.g. saved by a previous good run).
    If the file does not exist → returns False (threshold-only mode, per spec:
    "use eval/history / a stored baseline if present, else threshold-only").

    Note: eval/history/ contains human-scored SDD-run evaluations (0–5 scale
    across T1/T2/T3 scenarios).  Those are NOT comparable to artifact quality
    scores from this function.  We use a separate _BASELINE_PATH
    (eval/eval-suite-baseline.json) for apples-to-apples comparison.

    Returns:
        True if current_score < (baseline_eval_score - BASELINE_TOLERANCE).
    """
    if not _BASELINE_PATH.exists():
        return False
    try:
        baseline = load_json(_BASELINE_PATH)
        baseline_score: float = float(baseline.get("eval_score", 0.0))
        return current_score < (baseline_score - _BASELINE_TOLERANCE)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate(
    state_or_artifact: "dict | str | Path",
    findings: list[str] | None = None,
) -> dict:
    """
    Evaluate a build artifact or TaskState for regression (Phase 6 / T6.1).

    第7条 enforcement:
        Returns eval_score and regressed.  eval_node uses these to decide
        whether to retry (goto="build") or proceed (goto="review").

    第10条 enforcement:
        scan_code() is called whenever artifact text is non-empty.  Any
        CWE/OWASP finding it returns sets regressed=True regardless of the
        numeric score.

    第6条 compliance:
        Reads eval/rubric.json for 7 axis keys.
        Calls eval/aggregate.py mean() for the overall score.
        Calls harness/security_checks.py scan_code() for CWE checks.
        No duplicated logic.

    Args:
        state_or_artifact:
            - TaskState dict: artifact text read from state["build_artifact_ref"]
            - Path: file is read and scanned
            - str: treated as code text to scan directly
        findings:
            verify_findings list from the verify node.  None → treated as [].

    Returns:
        {
          "eval_score":        float         — normalized 0–1 mean of all axis scores
          "regressed":         bool          — True if any regression condition is met
          "axis_scores":       dict[str,float] — per-axis normalized scores (7 axes)
          "security_findings": list[Finding] — CWE/OWASP findings from scan_code
        }

    Regression conditions (any one → regressed=True):
        1. security_findings non-empty      (CWE/OWASP hit)
        2. eval_score < EVAL_SCORE_THRESHOLD (numeric quality gate)
        3. eval_score < baseline - tolerance (baseline drop)
    """
    if findings is None:
        findings = []

    # ── Resolve artifact text ───────────────────────────────────────────────
    artifact_text: str = ""
    if isinstance(state_or_artifact, dict):
        artifact_ref: str = state_or_artifact.get("build_artifact_ref", "")
        if artifact_ref:
            try:
                artifact_text = Path(artifact_ref).read_text(
                    encoding="utf-8", errors="replace"
                )
            except (OSError, FileNotFoundError):
                artifact_text = ""
    elif isinstance(state_or_artifact, Path):
        try:
            artifact_text = state_or_artifact.read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            artifact_text = ""
    else:
        artifact_text = str(state_or_artifact)

    # ── Security checks (第10条) ────────────────────────────────────────────
    security_findings: list[Finding] = (
        scan_code(artifact_text) if artifact_text else []
    )

    # ── Axis scores (reuses rubric.json axes + aggregate.mean, 第6条) ───────
    axis_scores: dict[str, float] = _compute_axis_scores(findings, security_findings)

    # ── Overall score (reuses eval/aggregate.py mean(), 第6条) ──────────────
    eval_score: float = round(mean(list(axis_scores.values())), 4)

    # ── Regression detection ────────────────────────────────────────────────
    regressed: bool = (
        bool(security_findings)                    # CWE/OWASP → always regressed
        or eval_score < EVAL_SCORE_THRESHOLD       # numeric gate
        or _check_baseline_regression(eval_score)  # vs stored baseline
    )

    return {
        "eval_score": eval_score,
        "regressed": regressed,
        "axis_scores": axis_scores,
        "security_findings": security_findings,
    }
