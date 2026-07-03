"""
tests/test_hook_allowlist.py — F-7: PreToolUse hook enforces the agent allow-list.

A real-API smoke showed that ClaudeAgentOptions(allowed_tools=["Read","Grep"]) is
ADVISORY: a specialist still invoked Bash and Glob.  The allow-list must therefore
be enforced at the hook layer (the real 第4/5条 boundary).  These tests fix that
contract.  All offline (hook callbacks are pure; no API).
"""

import asyncio

import pytest

from agents.definitions import BUILDER_TOOLS, build_options
from harness.hooks import make_hooks


def _callback(hooks: dict):
    return hooks["PreToolUse"][0].hooks[0]


def _decide(cb, tool_name, tool_input=None):
    out = asyncio.run(cb(
        {"tool_name": tool_name, "tool_input": tool_input or {}, "tool_use_id": "t"},
        None, None,
    ))
    if not out:
        return "defer"
    return out["hookSpecificOutput"]["permissionDecision"]


class TestAllowListEnforced:
    def test_denies_tools_outside_allowlist(self, tmp_path):
        """AC-1: Read/Grep-only allow-list denies Bash / Glob / LS (even safe-readonly)."""
        cb = _callback(make_hooks(str(tmp_path / "a.jsonl"), allowed_tools=["Read", "Grep"]))
        for tool in ("Bash", "Glob", "LS", "Write", "WebFetch"):
            assert _decide(cb, tool, {"command": "ls"}) == "deny", f"{tool} should be denied"

    def test_allows_tools_inside_allowlist(self, tmp_path):
        """AC-2: allow-listed read-only tools are approved."""
        cb = _callback(make_hooks(str(tmp_path / "a.jsonl"), allowed_tools=["Read", "Grep"]))
        assert _decide(cb, "Read", {"file_path": "/x/a.py"}) == "allow"
        assert _decide(cb, "Grep", {"pattern": "x"}) == "allow"


class TestBackwardCompatNoAllowList:
    def test_no_allowlist_defers_benign_bash(self, tmp_path):
        """AC-3: make_hooks() without an allow-list keeps legacy behaviour (Bash → defer)."""
        cb = _callback(make_hooks(str(tmp_path / "a.jsonl")))
        assert _decide(cb, "Bash", {"command": "ls -la"}) == "defer"

    def test_no_allowlist_still_allows_readonly(self, tmp_path):
        cb = _callback(make_hooks(str(tmp_path / "a.jsonl")))
        assert _decide(cb, "Glob", {"pattern": "**/*"}) == "allow"


class TestDenyListPriority:
    def test_denylist_wins_even_for_allowlisted_tool(self, tmp_path):
        """AC-4: rm -rf is denied even when Bash IS in the allow-list (deny-list priority)."""
        cb = _callback(make_hooks(str(tmp_path / "a.jsonl"), allowed_tools=BUILDER_TOOLS))
        assert "Bash" in BUILDER_TOOLS  # precondition
        assert _decide(cb, "Bash", {"command": "rm -rf /"}) == "deny"

    def test_benign_bash_allowed_for_builder_allowlist(self, tmp_path):
        """A builder (Bash in allow-list) may run a benign Bash (deferred, not denied)."""
        cb = _callback(make_hooks(str(tmp_path / "a.jsonl"), allowed_tools=BUILDER_TOOLS))
        assert _decide(cb, "Bash", {"command": "pytest -q"}) == "defer"


class TestBuilderOptionsAllowList:
    def test_build_options_hook_enforces_builder_tools(self):
        """AC-6: build_options() hook denies a tool outside BUILDER_TOOLS, allows Write."""
        cb = _callback(build_options().hooks)
        assert _decide(cb, "WebFetch", {"url": "http://x"}) == "deny"
        # Write is in BUILDER_TOOLS and not safe-readonly → deferred (allowed to proceed)
        assert _decide(cb, "Write", {"file_path": "/x", "content": "y"}) == "defer"
        assert "Bash" in BUILDER_TOOLS


class TestSpecialistOptionsAllowList:
    def test_specialist_hook_denies_bash(self, monkeypatch, tmp_path):
        """AC-5: the real specialist's hook (from _invoke_specialist) denies Bash."""
        from graph import nodes

        captured = {}

        async def fake_run_query(prompt, options):
            captured["options"] = options
            return "", None

        monkeypatch.setenv("SDD_RUN_REAL_VERIFY", "1")
        monkeypatch.setenv("SDD_OBS_STORE", str(tmp_path / "obs.jsonl"))
        monkeypatch.setattr(nodes, "_run_query", fake_run_query)
        asyncio.run(nodes._invoke_specialist(
            "tester", str(tmp_path / "art.txt"), "t", worktree_path=str(tmp_path)
        ))

        cb = _callback(captured["options"].hooks)
        assert _decide(cb, "Bash", {"command": "ls"}) == "deny"
        assert _decide(cb, "Glob", {"pattern": "**/*"}) == "deny"
        assert _decide(cb, "Read", {"file_path": "/x"}) == "allow"
