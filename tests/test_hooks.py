"""
tests/test_hooks.py — Phase 4 (T4.1) unit tests for harness/hooks.py.

第5条 ソフト境界 verification:
  AC(T4.1): rm -rf / git push / .env read are BLOCKED by PreToolUse guard.
  AC(T4.1): safe read-only tools (Read, Grep, etc.) are auto-approved.
  AC(T4.1): every tool call is written to the audit log (JSONL).

Test strategy:
  - is_blocked() is a pure function — tested without any SDK involvement.
  - The async hook callback is exercised via asyncio.run() with mock inputs.
  - Audit log is verified by checking the JSONL file content after a hook call.
  - make_hooks() returns a dict with expected structure (smoke test).
  - No real Agent SDK sessions are started; no network required.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from harness.hooks import (
    SAFE_READONLY_TOOLS,
    _append_audit_log,
    create_pre_tool_use_hook,
    create_subagent_stop_hook,
    is_blocked,
    make_hooks,
)
from claude_agent_sdk import HookMatcher


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _pre_tool_use_input(tool_name: str, tool_input: dict, tool_use_id: str = "tuid-001") -> dict:
    """Build a minimal PreToolUseHookInput-shaped dict for testing."""
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_use_id": tool_use_id,
    }


_MOCK_CTX: dict = {"signal": None}


# ---------------------------------------------------------------------------
# Tests: is_blocked() pure predicate — 第5条 ソフト境界
# ---------------------------------------------------------------------------

class TestIsBlockedPredicate:
    """Pure unit tests for is_blocked() — no SDK, no async, no I/O."""

    # --- rm -rf variants (dangerous Bash) ---

    def test_rm_rf_is_blocked(self):
        """rm -rf must be blocked (第5条: destructive file removal)."""
        blocked, reason = is_blocked("Bash", {"command": "rm -rf /"})
        assert blocked is True, "rm -rf / must be blocked"
        assert reason, "blocked reason must be non-empty"

    def test_rm_rf_subdir_is_blocked(self):
        """rm -rf on any directory is blocked."""
        blocked, reason = is_blocked("Bash", {"command": "rm -rf ./build"})
        assert blocked is True

    def test_rm_fr_is_blocked(self):
        """rm -fr (flags reversed) must also be blocked."""
        blocked, reason = is_blocked("Bash", {"command": "rm -fr tempdir"})
        assert blocked is True, "rm -fr (reversed flags) must be blocked"

    def test_rm_recursive_long_flag_is_blocked(self):
        """rm --recursive must be blocked."""
        blocked, reason = is_blocked("Bash", {"command": "rm --recursive /tmp/junk"})
        assert blocked is True

    def test_rm_r_no_f_is_blocked(self):
        """rm -r (without -f) must also be blocked (recursive is sufficient)."""
        blocked, reason = is_blocked("Bash", {"command": "rm -r ./dist"})
        assert blocked is True

    def test_rm_without_recursive_is_allowed(self):
        """Plain 'rm file.txt' (no recursive flag) is allowed."""
        blocked, reason = is_blocked("Bash", {"command": "rm -f file.txt"})
        # -f alone (without -r) should be allowed
        assert blocked is False, "rm -f without recursive should be allowed"

    def test_rm_single_file_is_allowed(self):
        """rm on a single file with no recursive flag is allowed."""
        blocked, reason = is_blocked("Bash", {"command": "rm artifact.txt"})
        assert blocked is False

    # --- git push (first-class block) ---

    def test_git_push_is_blocked(self):
        """git push must be blocked (第5条: irreversible remote write)."""
        blocked, reason = is_blocked("Bash", {"command": "git push origin main"})
        assert blocked is True, "git push must be blocked"

    def test_git_push_force_is_blocked(self):
        """git push --force must be blocked."""
        blocked, reason = is_blocked("Bash", {"command": "git push --force origin main"})
        assert blocked is True

    def test_git_push_bare_is_blocked(self):
        """'git push' with no remote is blocked."""
        blocked, reason = is_blocked("Bash", {"command": "git push"})
        assert blocked is True

    def test_git_pull_is_allowed(self):
        """git pull is allowed (fetch + merge, not a push)."""
        blocked, reason = is_blocked("Bash", {"command": "git pull origin main"})
        assert blocked is False

    def test_git_commit_is_allowed(self):
        """git commit is a local operation and is allowed."""
        blocked, reason = is_blocked("Bash", {"command": "git commit -m 'wip'"})
        assert blocked is False

    def test_ls_is_allowed(self):
        """ls is a safe read-only command."""
        blocked, reason = is_blocked("Bash", {"command": "ls -la"})
        assert blocked is False

    def test_pytest_is_allowed(self):
        """Running pytest is allowed."""
        blocked, reason = is_blocked("Bash", {"command": "python -m pytest tests/"})
        assert blocked is False

    # --- .env / secret file access ---

    def test_read_dotenv_is_blocked(self):
        """.env file read must be blocked (第5条: credential protection)."""
        blocked, reason = is_blocked("Read", {"file_path": ".env"})
        assert blocked is True, "Reading .env must be blocked"

    def test_read_dotenv_local_is_blocked(self):
        """'.env.local' (dotenv variant) read must be blocked."""
        blocked, reason = is_blocked("Read", {"file_path": ".env.local"})
        assert blocked is True

    def test_read_dotenv_in_path_is_blocked(self):
        """/home/user/.env (absolute path) read must be blocked."""
        blocked, reason = is_blocked("Read", {"file_path": "/home/user/.env"})
        assert blocked is True

    def test_read_pem_key_is_blocked(self):
        """Reading a .pem file must be blocked."""
        blocked, reason = is_blocked("Read", {"file_path": "server.pem"})
        assert blocked is True

    def test_read_private_key_is_blocked(self):
        """Reading a .key file must be blocked."""
        blocked, reason = is_blocked("Read", {"file_path": "id_rsa.key"})
        assert blocked is True

    def test_read_readme_is_allowed(self):
        """Reading README.md is a safe read and allowed."""
        blocked, reason = is_blocked("Read", {"file_path": "README.md"})
        assert blocked is False

    def test_read_python_file_is_allowed(self):
        """Reading a .py file is allowed."""
        blocked, reason = is_blocked("Read", {"file_path": "graph/nodes.py"})
        assert blocked is False

    def test_edit_dotenv_is_blocked(self):
        """Editing a .env file must be blocked."""
        blocked, reason = is_blocked("Edit", {"file_path": ".env"})
        assert blocked is True

    def test_write_dotenv_is_blocked(self):
        """Writing to a .env file must be blocked."""
        blocked, reason = is_blocked("Write", {"file_path": ".env"})
        assert blocked is True

    # --- Other tools not in deny-list ---

    def test_unknown_tool_is_allowed(self):
        """An unknown tool name returns (False, '') — deny-list only."""
        blocked, reason = is_blocked("WebFetch", {"url": "https://example.com"})
        assert blocked is False

    def test_task_tool_is_allowed(self):
        """Task tool is not in the bash/file deny-list."""
        blocked, reason = is_blocked("Task", {"description": "do something"})
        assert blocked is False


# ---------------------------------------------------------------------------
# Tests: async PreToolUse hook callback — 第5条 enforcement via SDK interface
# ---------------------------------------------------------------------------

class TestPreToolUseHookCallback:
    """
    Tests for the async hook callback returned by create_pre_tool_use_hook().
    Each test calls the hook via asyncio.run() — no real SDK session needed.
    """

    @pytest.fixture
    def log_file(self, tmp_path: Path) -> Path:
        return tmp_path / "audit.jsonl"

    def _run_hook(self, hook, tool_name: str, tool_input: dict, log_file: Path) -> dict:
        """Helper: run the async hook and return its output dict."""
        hook_input = _pre_tool_use_input(tool_name, tool_input)
        return asyncio.run(hook(hook_input, None, _MOCK_CTX))

    # --- Dangerous operations must be denied ---

    def test_hook_denies_rm_rf(self, log_file: Path):
        """PreToolUse hook must deny rm -rf (第5条)."""
        hook = create_pre_tool_use_hook(str(log_file))
        result = self._run_hook(hook, "Bash", {"command": "rm -rf /"}, log_file)

        specific = result.get("hookSpecificOutput", {})
        assert specific.get("permissionDecision") == "deny", (
            f"rm -rf must be denied; got hookSpecificOutput={specific!r}"
        )

    def test_hook_denies_git_push(self, log_file: Path):
        """PreToolUse hook must deny git push (第5条)."""
        hook = create_pre_tool_use_hook(str(log_file))
        result = self._run_hook(hook, "Bash", {"command": "git push origin main"}, log_file)

        specific = result.get("hookSpecificOutput", {})
        assert specific.get("permissionDecision") == "deny", (
            f"git push must be denied; got hookSpecificOutput={specific!r}"
        )

    def test_hook_denies_dotenv_read(self, log_file: Path):
        """PreToolUse hook must deny reading .env file (第5条)."""
        hook = create_pre_tool_use_hook(str(log_file))
        result = self._run_hook(hook, "Read", {"file_path": ".env"}, log_file)

        specific = result.get("hookSpecificOutput", {})
        assert specific.get("permissionDecision") == "deny", (
            f".env read must be denied; got hookSpecificOutput={specific!r}"
        )

    # --- Safe tools must be auto-approved (avoid approval flooding) ---

    def test_hook_allows_read_safe_file(self, log_file: Path):
        """PreToolUse hook auto-approves Read for safe files (plan §7)."""
        hook = create_pre_tool_use_hook(str(log_file))
        result = self._run_hook(hook, "Read", {"file_path": "graph/nodes.py"}, log_file)

        specific = result.get("hookSpecificOutput", {})
        assert specific.get("permissionDecision") == "allow", (
            f"Read on safe file must be allowed; got hookSpecificOutput={specific!r}"
        )

    def test_hook_allows_grep(self, log_file: Path):
        """PreToolUse hook auto-approves Grep (read-only tool)."""
        hook = create_pre_tool_use_hook(str(log_file))
        result = self._run_hook(hook, "Grep", {"pattern": "def build", "path": "."}, log_file)

        specific = result.get("hookSpecificOutput", {})
        assert specific.get("permissionDecision") == "allow"

    # --- Audit log must be written for every call ---

    def test_hook_writes_audit_log_for_allowed_tool(self, log_file: Path):
        """Every tool call — even allowed ones — must be logged to audit JSONL."""
        hook = create_pre_tool_use_hook(str(log_file))
        self._run_hook(hook, "Read", {"file_path": "README.md"}, log_file)

        assert log_file.exists(), "audit log must be created"
        lines = log_file.read_text().strip().splitlines()
        assert len(lines) >= 1, "at least one audit entry must be written"
        entry = json.loads(lines[-1])
        assert entry["tool_name"] == "Read"
        assert "file_path" in entry["tool_input"] or "path" in entry["tool_input"]

    def test_hook_writes_audit_log_for_blocked_tool(self, log_file: Path):
        """Blocked tool calls must also appear in the audit log."""
        hook = create_pre_tool_use_hook(str(log_file))
        self._run_hook(hook, "Bash", {"command": "rm -rf /"}, log_file)

        assert log_file.exists()
        lines = log_file.read_text().strip().splitlines()
        entry = json.loads(lines[-1])
        assert entry["tool_name"] == "Bash"
        assert "rm -rf" in entry["tool_input"].get("command", "")

    def test_audit_log_is_jsonl(self, log_file: Path):
        """Each line in the audit log must be valid JSON."""
        hook = create_pre_tool_use_hook(str(log_file))
        self._run_hook(hook, "Bash", {"command": "ls -la"}, log_file)
        self._run_hook(hook, "Read", {"file_path": "README.md"}, log_file)

        assert log_file.exists()
        for line in log_file.read_text().strip().splitlines():
            entry = json.loads(line)  # must not raise
            assert "timestamp" in entry
            assert "tool_name" in entry

    def test_audit_log_accumulates_multiple_calls(self, log_file: Path):
        """Multiple hook calls append to the audit log (not overwrite)."""
        hook = create_pre_tool_use_hook(str(log_file))
        for i in range(3):
            self._run_hook(hook, "Grep", {"pattern": f"pattern_{i}"}, log_file)

        lines = log_file.read_text().strip().splitlines()
        assert len(lines) == 3, f"Expected 3 audit entries; got {len(lines)}"


# ---------------------------------------------------------------------------
# Tests: SubagentStop hook stub
# ---------------------------------------------------------------------------

class TestSubagentStopHook:
    """SubagentStop hook logs agent completion without blocking execution."""

    @pytest.fixture
    def log_file(self, tmp_path: Path) -> Path:
        return tmp_path / "subagent-audit.jsonl"

    def test_subagent_stop_hook_logs_agent_id(self, log_file: Path):
        """SubagentStop hook must write agent_id to audit log."""
        hook = create_subagent_stop_hook(str(log_file))
        hook_input = {
            "hook_event_name": "SubagentStop",
            "stop_hook_active": False,
            "agent_id": "agent-abc123",
            "agent_transcript_path": "/tmp/transcript.json",
            "agent_type": "reviewer",
        }
        asyncio.run(hook(hook_input, None, _MOCK_CTX))

        assert log_file.exists()
        entry = json.loads(log_file.read_text().strip().splitlines()[-1])
        assert entry["tool_name"] == "SubagentStop"
        assert entry["tool_input"]["agent_id"] == "agent-abc123"

    def test_subagent_stop_hook_returns_empty_dict(self, log_file: Path):
        """SubagentStop stub must return empty dict (no execution intervention)."""
        hook = create_subagent_stop_hook(str(log_file))
        hook_input = {
            "hook_event_name": "SubagentStop",
            "stop_hook_active": False,
            "agent_id": "agent-xyz",
            "agent_transcript_path": "/tmp/t.json",
            "agent_type": "tester",
        }
        result = asyncio.run(hook(hook_input, None, _MOCK_CTX))
        assert result == {}, f"SubagentStop stub must return {{}}; got {result!r}"


# ---------------------------------------------------------------------------
# Tests: make_hooks() structure
# ---------------------------------------------------------------------------

class TestMakeHooks:
    """Smoke tests for the make_hooks() top-level API."""

    def test_make_hooks_returns_dict(self):
        """make_hooks() must return a dict."""
        hooks = make_hooks()
        assert isinstance(hooks, dict)

    def test_make_hooks_has_pre_tool_use_key(self):
        """make_hooks() must have a 'PreToolUse' key."""
        hooks = make_hooks()
        assert "PreToolUse" in hooks, "hooks dict must contain 'PreToolUse'"

    def test_make_hooks_has_subagent_stop_key(self):
        """make_hooks() must have a 'SubagentStop' key."""
        hooks = make_hooks()
        assert "SubagentStop" in hooks, "hooks dict must contain 'SubagentStop'"

    def test_pre_tool_use_is_list_of_hook_matchers(self):
        """PreToolUse value must be a list of HookMatcher instances."""
        hooks = make_hooks()
        matchers = hooks["PreToolUse"]
        assert isinstance(matchers, list), "PreToolUse must be a list"
        assert len(matchers) >= 1
        assert all(isinstance(m, HookMatcher) for m in matchers), (
            "All PreToolUse entries must be HookMatcher instances"
        )

    def test_subagent_stop_is_list_of_hook_matchers(self):
        """SubagentStop value must be a list of HookMatcher instances."""
        hooks = make_hooks()
        matchers = hooks["SubagentStop"]
        assert isinstance(matchers, list)
        assert all(isinstance(m, HookMatcher) for m in matchers)

    def test_make_hooks_accepts_custom_log_path(self, tmp_path: Path):
        """make_hooks() must accept a custom audit_log_path without error."""
        custom_log = str(tmp_path / "custom-audit.jsonl")
        hooks = make_hooks(audit_log_path=custom_log)
        assert hooks is not None


# ---------------------------------------------------------------------------
# Tests: SAFE_READONLY_TOOLS set
# ---------------------------------------------------------------------------

class TestSafeReadonlyTools:
    """Verify the SAFE_READONLY_TOOLS constant is correct."""

    def test_read_in_safe_tools(self):
        assert "Read" in SAFE_READONLY_TOOLS

    def test_grep_in_safe_tools(self):
        assert "Grep" in SAFE_READONLY_TOOLS

    def test_write_not_in_safe_tools(self):
        assert "Write" not in SAFE_READONLY_TOOLS

    def test_bash_not_in_safe_tools(self):
        assert "Bash" not in SAFE_READONLY_TOOLS

    def test_task_not_in_safe_tools(self):
        assert "Task" not in SAFE_READONLY_TOOLS


# ---------------------------------------------------------------------------
# Tests: audit log helper (_append_audit_log)
# ---------------------------------------------------------------------------

class TestAppendAuditLog:
    """Direct tests for the _append_audit_log() helper."""

    def test_creates_log_file_on_first_write(self, tmp_path: Path):
        """_append_audit_log creates the file and its parent dir on first call."""
        log_path = str(tmp_path / "sub" / "audit.jsonl")
        _append_audit_log("Read", {"file_path": "x.txt"}, "tuid-1", log_path)
        assert Path(log_path).exists()

    def test_entry_has_required_fields(self, tmp_path: Path):
        """Each audit entry must have timestamp, tool_name, tool_use_id, tool_input."""
        log_path = str(tmp_path / "audit.jsonl")
        _append_audit_log("Bash", {"command": "ls"}, "tuid-42", log_path)

        entry = json.loads(Path(log_path).read_text().strip())
        assert "timestamp" in entry
        assert entry["tool_name"] == "Bash"
        assert entry["tool_use_id"] == "tuid-42"
        assert entry["tool_input"] == {"command": "ls"}

    def test_appends_not_overwrites(self, tmp_path: Path):
        """Multiple _append_audit_log calls accumulate entries."""
        log_path = str(tmp_path / "audit.jsonl")
        _append_audit_log("Read", {}, "tuid-1", log_path)
        _append_audit_log("Grep", {}, "tuid-2", log_path)

        lines = Path(log_path).read_text().strip().splitlines()
        assert len(lines) == 2

    def test_does_not_raise_on_permission_error(self, tmp_path: Path):
        """_append_audit_log must not raise even if log path is unwritable."""
        # Use an invalid path (directory instead of file)
        _append_audit_log("Read", {}, "tuid-1", "/proc/1/this-cannot-exist/audit.jsonl")
        # No exception raised → silently ignored (audit must not block execution)
