"""
tests/test_sandbox_server.py — podman-backed test execution tool (isolation loop).

Covers the run_tests MCP tool (`mcp_servers/sandbox_server.py`) and its wiring into
the tester specialist:
  - the tool wraps run_in_sandbox and returns rc/output;
  - NFR-3: podman absent → structured "unavailable", NO host subprocess.run;
  - tester real options carry the sandbox MCP server + allow the tool name, while
    the F-7 hook still denies Bash/Glob (defense boundary preserved);
  - non-tester specialists are unchanged (no sandbox server) — backward compatible.

Offline: run_in_sandbox / _run_query are monkeypatched.  A skip-gated E2E exercises
the real podman round-trip when podman is available.
"""

import asyncio
import subprocess
from types import SimpleNamespace

import pytest

from harness.sandbox import podman_available
from mcp_servers import sandbox_server
from mcp_servers.sandbox_server import (
    SANDBOX_TOOL_NAME,
    _run_tests_impl,
    make_sandbox_server,
)


# ---------------------------------------------------------------------------
# The run_tests tool itself
# ---------------------------------------------------------------------------

class TestRunTestsTool:
    def test_returns_returncode_and_output(self, monkeypatch):
        """run_in_sandbox result → available=True with rc + output in content."""
        def fake_run(cmd, worktree_path, **kw):
            assert kw.get("network") is False           # egress blocked (NFR-3)
            assert "/workspace" in cmd[-1]               # targets the mount, not host cwd
            return SimpleNamespace(returncode=1, stdout="2 failed", stderr="")

        monkeypatch.setattr(sandbox_server, "run_in_sandbox", fake_run)
        out = asyncio.run(_run_tests_impl("/tmp/wt"))
        assert out["available"] is True
        assert out["returncode"] == 1
        assert "2 failed" in out["content"][0]["text"]

    def test_target_is_scoped_to_worktree_mount(self, monkeypatch):
        captured = {}

        def fake_run(cmd, worktree_path, **kw):
            captured["cmd"] = cmd
            return SimpleNamespace(returncode=0, stdout="ok", stderr="")

        monkeypatch.setattr(sandbox_server, "run_in_sandbox", fake_run)
        asyncio.run(_run_tests_impl("/tmp/wt", target="tests/test_x.py"))
        assert captured["cmd"][-1] == "/workspace/tests/test_x.py"

    def test_output_capped(self, monkeypatch):
        big = "x" * 10000
        monkeypatch.setattr(
            sandbox_server, "run_in_sandbox",
            lambda *a, **k: SimpleNamespace(returncode=0, stdout=big, stderr=""),
        )
        out = asyncio.run(_run_tests_impl("/tmp/wt"))
        assert len(out["content"][0]["text"]) < 5000
        assert "truncated" in out["content"][0]["text"]

    def test_tool_name_is_run_tests(self):
        srv = make_sandbox_server("/tmp/wt")
        assert srv is not None
        assert SANDBOX_TOOL_NAME == "mcp__sandbox__run_tests"


# ---------------------------------------------------------------------------
# NFR-3: no host fallback when podman is absent
# ---------------------------------------------------------------------------

class TestNoHostFallback:
    def test_unavailable_never_runs_on_host(self, monkeypatch):
        """podman absent → SandboxUnavailableError → structured result, and
        subprocess.run is NEVER called on the host (第4条 / NFR-3)."""
        monkeypatch.setattr("harness.sandbox.podman_available", lambda: False)

        def _boom(*a, **k):  # pragma: no cover - must never run
            raise AssertionError("subprocess.run called on host — NFR-3 violated!")

        monkeypatch.setattr(subprocess, "run", _boom)
        out = asyncio.run(_run_tests_impl("/tmp/wt"))
        assert out["available"] is False
        assert out["returncode"] is None
        assert "SANDBOX_UNAVAILABLE" in out["content"][0]["text"]


# ---------------------------------------------------------------------------
# Wiring into _invoke_specialist (offline option capture)
# ---------------------------------------------------------------------------

def _capture_options(monkeypatch, tmp_path, specialist_name):
    from graph import nodes

    captured = {}

    async def fake_run_query(prompt, options):
        captured["options"] = options
        return "", None

    monkeypatch.setenv("SDD_RUN_REAL_VERIFY", "1")
    monkeypatch.setenv("SDD_OBS_STORE", str(tmp_path / "obs.jsonl"))
    monkeypatch.setattr(nodes, "_run_query", fake_run_query)
    asyncio.run(nodes._invoke_specialist(
        specialist_name, str(tmp_path / "art.txt"), "t", worktree_path=str(tmp_path)
    ))
    return captured["options"]


def _pre_tool_cb(options):
    return options.hooks["PreToolUse"][0].hooks[0]


def _decide(cb, tool_name, tool_input=None):
    out = asyncio.run(cb(
        {"tool_name": tool_name, "tool_input": tool_input or {}, "tool_use_id": "x"},
        None, None,
    ))
    return "defer" if not out else out["hookSpecificOutput"]["permissionDecision"]


class TestTesterWiring:
    def test_tester_options_have_sandbox_server(self, monkeypatch, tmp_path):
        opts = _capture_options(monkeypatch, tmp_path, "tester")
        assert "sandbox" in (getattr(opts, "mcp_servers", {}) or {})
        assert SANDBOX_TOOL_NAME in opts.allowed_tools

    def test_tester_hook_allows_sandbox_tool_denies_bash(self, monkeypatch, tmp_path):
        opts = _capture_options(monkeypatch, tmp_path, "tester")
        cb = _pre_tool_cb(opts)
        assert _decide(cb, SANDBOX_TOOL_NAME) != "deny"   # sandbox tool permitted
        assert _decide(cb, "Read", {"file_path": "/x"}) == "allow"
        assert _decide(cb, "Bash", {"command": "ls"}) == "deny"   # host exec still denied
        assert _decide(cb, "Glob", {"pattern": "**/*"}) == "deny"

    def test_non_tester_specialist_has_no_sandbox(self, monkeypatch, tmp_path):
        """Backward compat: security/reviewer/validator get no sandbox server."""
        opts = _capture_options(monkeypatch, tmp_path, "security")
        assert "sandbox" not in (getattr(opts, "mcp_servers", {}) or {})
        assert SANDBOX_TOOL_NAME not in opts.allowed_tools


# ---------------------------------------------------------------------------
# E2E — real podman round-trip (skip-gated)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not podman_available(), reason="podman not installed — real sandbox E2E skipped")
class TestSandboxE2E:
    def test_run_tests_executes_in_container_and_returns_rc(self, tmp_path):
        """The tool runs inside podman and propagates a real returncode.

        A python+pytest image (SDD_SANDBOX_IMAGE) gives a true pass/fail; even the
        minimal default image proves the round-trip (tool → run_in_sandbox → podman
        → rc back) by returning a real integer returncode.
        """
        (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n")
        out = asyncio.run(_run_tests_impl(str(tmp_path)))
        assert out["available"] is True
        assert isinstance(out["returncode"], int)
