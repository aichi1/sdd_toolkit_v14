"""
graph/state.py — Lean TaskState for sdd_toolkit_v14.

第2条: 状態はパス/IDのみ。本文(diff・生成コード・トレース)はディスクに置く。

Phase 4 (S1 resolved):
  verify_findings reducer replaced from operator.add to reduce_findings.
  reduce_findings(old, None) → []       (build node resets between rounds)
  reduce_findings(old, list) → old+list (verify appends within a round)
  This resolves the S1 issue where operator.add could not distinguish a
  "reset" signal from an "empty append" — an empty list [] was a no-op.
"""
from __future__ import annotations

from typing import Annotated, TypedDict


def reduce_findings(
    old: list[str] | None,
    new: list[str] | None,
) -> list[str]:
    """
    Custom reducer for verify_findings (resolves Phase 3 S1).

    Per-round reset semantics:
      - new is None  → reset to []   (sent by build node at round start)
      - new is list  → append        (sent by verify branches in parallel)

    This allows the build node to signal "new round, clear stale findings"
    by returning {"verify_findings": None}, while parallel verify sub-agents
    append their findings with {"verify_findings": [...]}.

    Args:
        old: Current state value (list or None on very first state init).
        new: Update from a node's returned dict.

    Returns:
        [] on reset; (old or []) + new on append.
    """
    if new is None:
        return []
    return (old or []) + new


class TaskState(TypedDict):
    task_id: str
    spec_path: str                                        # path only, no body content
    constitution_digest: str                              # short hash, not full text
    context_slice_ids: list[str]                         # ChromaDB chunk IDs
    worktree_path: str                                    # Builder's work tree path
    build_artifact_ref: str                              # path/ref to artifact, not content
    verify_findings: Annotated[list[str], reduce_findings]  # reset-on-None, append-on-list
    eval_score: float | None
    attempt: int                                         # re-build counter
    decision: str | None                                 # "approved" | "rejected" | None
