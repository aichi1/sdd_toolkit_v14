"""
harness/observability.py — Local offline observability store (Phase 6 / T6.3).

FR-4.2: run ごとにコスト・トークンが観測ストアに残る。
第8条: すべての run はトレースされ、コストとトークン(サブエージェントはモデル別内訳)が記録される。
NFR-4: max_turns 等でオーケストレーターのコスト上限を設ける。

Architecture
────────────
Primary sink  : JSONL file at ~/.sdd-runs/observations.jsonl (local, offline).
                Path overridable via SDD_OBS_STORE env var (useful in tests).
                Written by _write_record(); silently skips on write error.

LangSmith     : Optional, guarded, default-off (SDD_ENABLE_LANGSMITH=1).
                langsmith==0.9.4 IS importable but egress is BLOCKED in this
                environment; the guard prevents hangs.  Import errors and
                network errors are silently caught.

OTel          : Optional, guarded, default-off (SDD_ENABLE_OTEL=1).
                Same pattern: import at call time, catch all exceptions.

Offline-safe  : record_run() ALWAYS writes to the local JSONL store first.
                LangSmith / OTel are best-effort after-thoughts — their failure
                never prevents the local record from being written.

NFR-4 constants
───────────────
MAX_TURNS         = 20   — maximum agent turns per invocation (pass to agent options).
MAX_EVAL_ATTEMPTS = 3    — maximum eval→build retry cycles (checked in eval_node).

Both are exported so callers can use them directly:

    from harness.observability import MAX_TURNS, MAX_EVAL_ATTEMPTS

Usage
─────
    from harness.observability import record_run

    record = record_run(
        run_id="task-abc",
        total_cost_usd=0.0123,          # from ResultMessage.total_cost_usd
        tokens={"input": 500, "output": 300},
        eval_score=0.72,                # extra metadata (optional)
    )
    # → record["record_id"], record["timestamp_utc"], etc.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# NFR-4: Cost ceiling constants (exported for callers)
# ---------------------------------------------------------------------------

MAX_TURNS: int = 20
"""Maximum agent turns per invocation (NFR-4).

Pass as `max_turns` to ClaudeAgentOptions to prevent run-away costs.
Exported here so build_graph.py / eval_node can reference the same constant.
"""

MAX_EVAL_ATTEMPTS: int = 3
"""Maximum eval→build retry cycles before the attempt cap forces review.

Re-exported from eval_suite to keep NFR-4 constants in one module.
eval_node checks this value in graph/nodes.py.
"""

# ---------------------------------------------------------------------------
# Local store
# ---------------------------------------------------------------------------

_DEFAULT_STORE_PATH: Path = Path.home() / ".sdd-runs" / "observations.jsonl"
"""Default JSONL store path (outside the git repo → never tracked).

Override with SDD_OBS_STORE env var for tests:
    monkeypatch.setenv("SDD_OBS_STORE", str(tmp_path / "obs.jsonl"))
