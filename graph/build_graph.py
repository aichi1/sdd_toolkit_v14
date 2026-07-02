"""
graph/build_graph.py — Assemble the LangGraph StateGraph with SqliteSaver checkpoint.

FR-5.1: SqliteSaver persists state to a file-based SQLite DB; never :memory:.
         Same thread_id resumes from the last checkpoint (NFR-2).
FR-4.1: eval node gates the review interrupt — artifact must pass eval before
         reaching the human approval gate (第7条).
NFR-4:  MAX_EVAL_ATTEMPTS enforced in eval_node; cost ceiling via MAX_TURNS.

Usage:
    graph = build_graph()                    # uses default "state.db"
    graph = build_graph("custom.db")         # custom path
    graph = build_graph(conn=existing_conn)  # share a connection (useful in tests)

Graph topology (Phase 6):
    START → spec_load → assemble_context → build → verify → eval ─(pass)──→ review ─(approve)→ END
                                              ↑──────(fail/cap)────────────┘           ↑─(reject)──┘
                                              └──────────────────(reject via Command)────────────────┘

    eval routing is handled by Command returned from eval_node (no conditional edge):
      - eval_score ≥ THRESHOLD and not regressed → "review"    (pass, 第7条 gate cleared)
      - eval_score < THRESHOLD or regressed      → "build"     (retry, attempt incremented)
      - attempt ≥ MAX_EVAL_ATTEMPTS              → "review"    (attempt cap, NFR-4)

    review routing is handled by Command returned from review node (unchanged):
      - approve → merge_worktree + END (第3条)
      - reject  → "build" with attempt+1

Phase 6 changes from Phase 3–5:
  - Added: verify node wired between build and eval (Phase 4 Deferral 1 resolved)
  - Added: eval node (eval_node) between verify and review
  - Removed: direct build→review edge (now build→verify→eval→review via Command)
  - Updated imports: added verify, eval_node
  - NFR-4 constants exported: MAX_EVAL_ATTEMPTS, MAX_TURNS (from harness.observability)

Backward compatibility:
  - All Phase 1–5 integration tests still pass.  The default stub path
    (stub build → stub verify → clean artifact → eval_score=0.60 ≥ 0.40)
    always reaches the review interrupt.
  - accept/reject Command semantics from review node are unchanged.
  - State schema (TaskState) is unchanged (10 fields, same types).
"""
from __future__ import annotations

import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from graph.nodes import assemble_context, build, eval_node, review, spec_load, verify
from graph.state import TaskState

# Re-export NFR-4 constants for documentation / test introspection
from harness.observability import MAX_EVAL_ATTEMPTS, MAX_TURNS  # noqa: F401


def build_graph(
    db_path: str = "state.db",
    conn: sqlite3.Connection | None = None,
) -> "CompiledGraph":  # noqa: F821 — forward ref to avoid heavy import at module level
    """
    Build and compile the Phase-6 StateGraph.

    Args:
        db_path: Path to the SQLite DB file (ignored when conn is provided).
                 NEVER use ':memory:' — persistence across process restarts is required (FR-5.1).
        conn:    Existing sqlite3.Connection to reuse.
                 Useful in tests to share a single DB file across two graph instances.

    Returns:
        Compiled LangGraph graph with SqliteSaver checkpointer.

    Graph topology (Phase 6):
        START → spec_load → assemble_context → build → verify → eval → review ─(approve)→ END
                                                 ↑─────────(eval fail/reject)──────────────┘
                                                            (via Command in eval_node/review)

    eval_node uses Command-based routing (第9条: control flow is in the graph, not the LLM):
        eval_score ≥ THRESHOLD and not regressed → "review"
        eval_score < THRESHOLD or regressed      → "build"  (attempt incremented)
        attempt ≥ MAX_EVAL_ATTEMPTS              → "review" (cap, NFR-4)
    """
    if conn is None:
        conn = sqlite3.connect(db_path, check_same_thread=False)

    checkpointer = SqliteSaver(conn)

    builder = StateGraph(TaskState)

    # ── Nodes ─────────────────────────────────────────────────────────────
    builder.add_node("spec_load", spec_load)
    builder.add_node("assemble_context", assemble_context)   # Phase 3
    builder.add_node("build", build)
    builder.add_node("verify", verify)                       # Phase 4 (wired Phase 6)
    builder.add_node("eval", eval_node)                      # Phase 6
    builder.add_node("review", review)

    # ── Edges ─────────────────────────────────────────────────────────────
    # Linear path: spec_load → assemble_context → build → verify → eval
    builder.add_edge(START, "spec_load")
    builder.add_edge("spec_load", "assemble_context")
    builder.add_edge("assemble_context", "build")
    builder.add_edge("build", "verify")
    builder.add_edge("verify", "eval")

    # eval → (review | build) via Command returned by eval_node
    # (no add_conditional_edges needed — eval_node's Command handles routing)

    # review → (END | build) via Command returned by review node (Phase 1, unchanged)

    return builder.compile(checkpointer=checkpointer)
