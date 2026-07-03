"""
agents/definitions.py — Claude Agent SDK options for sdd_toolkit_v14.

Tool permission policy (plan §6 vs approved design reconciliation):
  Plan §6 says "Write/Edit は外す (remove from specialists)" — that phrase applies
  to the specialist agents (reviewer/security/tester/validator), NOT the builder.
  The builder MUST have Write/Edit to generate code artifacts. Approved design:
    - builder:   Read, Write, Edit, Bash, Grep — full write access to create/modify files
    - reviewer:  Read, Grep               — read-only analysis; no Task (FR-3.3)
    - security:  Read, Grep               — read-only audit;    no Task (FR-3.3)
    - tester:    Read, Bash               — read + run tests;   no Task (FR-3.3)
    - validator: Read, Grep               — read-only validation; no Task (FR-3.3)
                                            Phase 5 S-1: added to complete verify's 4 specialists
  FR-3.3: specialists MUST NOT have Task — Task would allow recursive sub-agent spawning
          that cannot be bounded, causing runaway loops.

第6条: BUILDER_SYS is loaded from .claude/agents/builder.md at import time.
       Do not invent a new builder philosophy — reuse the v12/v13 asset.

Phase 5 S-1 resolution:
  validator was missing from SPECIALIST_TOOLS and build_options(), causing
  _invoke_specialist("validator", ...) in verify() to fail at definition lookup.
  Added here: validator has Read + Grep (read-only, no Task per FR-3.3).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import AgentDefinition


# ---------------------------------------------------------------------------
# 第6条: Load builder system prompt from .claude/agents/builder.md
# ---------------------------------------------------------------------------

_BUILDER_MD = Path(__file__).parent.parent / ".claude" / "agents" / "builder.md"
BUILDER_SYS: str = _BUILDER_MD.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tool sets (canonical constants)
# ---------------------------------------------------------------------------

# Builder: full write access — it generates and edits code artifacts (approved design §1)
BUILDER_TOOLS: list[str] = ["Read", "Write", "Edit", "Bash", "Grep"]

# Specialists: read-only / limited. Task is NOT included anywhere (FR-3.3).
# Plan §6 "Write/Edit は外す" applies HERE — specialists cannot modify files.
# Phase 5 S-1: added "validator" (Read, Grep) — completes the 4 verify specialists.
#
# F-2 (第4/5条, defense-boundary fix 2026-07-03): tester's "Bash" was REMOVED.
#   Rationale: a real-mode tester with Bash could execute host commands without
#   passing the podman hard boundary (第5条 requires BOTH soft hooks AND the
#   podman sandbox; Bash here only had the soft hook, not the sandbox).  案A
#   (minimal & safe): tester is read-only (Read+Grep) — it can inspect for test
#   presence/coverage but does not run code.  Real test EXECUTION will be
#   re-introduced as a dedicated tool that calls harness.sandbox.run_in_sandbox
#   (podman; no host fallback — NFR-3), in the phase that needs it (案B).
SPECIALIST_TOOLS: dict[str, list[str]] = {
    "reviewer":  ["Read", "Grep"],
    "security":  ["Read", "Grep"],
    "tester":    ["Read", "Grep"],   # base read-only tools; test EXECUTION is the
                                     # sandbox MCP tool below (not host Bash)
    "validator": ["Read", "Grep"],   # S-1 Phase 5: validator reads artifacts only
}

# Isolation loop: specialists that get a podman-backed MCP tool for real code
# execution (the built-but-formerly-unwired harness.sandbox.run_in_sandbox).  The
# tester runs the suite via mcp__sandbox__run_tests — inside podman (第4/5条 hard
# boundary), never host Bash.  graph.nodes._invoke_specialist attaches the server
# and extends BOTH allowed_tools and the F-7 hook allow-list with this tool name.
SPECIALIST_SANDBOX_TOOL: dict[str, str] = {
    "tester": "mcp__sandbox__run_tests",
}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def build_options(
    worktree_path: str | None = None,
    mcp_servers: dict | None = None,
    hooks: dict | None = None,
) -> ClaudeAgentOptions:
    """
    Build ClaudeAgentOptions for the sdd_toolkit_v14 agent team.

    Args:
        worktree_path: Builder's working directory.  FR-3.1 requires the builder to
                       run inside the git worktree (not the host working tree).
                       Passed as `cwd` to ClaudeAgentOptions.
        mcp_servers:   MCP server configs.  Placeholder — wired in Phase 3
                       (context_server) and Phase 5 (constitution_server).
                       Pass None to omit (uses SDK default empty dict).
        hooks:         Hook matchers for PreToolUse etc.  F-3: ALWAYS applied —
                       when None, defaults to harness.hooks.make_hooks() (第5条
                       soft boundary).  The PreToolUse hook blocks dangerous ops
                       and auto-approves safe read-only tools (Read, Grep) to
                       avoid approval flooding.  Pass an explicit dict to override;
                       there is no way to run the builder with hooks disabled.

    Returns:
        ClaudeAgentOptions with:
          - agents   = {builder, reviewer, security, tester, validator}
          - allowed_tools = BUILDER_TOOLS (governs the main / builder agent)
          - cwd      = worktree_path (if provided)

    Tool reconciliation note (plan §6 ambiguity):
        Plan §6 mentions "Write/Edit は外す" in the context of specialist agents.
        The builder agent MUST retain Write/Edit to produce code artifacts.
        Specialists (reviewer/security/tester/validator) have restricted tool
        lists with no Task tool — FR-3.3 prevents recursive sub-agent spawning.

    Phase 5 S-1 note:
        validator AgentDefinition added to bring verify's 4 specialists
        (validator/tester/reviewer/security) to completion.
    """
    agents: dict[str, AgentDefinition] = {
        # ---- builder ---------------------------------------------------------
        # Has Write/Edit — it generates code files inside the worktree.
        # System prompt loaded from .claude/agents/builder.md (第6条 reuse).
        "builder": AgentDefinition(
            description=(
                "Generates code artifacts inside the worktree following SKILL.md "
                "procedures. Has Write/Edit access to create and modify files. "
                "Does not self-judge quality; hands off to Validator."
            ),
            prompt=BUILDER_SYS,
            tools=BUILDER_TOOLS,
            # No disallowedTools needed: explicit allow list above is authoritative.
        ),

        # ---- reviewer --------------------------------------------------------
        # Read-only. No Task (FR-3.3). No Write/Edit (plan §6 specialist rule).
        "reviewer": AgentDefinition(
            description=(
                "Reviews build artifacts for correctness and spec compliance. "
                "Read-only: no Write, Edit, or Task (FR-3.3)."
            ),
            prompt=(
                "You are a code reviewer for sdd_toolkit_v14. "
                "Analyze build artifacts for correctness, quality, and spec compliance. "
                "Report findings as a structured list with location, problem, and severity. "
                "Do NOT modify any files."
            ),
            tools=SPECIALIST_TOOLS["reviewer"],
            # Task is not in tools list → FR-3.3 satisfied (no recursive spawning)
        ),

        # ---- security --------------------------------------------------------
        # Read-only. No Task (FR-3.3). No Write/Edit (plan §6 specialist rule).
        "security": AgentDefinition(
            description=(
                "Performs security audit on build artifacts. "
                "Read-only: no Write, Edit, or Task (FR-3.3)."
            ),
            prompt=(
                "You are a security auditor for sdd_toolkit_v14. "
                "Scan build artifacts for vulnerabilities, injection risks, "
                "insecure patterns, and policy violations. "
                "Report all findings with severity (Critical/High/Medium/Low). "
                "Do NOT modify any files."
            ),
            tools=SPECIALIST_TOOLS["security"],
        ),

        # ---- tester ----------------------------------------------------------
        # Read + Grep + the podman-backed run_tests MCP tool.  NO host Bash
        # (F-2/F-7): test EXECUTION goes through the sandbox (第4/5条), not the
        # host.  No Task (FR-3.3). No Write/Edit (plan §6 specialist rule).
        "tester": AgentDefinition(
            description=(
                "Inspects and runs tests on build artifacts. Read + Grep for "
                "static inspection; executes the suite via the sandboxed "
                "mcp__sandbox__run_tests tool (podman, no host Bash). "
                "No Write, Edit, or Task (FR-3.3)."
            ),
            prompt=(
                "You are the tester for sdd_toolkit_v14. Inspect tests statically "
                "and, when tests exist, EXECUTE them via the run_tests tool, which "
                "runs pytest inside a network-isolated podman sandbox. Report "
                "pass/fail with error details. If the sandbox is unavailable, say "
                "so — never assume tests pass. Do NOT write or modify files."
            ),
            tools=SPECIALIST_TOOLS["tester"],
        ),

        # ---- validator -------------------------------------------------------
        # Read + Grep only. No Task (FR-3.3). No Write/Edit (plan §6 specialist rule).
        # Phase 5 S-1: added to complete verify's 4 specialist set.
        # Validator reads artifacts and spec, reports findings — never modifies files.
        "validator": AgentDefinition(
            description=(
                "Validates build artifacts against spec acceptance criteria. "
                "Read-only: no Write, Edit, or Task (FR-3.3)."
            ),
            prompt=(
                "You are a validator for sdd_toolkit_v14. "
                "Check build artifacts against the spec acceptance criteria. "
                "Every issue must cite a specific requirement from docs/ or SKILL.md. "
                "Report findings with location, problem, required-by, and severity. "
                "Do NOT modify any files."
            ),
            tools=SPECIALIST_TOOLS["validator"],
        ),
    }

    kwargs: dict[str, Any] = {
        "agents": agents,
        # allowed_tools governs the main (builder) agent's tool access
        "allowed_tools": BUILDER_TOOLS,
    }

    # FR-3.1: set cwd to worktree_path so builder runs inside the worktree
    if worktree_path is not None:
        kwargs["cwd"] = worktree_path

    # Phase 3/5: MCP servers (context_server, constitution_server) wired here
    if mcp_servers is not None:
        kwargs["mcp_servers"] = mcp_servers

    # F-3 (第5条): the PreToolUse guard is ALWAYS applied.  When no hooks are
    # supplied we default to make_hooks() rather than leaving the builder
    # unguarded — a real-mode builder holds Write/Edit/Bash and must be bounded
    # by the same soft boundary as the specialists (there is deliberately no way
    # to run the builder with hooks disabled).
    if hooks is None:
        from harness.hooks import make_hooks

        # F-7: enforce the builder's allow-list (BUILDER_TOOLS) at the hook layer
        # too — the SDK's allowed_tools is advisory, not a hard whitelist.
        hooks = make_hooks(allowed_tools=BUILDER_TOOLS)
    kwargs["hooks"] = hooks

    return ClaudeAgentOptions(**kwargs)