"""


def get_store_path() -> Path:
    """Return the active observation store path."""
    env_path = os.environ.get("SDD_OBS_STORE")
    if env_path:
        return Path(env_path)
    return _DEFAULT_STORE_PATH


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def record_run(
    run_id: str,
    total_cost_usd: float = 0.0,
    tokens: dict[str, int] | None = None,
    **metadata: Any,
) -> dict:
    """
    Record a run observation to the local JSONL store.

    FR-4.2 guarantee: a record with total_cost_usd and tokens is written for
    EVERY call, including stub/offline mode (zeros as placeholders).

    第8条 compliance: called from eval_node after every eval run.  In stub mode,
    total_cost_usd=0.0 and tokens={"input":0,"output":0} are placeholders —
    the structural guarantee (record exists) satisfies FR-4.2.

    NFR-4: max_turns_ceiling is embedded in every record for audit visibility.

    Args:
        run_id:         Task ID or other unique identifier for this run.
        total_cost_usd: Total USD cost (0.0 in offline/stub mode).
                        Source: ResultMessage.total_cost_usd when available.
        tokens:         Token usage dict.  Convention: {"input": N, "output": M}.
                        Sub-agent model breakdown can be added as extra keys.
                        None → {"input": 0, "output": 0}.
        **metadata:     Any additional fields (eval_score, attempt, regressed, …).

    Returns:
        The observation record dict that was written to the store.
    """
    if tokens is None:
        tokens = {"input": 0, "output": 0}

    record: dict[str, Any] = {
        "record_id": str(uuid.uuid4()),
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_cost_usd": total_cost_usd,
        "tokens": tokens,
        "max_turns_ceiling": MAX_TURNS,   # NFR-4: document cost ceiling in record
        **metadata,
    }

    # Primary sink: local JSONL (always, offline-safe)
    _write_record(record)

    # Optional sinks: best-effort, never block
    _try_langsmith(record)
    _try_otel(record)

    return record


def record_agent_call(
    run_id: str,
    role: str,
    total_cost_usd: float = 0.0,
    tokens: dict[str, int] | None = None,
    **metadata: Any,
) -> dict:
    """
    Record a single real Agent SDK call (builder or specialist) to the store.

    Written with record_type="agent_call" so it can be distinguished from
    eval-run records (which have no record_type key).  eval_node later sums
    these via sum_agent_costs() to report the real cost/token totals for a run
    (FR-4.2 / 第8条 — the values are now real, not placeholder zeros).

    Args:
        run_id:         Task ID (or worktree slug) tying this call to a run.
        role:           "builder" | "validator" | "tester" | "reviewer" | "security".
        total_cost_usd: From ResultMessage.total_cost_usd.
        tokens:         {"input": N, "output": M}; None → zeros.
        **metadata:     Extra fields (model, num_turns, …).

    Returns:
        The record dict that was written.
    """
    if tokens is None:
        tokens = {"input": 0, "output": 0}
    record: dict[str, Any] = {
        "record_id": str(uuid.uuid4()),
        "record_type": "agent_call",
        "run_id": run_id,
        "role": role,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "total_cost_usd": total_cost_usd,
        "tokens": tokens,
        **metadata,
    }
    _write_record(record)
    return record


def record_eval_breakdown(
    run_id: str,
    role_counts: dict[str, int] | None = None,
    severity_counts: dict[str, int] | None = None,
    **metadata: Any,
) -> dict:
    """
    Record an eval run's finding breakdown (T-4 / AC-4.3) to the store.

    Written with record_type="eval_breakdown" so it is EXCLUDED from
    sum_agent_costs() (which counts only record_type=="agent_call") and from the
    eval-run cost records.  Captures per-role finding counts and the HIGH/MED/LOW
    severity distribution so trends (e.g. new HIGH appearing) are auditable.

    Args:
        run_id:          Task ID tying this breakdown to a run.
        role_counts:     {"security": 2, "validator": 1, ...}; None → {}.
        severity_counts: {"HIGH": 1, "MED": 3, "LOW": 0}; None → zeros.
        **metadata:      Extra fields (attempt, eval_score, …).

    Returns:
        The record dict that was written.
    """
    record: dict[str, Any] = {
        "record_id": str(uuid.uuid4()),
        "record_type": "eval_breakdown",
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "role_counts": role_counts or {},
        "severity_counts": severity_counts or {"HIGH": 0, "MED": 0, "LOW": 0},
        **metadata,
    }
    _write_record(record)
    return record


def sum_agent_costs(
    run_id: str, store_path: Path | None = None
) -> tuple[float, dict[str, int]]:
    """
    Sum the cost and tokens of all agent_call records for a given run_id.

    Only records with record_type == "agent_call" are counted; eval-run records
    (which lack that key) are excluded.  Returns (0.0, {"input":0,"output":0})
    when no agent_call records exist — so stub/offline runs report zeros
    exactly as before (backward-compatible with existing tests).

    Args:
        run_id:     The task_id / worktree slug to aggregate.
        store_path: Override path. None → get_store_path().

    Returns:
        (total_cost_usd, {"input": Σ, "output": Σ, ...merged extra token keys}).
    """
    total_cost = 0.0
    tokens: dict[str, int] = {"input": 0, "output": 0}
    for rec in read_observations(store_path):
        if rec.get("record_type") != "agent_call":
            continue
        if rec.get("run_id") != run_id:
            continue
        try:
            total_cost += float(rec.get("total_cost_usd", 0.0) or 0.0)
        except (TypeError, ValueError):
            pass
        rec_tokens = rec.get("tokens") or {}
        for key, val in rec_tokens.items():
            try:
                tokens[key] = tokens.get(key, 0) + int(val)
            except (TypeError, ValueError):
                pass
    return total_cost, tokens


def read_observations(store_path: Path | None = None) -> list[dict]:
    """
    Read all run records from the local JSONL store.

    Args:
        store_path: Override path.  None → use get_store_path().

    Returns:
        List of observation dicts (oldest first).  [] if store does not exist.
    """
    path = store_path or get_store_path()
    if not path.exists():
        return []
    records: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return records


# ---------------------------------------------------------------------------
# Internal: local JSONL writer
# ---------------------------------------------------------------------------

def _write_record(record: dict) -> None:
    """
    Append record to JSONL store.  Silently swallows all exceptions.

    第8条 principle: observability must NEVER block or crash the main flow.
    If the store directory cannot be created or the file cannot be written,
    the error is suppressed (not re-raised).
    """
    try:
        store_path = get_store_path()
        store_path.parent.mkdir(parents=True, exist_ok=True)
        with store_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # best-effort: never block the orchestrator


# ---------------------------------------------------------------------------
# Optional: LangSmith (guarded, best-effort, default-off)
# ---------------------------------------------------------------------------

def _try_langsmith(record: dict) -> None:
    """
    Submit record to LangSmith (optional, offline-safe).

    Gate: SDD_ENABLE_LANGSMITH=1 (default-off).
    Safety: any exception (import, network, auth) is silently caught.

    Note: langsmith==0.9.4 is importable in this environment but egress is
    BLOCKED.  The SDD_ENABLE_LANGSMITH gate prevents spurious connection
    attempts and ensures tests pass without network access.
    """
    if not os.environ.get("SDD_ENABLE_LANGSMITH"):
        return
    try:
        import langsmith  # type: ignore[import]

        client = langsmith.Client()
        client.create_run(
            name=f"sdd_eval_{record.get('run_id', 'unknown')}",
            run_type="chain",
            inputs={"run_id": record.get("run_id")},
            outputs={
                "eval_score": record.get("eval_score"),
                "total_cost_usd": record.get("total_cost_usd"),
                "tokens": record.get("tokens"),
            },
            extra={"metadata": record},
        )
    except Exception:
        pass  # best-effort; network errors / auth errors are expected offline


# ---------------------------------------------------------------------------
# Optional: OTel (guarded, best-effort, default-off)
# ---------------------------------------------------------------------------

def _try_otel(record: dict) -> None:
    """
    Emit an OTel span for this run (optional, offline-safe).

    Gate: SDD_ENABLE_OTEL=1 (default-off).
    Safety: any exception (import, no tracer configured) is silently caught.
    """
    if not os.environ.get("SDD_ENABLE_OTEL"):
        return
    try:
        from opentelemetry import trace  # type: ignore[import]

        tracer = trace.get_tracer("sdd_toolkit_v14")
        with tracer.start_as_current_span("sdd_eval_run") as span:
            span.set_attribute("run_id", str(record.get("run_id", "")))
            span.set_attribute(
                "total_cost_usd", float(record.get("total_cost_usd", 0.0))
            )
            span.set_attribute("eval_score", float(record.get("eval_score", 0.0)))
            span.set_attribute(
                "tokens_input",
                int((record.get("tokens") or {}).get("input", 0)),
            )
            span.set_attribute(
                "tokens_output",
                int((record.get("tokens") or {}).get("output", 0)),
            )
    except Exception:
        pass  # best-effort; no tracer configured is the normal case offline
