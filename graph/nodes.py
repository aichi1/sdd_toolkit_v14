"""
graph/nodes.py — LangGraph node functions for sdd_toolkit_v14 (Phase 1–6).

Node contract:
  spec_load        — idempotent; sets path/digest/worktree_path (no body content).
  assemble_context — Phase 3; sets context_slice_ids (IDs only, 第2条).
                     Injection order: immutable constitution block first → slices
                     after (FR-2.2 prompt-cache hit condition).
  build            — invokes _invoke_builder (injectable seam) inside the worktree.
                     Stub mode (default, no API key needed): backward-compatible with
                     Phase 1 tests. Real mode (SDD_RUN_REAL_BUILDER=1): Agent SDK.
                     Phase 4 S1 fix: returns verify_findings=None to trigger reducer
                     reset between build rounds.
  verify           — Phase 4 (T4.3); runs Validator+Tester+Reviewer+Security in
                     parallel via asyncio.gather. Findings merged via reduce_findings
                     reducer (FR-3.2). _invoke_specialist is the injectable seam.
                     WIRED into build_graph.py topology from Phase 6 (Deferral 1 resolved).
  eval_node        — Phase 6 (T6.2); calls eval_suite.evaluate(), detects regression,
                     records observability, and returns Command with routing decision:
                       score ≥ THRESHOLD and not regressed → Command(goto="review")
                       score < THRESHOLD or regressed      → Command(goto="build", attempt+1)
                       attempt ≥ MAX_EVAL_ATTEMPTS (cap)   → Command(goto="review")
  review           — interrupt() gate; merge_worktree called ONLY in approve branch
                     (第3条).

第2条: nodes return dicts / Commands with path/ID fields only — no body content in state.
第3条: merge_worktree lives exclusively in the approve branch, after interrupt().
第6条: BUILDER_SYS (via agents.definitions.build_options) comes from
       .claude/agents/builder.md — not reinvented here.
第7条: eval_node enforces the evaluation gate — eval_score < THRESHOLD routes to build.
第8条: eval_node calls record_run() for EVERY eval (total_cost_usd + tokens always written).
第10条: eval_node calls eval_suite which imports scan_code (CWE/OWASP, S-#1 resolved).

Phase 2 additions:
  _invoke_builder — async injectable seam wrapping claude_agent_sdk.query().
                    Monkeypatch in unit tests to avoid real API calls.

Phase 3 additions:
  assemble_prompt  — pure function: constitution digest block (HEAD) → slice IDs
                     block (BODY). HEAD is identical for same digest → FR-2.2.
  assemble_context — LangGraph node that populates context_slice_ids.

Phase 4 additions (T4.3):
  _invoke_specialist — async injectable seam for specialist agent calls.
                       Stub mode: returns [] (no API call).
                       Monkeypatch in tests: monkeypatch.setattr(nodes_module,
                       "_invoke_specialist", async_mock).
  verify           — runs 4 specialists in parallel (asyncio.gather), merges
                     findings via reduce_findings reducer (FR-3.2, FR-3.3).
  S1 resolved      — build() now returns {"verify_findings": None} to trigger
                     reduce_findings reset, replacing the Phase 1–3 placeholder
                     of [] which was a no-op with operator.add.

Phase 5 additions:
  S-3 (historical) — _invoke_specialist once had a stub real mode that raised
                     NotImplementedError.  post-v14 wiring replaced it: real mode
                     (SDD_RUN_REAL_VERIFY=1) now runs the specialist via the Agent
                     SDK, parses 'FINDING:' lines, records cost, isolates errors,
                     and attaches make_hooks() (第5条).  Tests monkeypatch the seam.

Phase 6 additions (T6.2 — this phase):
  eval_node        — Calls harness.eval_suite.evaluate() for regression detection
                     and scoring.  Returns a LangGraph Command for routing:
                       attempt ≥ MAX_EVAL_ATTEMPTS → "review" (attempt cap, NFR-4)
                       regressed or score < THRESHOLD → "build" (retry, 第7条)
                       otherwise → "review" (pass)
                     Calls harness.observability.record_run() for every eval run
                     (FR-4.2 / 第8条).  In stub/offline mode, records zeros.
  Phase 4 Deferral 1 resolved:
                     verify is now wired into build_graph.py main topology:
                     spec_load → assemble_context → build → verify → eval → review.
                     (historical) real Agent SDK calls were deferred past Phase 6;
                     they are now wired (see the post-v14 real-mode note above).
                     Default (env gate unset) remains the offline stub — safe.

Graph wiring note (Phase 6):
  Full topology:  spec_load → assemble_context → build → verify → eval → review
  eval uses Command-based routing (no conditional edge in build_graph.py).
  review still uses Command for approve/reject (unchanged from Phase 1).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
from pathlib import Path

from langgraph.graph import END
from langgraph.types import Command, interrupt

from claude_agent_sdk import ClaudeAgentOptions, query

from graph.state import TaskState
from harness.sandbox import _slug, carve_worktree, merge_worktree

# Phase 6 imports: eval_suite + observability
from harness.eval_suite import (
    EVAL_SCORE_THRESHOLD,
    MAX_EVAL_ATTEMPTS,
    evaluate as _eval_suite_evaluate,
)
from harness.observability import (
    MAX_TURNS,
    record_agent_call,
    record_run,
    sum_agent_costs,
)

# ---------------------------------------------------------------------------
# Phase 3 context constants
# ---------------------------------------------------------------------------

_CONTEXT_DEFAULT_K = 5          # default number of spec slices to retrieve
_IMMUTABLE_HEADER = "[IMMUTABLE BLOCK]"
_SLICES_HEADER = "[TASK-SPECIFIC SLICES]"

# ---------------------------------------------------------------------------
# Real Agent SDK wiring — pure helpers (post-v14 / .steering real-agent-sdk)
#
# These are side-effect-free and independently unit-tested.  The SDK-touching
# code (query) is isolated in _run_query so the pure helpers never need the
# network or an API key.  Messages are handled by DUCK TYPING (a result message
# has .total_cost_usd; a content message has .content) rather than isinstance,
# so tests can pass simple fakes and the code is resilient to SDK version drift.
# ---------------------------------------------------------------------------

_FINDING_PREFIX = "FINDING:"


def _parse_findings(text: str, role: str) -> list[str]:
    """Extract 'FINDING:'-prefixed lines from agent text → ['[role] body', ...].

    Lines not starting with FINDING: are ignored.  Returns [] when the agent
    reported no findings (clean artifact), which is the desired signal for the
    verify/eval gate — an empty list means "nothing to flag".
    """
    findings: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith(_FINDING_PREFIX):
            body = stripped[len(_FINDING_PREFIX):].strip()
            if body:
                findings.append(f"[{role}] {body}")
    return findings


def _extract_cost(result_msg) -> tuple[float, dict[str, int]]:
    """Pull (total_cost_usd, {'input':N,'output':M}) from a ResultMessage.

    Tolerates usage being a dict OR an object, and missing fields → 0.
    """
    cost = float(getattr(result_msg, "total_cost_usd", 0.0) or 0.0)
    usage = getattr(result_msg, "usage", None)

    def _get(u, key):
        if u is None:
            return 0
        if isinstance(u, dict):
            val = u.get(key, 0)
        else:
            val = getattr(u, key, 0)
        try:
            return int(val or 0)
        except (TypeError, ValueError):
            return 0

    tokens = {
        "input": _get(usage, "input_tokens") or _get(usage, "input"),
        "output": _get(usage, "output_tokens") or _get(usage, "output"),
    }
    return cost, tokens


def _resolve_artifact(cwd: str) -> str:
    """Resolve the build artifact path for `cwd`.

    Prefers a builder-declared manifest at `{cwd}/.sdd/artifact_manifest.json`
    ({"primary_artifact": "<relative or absolute path>"}); falls back to
    `{cwd}/artifact.txt` when no manifest exists (Phase 1/2 compatible).
    """
    manifest = Path(cwd) / ".sdd" / "artifact_manifest.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            primary = data.get("primary_artifact")
            if primary:
                p = Path(primary)
                if not p.is_absolute():
                    p = Path(cwd) / p
                return str(p)
        except (json.JSONDecodeError, OSError, TypeError):
            pass  # fall back to the default artifact
    return str(Path(cwd) / "artifact.txt")


async def _run_query(prompt: str, options) -> tuple[str, object | None]:
    """Thin, mockable seam around the SDK `query()`.

    Runs the query, concatenates assistant text, and captures the final
    ResultMessage.  Returns (text, result_msg_or_None).  Tests monkeypatch this
    function so no network/API key is needed; the real body is exercised only
    by the opt-in smoke script and real runs.
    """
    text_parts: list[str] = []
    result_msg = None
    async for msg in query(prompt=prompt, options=options):
        if hasattr(msg, "total_cost_usd"):
            result_msg = msg
            # ResultMessage may also carry the final text in .result
            if getattr(msg, "result", None):
                text_parts.append(str(msg.result))
        elif hasattr(msg, "content"):
            for block in (msg.content or []):
                block_text = getattr(block, "text", None)
                if block_text:
                    text_parts.append(str(block_text))
    return "\n".join(text_parts), result_msg


# ---------------------------------------------------------------------------
# Phase 3: assemble_prompt (pure function) + assemble_context (graph node)
# ---------------------------------------------------------------------------

def assemble_prompt(constitution_digest: str, slice_ids: list[str]) -> str:
    """
    Build the injection prompt string from a constitution digest and slice IDs.

    Layout (FR-2.2 prompt-cache hit condition):
        [IMMUTABLE BLOCK]
        constitution_digest: <digest>

        [TASK-SPECIFIC SLICES]
        - <slice_id_0>
        - <slice_id_1>
        ...

    The HEAD block (everything up to and including the blank line after the
    digest) is IDENTICAL for the same constitution_digest across all calls,
    regardless of the slice IDs.  This is the fixed prefix required for
    prompt caching (Anthropic's cache-control semantics: the longest identical
    prefix hit is cached).

    第2条: slice_ids are ID strings — no body text is embedded here.

    Args:
        constitution_digest: Short hash string from spec_load (e.g. "sha256:abc123ef")
        slice_ids:           Ordered list of chunk IDs from retrieve_slice_ids().

    Returns:
        Prompt string with immutable head block followed by slice IDs.
    """
    head = f"{_IMMUTABLE_HEADER}\nconstitution_digest: {constitution_digest}\n"
    if not slice_ids:
        body = f"\n{_SLICES_HEADER}\n(no slices selected)"
    else:
        lines = "\n".join(f"- {sid}" for sid in slice_ids)
        body = f"\n{_SLICES_HEADER}\n{lines}"
    return head + body


def assemble_context(state: TaskState) -> dict:
    """
    Phase 3 context-assembly node.

    Retrieves the top-k spec chunks most relevant to the current task and
    stores their IDs in TaskState.context_slice_ids.

    第2条: only chunk IDs are stored in state — never body text.
    FR-2.1: returned count is always < total chunk count (enforced by
            retrieve_slice_ids via k_actual = min(k, total-1)).
    FR-2.2: same (task_id, constitution_digest) pair always yields the same
            context_slice_ids ordering, because LocalHashEmbedding is
            deterministic and results are sorted by (distance, id).

    The injection order for downstream prompt construction is:
        assemble_prompt(constitution_digest, context_slice_ids)
    which puts the immutable constitution block first (cache-hit head).

    Graph wiring: spec_load → assemble_context → build
    (assemble_context runs after spec_load so constitution_digest is available)
    """
    # Late import to avoid circular imports during module load.
    # context_server is a peer module; importing at call-time also allows
    # tests to monkeypatch SDD_DOCS_DIR before the collection is built.
    from mcp_servers.context_server import retrieve_slice_ids

    task_id: str = state["task_id"]
    docs_dir: str | None = os.environ.get("SDD_DOCS_DIR")

    ids = retrieve_slice_ids(
        query=task_id,
        k=_CONTEXT_DEFAULT_K,
        docs_dir=docs_dir,  # None → context_server falls back to env/default
    )

    # 第2条: return IDs only — no body content in state
    return {"context_slice_ids": ids}


# ---------------------------------------------------------------------------
# spec_load
# ---------------------------------------------------------------------------

def spec_load(state: TaskState) -> dict:
    """
    Load spec metadata and carve git worktree.

    Sets: spec_path (validated), constitution_digest, worktree_path.
    Does NOT load file bodies into state (第2条).
    Idempotent: if worktree_path already set and exists, skip re-carving.
    """
    spec_path = state["spec_path"]

    # Validate spec exists
    if not Path(spec_path).exists():
        raise FileNotFoundError(f"spec_path not found: {spec_path!r}")

    # Compute constitution digest (short — not full text in state, 第2条)
    # Resolution order: env override → project constitution (docs/, created by
    # /init-task) → distributable default (specs/, shipped with the toolkit).
    constitution_path = os.environ.get("SDD_CONSTITUTION_PATH")
    if not constitution_path:
        constitution_path = (
            "docs/constitution.md"
            if Path("docs/constitution.md").exists()
            else "specs/constitution.md"
        )
    constitution_bytes = Path(constitution_path).read_bytes()
    digest = "sha256:" + hashlib.sha256(constitution_bytes).hexdigest()[:16]

    # Idempotency guard: if worktree already carved and path still exists, reuse
    existing_wt = state.get("worktree_path", "")
    if existing_wt and Path(existing_wt).exists():
        return {
            "spec_path": spec_path,
            "constitution_digest": digest,
            "worktree_path": existing_wt,
        }

    # Carve a fresh git worktree for this task
    base_repo = os.environ.get("SDD_BASE_REPO", ".")
    worktree_path = carve_worktree(state["task_id"], base_repo=base_repo)

    return {
        "spec_path": spec_path,
        "constitution_digest": digest,
        "worktree_path": worktree_path,
    }


# ---------------------------------------------------------------------------
# Builder injectable seam (Phase 2)
# ---------------------------------------------------------------------------

def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    if "GIT_AUTHOR_NAME" not in env:
        env["GIT_AUTHOR_NAME"] = "sdd-build"
        env["GIT_AUTHOR_EMAIL"] = "sdd@localhost"
        env["GIT_COMMITTER_NAME"] = "sdd-build"
        env["GIT_COMMITTER_EMAIL"] = "sdd@localhost"
    return env


async def _invoke_builder(
    prompt: str,
    options: ClaudeAgentOptions,
    cwd: str,
) -> str:
    """
    Injectable seam: calls the Claude Agent SDK Builder.

    Mode selection (controlled by SDD_RUN_REAL_BUILDER environment variable):

      SDD_RUN_REAL_BUILDER=1  →  real Agent SDK call via claude_agent_sdk.query().
                                  The builder agent writes files to cwd.

      default (env var absent) →  stub mode: backward-compatible with Phase 1 tests.
                                  Writes the prompt's first line as artifact.txt content
                                  and commits in the worktree. No API key required.

    To isolate unit tests from both the API and git side-effects, monkeypatch this
    module-level function before calling build():

        monkeypatch.setattr(nodes_module, "_invoke_builder", my_async_mock)

    Invariants:
      第2条: returns an absolute path string (never body content).
      FR-3.1: cwd is expected to be worktree_path (caller's responsibility).
      第6条: options.agents["builder"] carries BUILDER_SYS from builder.md.
    """
    if not os.environ.get("SDD_RUN_REAL_BUILDER"):
        # --- Stub mode (default) ---
        # Backward-compatible: build() sets the prompt's first line to
        # "STUB artifact for {task_id}, attempt {attempt}" so that Phase 1
        # TestBuild assertions (which check artifact.txt content) still pass.
        artifact = Path(cwd) / "artifact.txt"
        artifact.write_text(prompt.split("\n")[0])
        env = _git_env()
        subprocess.run(
            ["git", "-C", cwd, "add", "artifact.txt"],
            check=True,
            capture_output=True,
            env=env,
        )
        subprocess.run(
            ["git", "-C", cwd, "commit", "-m", "build: stub artifact"],
            check=True,
            capture_output=True,
            env=env,
        )
        return str(artifact)

    # --- Real mode (SDD_RUN_REAL_BUILDER=1) ---
    # Run the Agent SDK query; the builder agent writes artifacts to cwd.
    # The builder's file writes are the side-effect; we capture cost/tokens.
    _text, result_msg = await _run_query(prompt=prompt, options=options)
    if result_msg is not None:
        cost, tokens = _extract_cost(result_msg)
        # run_id = worktree dir name = _slug(task_id); eval_node sums by slug too.
        record_agent_call(
            run_id=Path(cwd).name,
            role="builder",
            total_cost_usd=cost,
            tokens=tokens,
            num_turns=getattr(result_msg, "num_turns", None),
        )

    # Artifact path: builder-declared manifest → primary_artifact, else artifact.txt.
    return _resolve_artifact(cwd)


# ---------------------------------------------------------------------------
# build (Phase 2: real _invoke_builder call replacing Phase 1 stub)
# ---------------------------------------------------------------------------

def build(state: TaskState) -> dict:
    """
    Build node: invokes the Builder agent inside the git worktree.

    Calls _invoke_builder (injectable seam) with:
      prompt  — structured task description; first line = Phase 1-compatible
                stub content for backward-compatibility.
      options — ClaudeAgentOptions(cwd=worktree_path, agents={...}, ...)
      cwd     — worktree_path (FR-3.1: never the host working tree)

    The seam is mockable for unit tests:
        monkeypatch.setattr(nodes_module, "_invoke_builder", async_mock)

    FR-3.1: Builder executes with cwd=worktree_path — host working tree is NEVER
            modified by the builder (worktree is a sibling, not inside the repo).
    第2条: sets build_artifact_ref to a path only — no body content in state.
    第6条: build_options() loads BUILDER_SYS from .claude/agents/builder.md.

    Phase 4 S1 resolved: returns {"verify_findings": None} to signal the
    reduce_findings reducer to reset findings to [] for this new round.
    Each reject→rebuild cycle begins with a clean findings list.
    """
    worktree_path = state["worktree_path"]
    task_id = state["task_id"]
    attempt = state["attempt"]

    # Late import avoids circular imports during Phase 3 MCP wiring
    from agents.definitions import build_options

    options = build_options(worktree_path=worktree_path)

    # First line = Phase 1-compatible stub content (TestBuild assertions check this).
    # Remaining lines = real task description used by the Agent SDK builder.
    prompt = (
        f"STUB artifact for {task_id}, attempt {attempt}\n"
        f"Build task: {task_id} (attempt {attempt}).\n"
        f"Spec file: {state['spec_path']}\n"
        f"Constitution digest: {state['constitution_digest']}\n"
    )

    # Call builder through injectable seam.
    # In tests: monkeypatch _invoke_builder before calling build().
    # In production: _invoke_builder calls the real Agent SDK.
    # Default (stub mode): _invoke_builder writes artifact.txt in cwd and commits.
    artifact_ref = asyncio.run(_invoke_builder(prompt, options, worktree_path))

    # S1 resolved (Phase 4): return None to signal "round reset" to the
    # reduce_findings reducer in graph/state.py.  reduce_findings(old, None)
    # returns [] regardless of what old holds, clearing stale findings from
    # any previous reject→rebuild round.  The old [] placeholder was a no-op
    # with operator.add and caused findings to accumulate across rounds.
    return {
        "build_artifact_ref": artifact_ref,
        "verify_findings": None,  # reduce_findings(old, None) → [] (round reset)
    }


# ---------------------------------------------------------------------------
# review
# ---------------------------------------------------------------------------

def review(state: TaskState) -> Command:
    """
    Human-in-the-loop approval gate using LangGraph interrupt().

    Pause execution and surface diff + findings to the reviewer.
    On resume:
      - approve → merge_worktree (ONLY side-effect point, 第3条) → END
      - reject  → increment attempt, loop back to build (no merge)

    第3条 enforcement: merge_worktree appears ONLY inside the approve branch,
    which is only reachable after interrupt() returns — never before.
    """
    decision = interrupt(
        {
            "kind": "merge_approval",
            "diff_ref": state["build_artifact_ref"],
            "findings": state["verify_findings"],
            "eval_score": state["eval_score"],
        }
    )

    if decision["action"] == "approve":
        # 第3条: irreversible side-effect only after human approval
        base_repo = os.environ.get("SDD_BASE_REPO", ".")
        merge_worktree(state["worktree_path"], base_repo=base_repo)
        return Command(goto=END, update={"decision": "approved"})

    # reject: loop back to build with attempt counter incremented
    return Command(
        goto="build",
        update={
            "decision": "rejected",
            "attempt": state["attempt"] + 1,
        },
    )


# ---------------------------------------------------------------------------
# Phase 4 (T4.3): verify — parallel specialist execution
# ---------------------------------------------------------------------------

async def _invoke_specialist(
    specialist_name: str,
    artifact_ref: str,
    task_id: str,
    worktree_path: str = "",
) -> list[str]:
    """
    Injectable seam: invokes a named specialist sub-agent and returns findings.

    Mode selection (controlled by SDD_RUN_REAL_VERIFY environment variable):

      SDD_RUN_REAL_VERIFY=1  →  REAL mode (post-v14 wiring): runs the specialist
                                 via the Agent SDK inside the worktree, parses
                                 'FINDING:' lines into findings, and records the
                                 call's cost/tokens (FR-4.2).  A specialist that
                                 errors returns a single '[role] ERROR: …' finding
                                 so one failure never loses the other specialists'
                                 findings (asyncio.gather isolation).

      default (env var absent) →  stub mode: returns [] immediately, no API call.

    To isolate unit tests from both the API and network, monkeypatch this
    module-level function OR the smaller _run_query seam:

        monkeypatch.setattr(nodes_module, "_invoke_specialist", my_async_mock)
        monkeypatch.setattr(nodes_module, "_run_query", my_async_query)

    FR-3.3: specialist tool sets come from agents.definitions.SPECIALIST_TOOLS
             and do NOT include the Task tool — no recursive sub-agent spawning.
    第4条: the specialist runs with cwd = the worktree (parent of artifact_ref).
    第2条: findings are short strings; cost/tokens go to the observation store.

    Args:
        specialist_name: One of "validator", "tester", "reviewer", "security".
        artifact_ref:    Path reference to the build artifact (第2条: path only).
        task_id:         Current task identifier for context.

    Returns:
        List of finding strings (each prefixed "[role] ").
    """
    if not os.environ.get("SDD_RUN_REAL_VERIFY"):
        # Stub mode: no API call.
        return []

    # --- Real mode (SDD_RUN_REAL_VERIFY=1) ---
    from agents.definitions import SPECIALIST_TOOLS
    from harness.hooks import make_hooks

    tools = SPECIALIST_TOOLS.get(specialist_name, ["Read"])  # FR-3.3: no Task
    # cwd = the worktree ROOT (第4条: run inside the worktree). F-6: prefer the
    # explicit worktree_path; fall back to the artifact's parent only when it is
    # absent (an artifact may live in a subdirectory, so its parent ≠ root).
    cwd = worktree_path or (
        str(Path(artifact_ref).parent) if artifact_ref else "."
    )

    concern = _SPECIALIST_CONCERN.get(
        specialist_name, "quality issues in the artifact"
    )
    system_prompt = (
        f"You are the {specialist_name} reviewer in an SDD verify step. "
        f"Inspect the build artifact and surrounding files in the working "
        f"directory for {concern}. Use only your read-only tools. "
        f"Output one line per issue, each starting with 'FINDING:' followed by a "
        f"concise description. If you find no issues, output nothing."
    )
    prompt = (
        f"Review the artifact for task '{task_id}'. "
        f"Primary artifact: {artifact_ref}. "
        f"Report issues as 'FINDING:' lines per your instructions."
    )
    # F-1 (第5条): attach the PreToolUse guard (make_hooks) to EVERY real agent
    # invocation.  We do NOT force permission_mode to a bypass value (left at the
    # SDK default) — the SAFE_READONLY_TOOLS auto-approval inside make_hooks()
    # prevents approval flooding (plan §7 intent) without disabling permissions.
    options = ClaudeAgentOptions(
        cwd=cwd,
        allowed_tools=tools,
        system_prompt=system_prompt,
        max_turns=MAX_TURNS,
        hooks=make_hooks(),
    )

    try:
        text, result_msg = await _run_query(prompt=prompt, options=options)
        if result_msg is not None:
            cost, tokens = _extract_cost(result_msg)
            record_agent_call(
                run_id=task_id,
                role=specialist_name,
                total_cost_usd=cost,
                tokens=tokens,
                num_turns=getattr(result_msg, "num_turns", None),
            )
        return _parse_findings(text, specialist_name)
    except Exception as exc:  # noqa: BLE001 — isolate one specialist's failure
        # Do not let one specialist's error drop the others (FR-3.2 robustness).
        return [f"[{specialist_name}] ERROR: {exc}"]


# CWE/quality concern each specialist focuses on (used in the real-mode prompt).
_SPECIALIST_CONCERN: dict[str, str] = {
    "validator": "spec/acceptance-criteria mismatches and missing deliverables",
    "tester": "missing tests and untested error paths (read-only inspection; "
    "test execution is deferred to a future podman-backed tool — F-2)",
    "reviewer": "design, module boundaries, and maintainability problems",
    "security": "security vulnerabilities (injection, secrets, unsafe deserialization)",
}


async def _run_verify_parallel(state: TaskState) -> list[str]:
    """
    Run all 4 specialist sub-agents in parallel via asyncio.gather.

    FR-3.2: findings from each specialist are collected without overwriting.
    All 4 agents start concurrently; their results are concatenated afterward.

    Returns:
        Merged list of findings from all specialists (no duplicates removed —
        each specialist's contribution is preserved as-is).
    """
    artifact_ref = state.get("build_artifact_ref", "")
    task_id = state.get("task_id", "")
    worktree_path = state.get("worktree_path", "")  # F-6: cwd = worktree root

    # Run all specialists concurrently (FR-3.2: parallel, not sequential)
    results = await asyncio.gather(
        _invoke_specialist("validator", artifact_ref, task_id, worktree_path),
        _invoke_specialist("tester", artifact_ref, task_id, worktree_path),
        _invoke_specialist("reviewer", artifact_ref, task_id, worktree_path),
        _invoke_specialist("security", artifact_ref, task_id, worktree_path),
    )

    # Merge without overwrite: extend accumulates all findings (FR-3.2)
    merged: list[str] = []
    for specialist_findings in results:
        merged.extend(specialist_findings)
    return merged


def verify(state: TaskState) -> dict:
    """
    Phase 4 verify node: run 4 specialists in parallel, merge findings.

    Specialists:  Validator, Tester, Reviewer, Security (FR-3.2)
    Parallelism:  asyncio.gather via _run_verify_parallel (concurrent, not sequential)
    Reducer:      reduce_findings — appends to state (no overwrite, FR-3.2)
    No Task tool: specialists defined in agents.definitions.SPECIALIST_TOOLS (FR-3.3)

    Injectable seam for tests:
        monkeypatch.setattr(nodes_module, "_invoke_specialist", async_mock)

    Returns a dict with verify_findings set to the merged list.  The
    reduce_findings reducer in TaskState appends this to the current value
    (which is [] after build resets).  In a reject→rebuild cycle:
      build returns None  → reduce_findings(old, None) = []   (reset)
      verify returns [...]→ reduce_findings([], [...]) = [...] (fresh findings)

    Phase 6 note (Deferral 1 resolved):
      verify is now wired into build_graph.py main topology.
      _invoke_specialist stub mode (no SDD_RUN_REAL_VERIFY) still returns [].
      Real Agent SDK calls are wired (post-v14): SDD_RUN_REAL_VERIFY=1 runs the
      4 specialists via the SDK under make_hooks() (第5条); default is the stub.
    """
    findings = asyncio.run(_run_verify_parallel(state))
    return {"verify_findings": findings}


# ---------------------------------------------------------------------------
# Phase 6 (T6.2): eval_node — regression detection + conditional routing
# ---------------------------------------------------------------------------

def eval_node(state: TaskState) -> Command:
    """
    Phase 6 eval node: score artifact, detect regression, route conditionally.

    Implements:
      第7条: evaluation gate — eval_score < THRESHOLD → retry (goto="build")
      第8条: record_run() always writes cost/token record (FR-4.2)
      第10条: eval_suite.evaluate() calls scan_code internally (S-#1 resolved)
      NFR-4: attempt cap at MAX_EVAL_ATTEMPTS → force goto="review"

    Routing (via Command — no separate conditional edge in build_graph.py):

      1. attempt ≥ MAX_EVAL_ATTEMPTS (cap)
         → Command(goto="review", update={"eval_score": score})
         Prevents infinite retry loops (NFR-4).

      2. regressed OR eval_score < EVAL_SCORE_THRESHOLD (fail)
         → Command(goto="build", update={"eval_score": 0.0, "attempt": attempt+1})
         eval_score set to 0.0 so review sees a clear failure signal.
         attempt incremented to track retry count toward the cap.

      3. eval_score ≥ EVAL_SCORE_THRESHOLD AND NOT regressed (pass)
         → Command(goto="review", update={"eval_score": score})
         Artifact cleared the evaluation gate.

    Observability (FR-4.2 / 第8条):
      record_run() is called for EVERY eval run.  In stub/offline mode,
      total_cost_usd=0.0 and tokens={"input":0,"output":0} are placeholders;
      the structural guarantee (record exists per run) satisfies FR-4.2.

    Injectable seam for tests:
      Monkeypatch harness.eval_suite.evaluate at the module level:
        monkeypatch.setattr("harness.eval_suite.evaluate", mock_evaluate)
      Or patch _eval_suite_evaluate in this module:
        monkeypatch.setattr(nodes_module, "_eval_suite_evaluate", mock_fn)
    """
    findings: list[str] = state.get("verify_findings") or []
    attempt: int = state.get("attempt", 0)

    # ── Evaluate artifact (第7条 / 第10条) ────────────────────────────────
    result = _eval_suite_evaluate(state_or_artifact=state, findings=findings)
    raw_score: float = result["eval_score"]
    regressed: bool = result["regressed"]

    # If regressed, override score to 0.0 so review sees a clear failure signal
    # and the route_after_eval logic is consistent (score < THRESHOLD → build).
    eval_score: float = 0.0 if regressed else raw_score

    # ── Observability (FR-4.2 / 第8条) ────────────────────────────────────
    # Always write a record.  Cost/tokens are the SUM of this run's real
    # agent_call rows (builder + specialists).  In stub/offline mode no
    # agent_call rows exist → totals are 0.0 (backward-compatible with tests).
    # SDD_OBS_STORE env var can redirect to a temp path in tests.
    task_id = state.get("task_id", "unknown")
    run_cost, run_tokens = sum_agent_costs(task_id)
    slug = _slug(task_id)
    if slug != task_id:  # builder rows are keyed by the worktree slug
        slug_cost, slug_tokens = sum_agent_costs(slug)
        run_cost += slug_cost
        for k, v in slug_tokens.items():
            run_tokens[k] = run_tokens.get(k, 0) + v
    record_run(
        run_id=task_id,
        attempt=attempt,
        total_cost_usd=run_cost,     # real sum of agent_call rows (0.0 in stub mode)
        tokens=run_tokens,           # summed input/output tokens (FR-4.2)
        eval_score=eval_score,
        raw_eval_score=raw_score,
        regressed=regressed,
        security_findings_count=len(result["security_findings"]),
        verify_findings_count=len(findings),
    )

    # ── Routing (第7条 / NFR-4 attempt cap) ───────────────────────────────
    if attempt >= MAX_EVAL_ATTEMPTS:
        # Attempt cap: too many retries → force to review (NFR-4).
        # Human reviewer sees eval_score and can approve or reject.
        return Command(
            goto="review",
            update={"eval_score": eval_score},
        )

    if eval_score < EVAL_SCORE_THRESHOLD:
        # Fail: retry build with incremented attempt counter.
        # attempt+1 counts toward MAX_EVAL_ATTEMPTS cap.
        return Command(
            goto="build",
            update={
                "eval_score": eval_score,
                "attempt": attempt + 1,
            },
        )

    # Pass: artifact cleared the evaluation gate (第7条).
    return Command(
        goto="review",
        update={"eval_score": eval_score},
    )
