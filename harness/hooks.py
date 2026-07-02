"""
harness/hooks.py — Phase 4 (T4.1): Claude Agent SDK PreToolUse guard.

第5条 ソフト境界（Claude Agent SDK hooks）実装:
  - PreToolUse guard: 禁止操作（rm -rf / git push / .env 読取り等）を拒否。
  - 監査ログ: 全ツール呼び出しを JSONL 形式で追記（gitignore 済み）。
  - SubagentStop フック: スタブ（エージェント完了をログ、将来拡張用）。
  - 安全な読み取り専用ツールを自動承認（承認フラッディング回避、plan §7）。

Two-layer defense (第5条):
  Soft boundary (this file):  PreToolUse hook intercepts and blocks dangerous
                               tool calls BEFORE they reach the OS/filesystem.
  Hard boundary (sandbox.py): podman rootless + cgroups MemoryMax prevents
                               escape even if a soft-boundary bypass occurs.

Architecture:
  is_blocked(tool_name, tool_input)  — pure predicate, side-effect free.
                                       Fully unit-testable without the SDK.
  create_pre_tool_use_hook(log_path) — factory returning the async callback.
                                       Wires is_blocked + audit log together.
  make_hooks(audit_log_path)         — top-level API: returns the dict
                                       {HookEvent: [HookMatcher]} for
                                       ClaudeAgentOptions(hooks=...).
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from claude_agent_sdk import HookMatcher


# ---------------------------------------------------------------------------
# Audit log configuration (path gitignored via .gitignore entry)
# ---------------------------------------------------------------------------

_DEFAULT_AUDIT_LOG: str = os.environ.get(
    "SDD_AUDIT_LOG",
    str(Path(__file__).parent.parent / "logs" / "audit.jsonl"),
)


# ---------------------------------------------------------------------------
# Safe read-only tools — auto-approved to avoid approval flooding (plan §7)
# ---------------------------------------------------------------------------

#: Tools that are always read-only and safe to auto-approve.
#: Approval flooding occurs when every Read/Grep call triggers a prompt;
#: auto-approving these keeps the interactive review cycle focused on
#: genuinely dangerous operations.
SAFE_READONLY_TOOLS: frozenset[str] = frozenset({
    "Read",
    "Grep",
    "Glob",
    "LS",
})


# ---------------------------------------------------------------------------
# Deny-list patterns (第5条: ソフト境界)
# ---------------------------------------------------------------------------

# Bash command patterns that are unconditionally blocked.
# Using re.IGNORECASE to catch both rm and RM (edge cases in some shells).
_BLOCKED_BASH_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"\brm\b.*-[a-zA-Z]*[rR]", re.IGNORECASE),
        "rm with recursive flag blocked (第5条: destructive file removal)",
    ),
    (
        re.compile(r"\brm\b.*--recursive", re.IGNORECASE),
        "rm --recursive blocked (第5条: destructive file removal)",
    ),
    (
        re.compile(r"\bgit\s+push\b", re.IGNORECASE),
        "git push blocked (第5条: irreversible remote write — use review gate)",
    ),
]

# File path patterns for secret / credential files.
# Reading or writing these is blocked regardless of tool.
_BLOCKED_FILE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"(^|[/\\])\.env(\b|$|\.)"),
        ".env file access blocked (第5条: credential protection)",
    ),
    (
        re.compile(r"(^|[/\\])secrets?[/\\]", re.IGNORECASE),
        "secrets/ directory access blocked (第5条: credential protection)",
    ),
    (
        re.compile(r"\.(pem|key|p12|pfx|jks|crt|cer)$", re.IGNORECASE),
        "Private key/certificate file access blocked (第5条: credential protection)",
    ),
    (
        re.compile(r"(^|[/\\])credentials?\b", re.IGNORECASE),
        "credentials file access blocked (第5条: credential protection)",
    ),
]

# Tool names whose file_path/path argument is checked against _BLOCKED_FILE_PATTERNS.
_FILE_TOOLS: frozenset[str] = frozenset({"Read", "Write", "Edit", "MultiEdit"})


# ---------------------------------------------------------------------------
# Pure predicate — no side-effects, fully testable without SDK
# ---------------------------------------------------------------------------

def is_blocked(tool_name: str, tool_input: dict[str, Any]) -> tuple[bool, str]:
    """
    Pure predicate: returns (blocked: bool, reason: str).

    第5条 ソフト境界 enforcement logic:
      - Bash tool: check command against _BLOCKED_BASH_PATTERNS.
      - Read/Write/Edit/MultiEdit: check file_path against _BLOCKED_FILE_PATTERNS.
      - All other tools: allowed (False, "").

    This function has NO side-effects and can be tested independently of the SDK.

    Args:
        tool_name:  Claude tool name (e.g. "Bash", "Read", "Write", "Edit").
        tool_input: Tool input dict as provided by the SDK hook.

    Returns:
        (True, reason_string) if the call must be blocked.
        (False, "")           if the call is allowed.

    Examples:
        >>> is_blocked("Bash", {"command": "rm -rf /"})
        (True, "rm with recursive flag blocked ...")
        >>> is_blocked("Bash", {"command": "git push origin main"})
        (True, "git push blocked ...")
        >>> is_blocked("Read", {"file_path": "/home/user/.env"})
        (True, ".env file access blocked ...")
        >>> is_blocked("Read", {"file_path": "README.md"})
        (False, "")
    """
    if tool_name == "Bash":
        command: str = tool_input.get("command", "")
        for pattern, reason in _BLOCKED_BASH_PATTERNS:
            if pattern.search(command):
                return True, reason
        return False, ""

    if tool_name in _FILE_TOOLS:
        file_path: str = (
            tool_input.get("file_path")
            or tool_input.get("path")
            or ""
        )
        if file_path:
            for pattern, reason in _BLOCKED_FILE_PATTERNS:
                if pattern.search(file_path):
                    return True, reason
        return False, ""

    return False, ""


# ---------------------------------------------------------------------------
# Audit log helper
# ---------------------------------------------------------------------------

def _append_audit_log(
    tool_name: str,
    tool_input: dict[str, Any],
    tool_use_id: str,
    audit_log_path: str = _DEFAULT_AUDIT_LOG,
) -> None:
    """
    Append one JSONL entry to the audit log.

    Each entry records: timestamp (UTC ISO-8601), tool_name, tool_use_id,
    and the sanitised tool_input.  Failures are silenced — audit log errors
    must not block tool execution.

    The log file is created on first write.  Parent directory is created as
    needed.  The path is gitignored via the project .gitignore entry for
    'logs/'.
    """
    entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool_name": tool_name,
        "tool_use_id": tool_use_id,
        "tool_input": tool_input,
    }
    try:
        Path(audit_log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(audit_log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        # Audit log failure must not interrupt tool execution.
        pass


# ---------------------------------------------------------------------------
# Hook callback factories
# ---------------------------------------------------------------------------

def create_pre_tool_use_hook(audit_log_path: str = _DEFAULT_AUDIT_LOG):
    """
    Return an async PreToolUse hook callback.

    The returned callback:
      1. Appends every tool call to the audit log.
      2. Returns ``permissionDecision: "deny"`` for calls that match the
         第5条 deny-list (is_blocked returns True).
      3. Returns ``permissionDecision: "allow"`` for SAFE_READONLY_TOOLS to
         avoid approval flooding (plan §7).
      4. Returns an empty dict for all other calls, deferring to the SDK's
         own permission rules.

    Args:
        audit_log_path: Path to the JSONL audit log file.

    Returns:
        Async callback compatible with the HookCallback type alias.
    """
    async def pre_tool_use_callback(
        hook_input: Any,
        session_id: str | None,
        ctx: Any,
    ) -> dict:
        tool_name: str = hook_input.get("tool_name", "") if isinstance(hook_input, dict) else getattr(hook_input, "tool_name", "")
        tool_input: dict = hook_input.get("tool_input", {}) if isinstance(hook_input, dict) else getattr(hook_input, "tool_input", {})
        tool_use_id: str = hook_input.get("tool_use_id", "") if isinstance(hook_input, dict) else getattr(hook_input, "tool_use_id", "")

        # Step 1: Audit-log every call (before decision, so even blocked calls appear)
        _append_audit_log(tool_name, tool_input, tool_use_id, audit_log_path)

        # Step 2: Check deny-list (第5条 ソフト境界)
        blocked, reason = is_blocked(tool_name, tool_input)
        if blocked:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }

        # Step 3: Auto-approve safe read-only tools (avoid approval flooding)
        if tool_name in SAFE_READONLY_TOOLS:
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                }
            }

        # Step 4: Defer to SDK permission rules for everything else
        return {}

    return pre_tool_use_callback


def create_subagent_stop_hook(audit_log_path: str = _DEFAULT_AUDIT_LOG):
    """
    Return an async SubagentStop hook stub.

    Logs subagent completion to the audit log for observability.
    Does not intervene in execution (stub — extensible in Phase 5+).

    Args:
        audit_log_path: Path to the JSONL audit log file.

    Returns:
        Async callback compatible with the HookCallback type alias.
    """
    async def subagent_stop_callback(
        hook_input: Any,
        session_id: str | None,
        ctx: Any,
    ) -> dict:
        agent_id: str = hook_input.get("agent_id", "unknown") if isinstance(hook_input, dict) else getattr(hook_input, "agent_id", "unknown")
        agent_type: str = hook_input.get("agent_type", "unknown") if isinstance(hook_input, dict) else getattr(hook_input, "agent_type", "unknown")

        _append_audit_log(
            tool_name="SubagentStop",
            tool_input={"agent_id": agent_id, "agent_type": agent_type},
            tool_use_id=agent_id,
            audit_log_path=audit_log_path,
        )
        # No intervention — stub only
        return {}

    return subagent_stop_callback


# ---------------------------------------------------------------------------
# Top-level API
# ---------------------------------------------------------------------------

def make_hooks(
    audit_log_path: str | None = None,
) -> dict[str, list[HookMatcher]]:
    """
    Build the hooks dict for ``ClaudeAgentOptions(hooks=make_hooks())``.

    第5条 ソフト境界:
      PreToolUse  → blocks dangerous operations + auto-approves safe read-only
                    tools + appends every call to audit log.
      SubagentStop → logs subagent completion (stub; no execution intervention).

    Args:
        audit_log_path: Override the audit log path (default: SDD_AUDIT_LOG env
                        var or ``logs/audit.jsonl`` in the project root).

    Returns:
        Dict mapping HookEvent strings to lists of HookMatcher.

    Usage::

        from harness.hooks import make_hooks
        from agents.definitions import build_options

        options = build_options(hooks=make_hooks())
    """
    log_path = audit_log_path or _DEFAULT_AUDIT_LOG

    return {
        "PreToolUse": [
            HookMatcher(
                matcher=None,  # match ALL tools — no tool is exempt from audit
                hooks=[create_pre_tool_use_hook(log_path)],
            )
        ],
        "SubagentStop": [
            HookMatcher(
                matcher=None,
                hooks=[create_subagent_stop_hook(log_path)],
            )
        ],
    }
