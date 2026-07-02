"""
tests/test_state.py — Unit tests for TaskState schema.

AC(T1.1) / 第2条:
  - Exactly 10 fields (no body/diff/log extras).
  - verify_findings carries the reduce_findings reducer (Phase 4 S1 resolved).

Phase 4 S1 resolution (updated from Phase 1):
  Previously: verify_findings used operator.add as the reducer.
  Problem: operator.add([], []) == [] was a no-op; returning [] from build()
           could not signal "reset findings for this new round" since
           operator.add(existing_findings, []) just appends nothing.
  Fix:     reduce_findings(old, new) where new is None → [] (reset signal),
           and new is a list → (old or []) + new (parallel append).
           build() now returns {"verify_findings": None} to trigger reset.
  Result:  reject→rebuild→re-verify cycles no longer accumulate stale findings.
"""
from __future__ import annotations

import typing

import pytest

from graph.state import TaskState, reduce_findings

EXPECTED_FIELDS = {
    "task_id",
    "spec_path",
    "constitution_digest",
    "context_slice_ids",
    "worktree_path",
    "build_artifact_ref",
    "verify_findings",
    "eval_score",
    "attempt",
    "decision",
}

# Fields that would indicate body content in state (第2条 violation)
FORBIDDEN_BODY_FIELDS = {"body", "diff", "log", "content", "text", "code", "source"}


def _hints() -> dict:
    """Return full type hints including Annotated metadata."""
    return typing.get_type_hints(TaskState, include_extras=True)


class TestTaskStateFields:
    def test_exact_10_fields(self):
        """TaskState must have exactly 10 fields — no more, no fewer."""
        hints = _hints()
        assert len(hints) == 10, (
            f"Expected 10 fields, got {len(hints)}: {sorted(hints)}"
        )

    def test_field_names_match_spec(self):
        """Field names must exactly match docs/plan.md §4."""
        hints = _hints()
        assert set(hints.keys()) == EXPECTED_FIELDS, (
            f"Unexpected fields: {set(hints.keys()) ^ EXPECTED_FIELDS}"
        )

    def test_verify_findings_has_reduce_findings_reducer(self):
        """
        Phase 4 S1 resolved: verify_findings must use reduce_findings, NOT operator.add.

        reduce_findings is a custom reducer that supports:
          - reset semantics: reduce_findings(old, None) → [] (build round start)
          - append semantics: reduce_findings(old, list) → old + list (verify branches)

        This resolves S1 (phase-context.json pending_issues) where operator.add
        could not distinguish a "reset" from an "empty append", causing stale
        findings to accumulate across reject→rebuild cycles.
        """
        hints = _hints()
        vf_type = hints["verify_findings"]

        # Must be an Annotated type
        assert hasattr(vf_type, "__metadata__"), (
            "verify_findings must be Annotated[list[str], reduce_findings]; "
            "missing __metadata__"
        )
        assert reduce_findings in vf_type.__metadata__, (
            f"reduce_findings not found in Annotated metadata: {vf_type.__metadata__}"
        )

    def test_no_body_fields_in_state(self):
        """
        第2条: state must not carry body content (diff, log, code, etc.).
        Only paths and IDs are allowed.
        """
        hints = _hints()
        collisions = set(hints.keys()) & FORBIDDEN_BODY_FIELDS
        assert not collisions, (
            f"Body/content fields found in TaskState (第2条 violation): {collisions}"
        )


class TestReduceFindings:
    """
    Unit tests for the reduce_findings custom reducer (S1 resolution).

    These tests prove the core property of Phase 4 S1:
      - Returning None from build() resets the list to [] for a new round.
      - Returning a list from verify() appends without losing old findings
        within the same round (parallel merge, FR-3.2).
    """

    def test_reset_on_none_clears_existing_findings(self):
        """
        reduce_findings(old, None) → [] regardless of old content.
        This is the "build node signals new round" path (S1 fix).
        """
        assert reduce_findings(["f1", "f2"], None) == []

    def test_reset_on_none_when_old_is_empty(self):
        """reduce_findings([], None) → [] (reset an already-empty list)."""
        assert reduce_findings([], None) == []

    def test_reset_on_none_when_old_is_none(self):
        """reduce_findings(None, None) → [] (both sides None, still reset)."""
        assert reduce_findings(None, None) == []

    def test_append_list_to_existing(self):
        """
        reduce_findings(old, new_list) → old + new_list (no overwrite, FR-3.2).
        """
        result = reduce_findings(["existing"], ["new1", "new2"])
        assert result == ["existing", "new1", "new2"]

    def test_append_to_empty(self):
        """reduce_findings([], new_list) → new_list (first append after reset)."""
        assert reduce_findings([], ["f1", "f2"]) == ["f1", "f2"]

    def test_append_to_none_old(self):
        """reduce_findings(None, new_list) → new_list (None old treated as [])."""
        assert reduce_findings(None, ["f1"]) == ["f1"]

    def test_append_empty_list_is_noop(self):
        """reduce_findings(old, []) → old (appending empty list preserves old)."""
        assert reduce_findings(["existing"], []) == ["existing"]

    def test_s1_reject_rebuild_cycle_does_not_accumulate(self):
        """
        S1 resolved: reject→rebuild→reverify must NOT accumulate stale findings.

        Simulates the full cycle:
          Round 1: build resets (None), verify appends [f1, f2]
          Reject
          Round 2: build resets (None), verify appends [f3, f4]
          Expected: state after round 2 == [f3, f4] (NOT [f1, f2, f3, f4])
        """
        # Round 1: initial state is []
        state_verify_findings: list[str] = []

        # build round 1: returns None → reset
        state_verify_findings = reduce_findings(state_verify_findings, None)
        assert state_verify_findings == [], "Round 1 build must reset to []"

        # verify round 1: returns [f1, f2] → append
        state_verify_findings = reduce_findings(state_verify_findings, ["f1", "f2"])
        assert state_verify_findings == ["f1", "f2"]

        # --- reject path: back to build ---

        # build round 2: returns None → reset (S1 fix: must clear f1, f2!)
        state_verify_findings = reduce_findings(state_verify_findings, None)
        assert state_verify_findings == [], (
            "S1: Round 2 build must reset to [] — stale findings must not persist"
        )

        # verify round 2: returns [f3, f4] → append
        state_verify_findings = reduce_findings(state_verify_findings, ["f3", "f4"])
        assert state_verify_findings == ["f3", "f4"], (
            "S1: Round 2 findings must be [f3, f4], not accumulated with round 1"
        )
        assert "f1" not in state_verify_findings, "f1 (stale) must not appear in round 2"
        assert "f2" not in state_verify_findings, "f2 (stale) must not appear in round 2"
