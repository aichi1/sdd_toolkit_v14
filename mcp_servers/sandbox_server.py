"""
mcp_servers/sandbox_server.py — podman-backed test execution as an MCP tool.

Closes the isolation loop: harness.sandbox.run_in_sandbox is fully built and
podman-tested but was never invoked by any graph node.  This exposes it to the
verify pipeline as an in-process MCP tool (`run_tests`) that the tester specialist
may call INSTEAD of raw Bash.  All code execution flows through podman
(--network=none, --memory cap, throwaway --rm container) — the 第4/5条 hard
boundary — and NEVER on the host (NFR-3: SandboxUnavailableError, no fallback).

第6条 (reuse): this module only wraps run_in_sandbox; it does not re-implement any
sandboxing logic.

Design — factory + closure (not a module-level server):
    verify runs the 4 specialists concurrently (asyncio.gather).  Each tester
    invocation must run tests in ITS OWN worktree, so `make_sandbox_server(cwd)`
    binds the worktree path in a closure and returns a fresh server per call.
"""
from __future__ import annotations

from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool

from harness.sandbox import SandboxUnavailableError, run_in_sandbox

#: Fully-qualified tool name (MCP tools are addressed as mcp__<server>__<tool>).
#: Used by graph.nodes to extend the tester's allow_tools AND the F-7 hook allow-list.
SANDBOX_TOOL_NAME: str = "mcp__sandbox__run_tests"

#: Container mount point for the worktree — mirrors harness.sandbox._CONTAINER_MOUNT.
#: run_in_sandbox mounts the worktree here but does NOT set a WORKDIR, so pytest
#: must be pointed at this absolute path (not a relative one).
_MOUNT: str = "/workspace"

#: Cap on returned output so a huge test log cannot blow up the agent's context.
_MAX_OUTPUT_CHARS: int = 4000


async def _run_tests_impl(worktree_path: str, target: str = "") -> dict[str, Any]:
    """
    Run the worktree's pytest suite inside the podman sandbox and return the result.

    Kept as a plain async function (separate from the @tool wrapper) so unit tests
    can call it directly without the MCP handshake.

    Args:
        worktree_path: host path of the git worktree to mount + test.
        target:        optional test path RELATIVE to the worktree root; empty
                       runs the whole suite.

    Returns:
        MCP-style result dict with keys: content, available (bool), returncode.
        On podman absence → available=False, returncode=None, and NO host
        execution occurs (NFR-3 — run_in_sandbox raises before any subprocess).
    """
    cmd = ["python", "-m", "pytest", "-q", f"{_MOUNT}/{target}" if target else _MOUNT]
    try:
        # network=False → egress blocked (NFR-3); read_only=False → pytest may
        # write __pycache__/.pytest_cache inside the throwaway container.
        proc = run_in_sandbox(cmd, worktree_path, network=False, read_only=False)
    except SandboxUnavailableError as exc:
        return {
            "content": [{"type": "text", "text": f"SANDBOX_UNAVAILABLE: {exc}"}],
            "available": False,
            "returncode": None,
        }

    combined = (proc.stdout or "") + (proc.stderr or "")
    if len(combined) > _MAX_OUTPUT_CHARS:
        combined = "…(truncated)…\n" + combined[-_MAX_OUTPUT_CHARS:]
    return {
        "content": [
            {"type": "text", "text": f"returncode={proc.returncode}\n{combined}"}
        ],
        "available": True,
        "returncode": proc.returncode,
    }


def make_sandbox_server(worktree_path: str):
    """
    Build a fresh in-process "sandbox" MCP server bound to one worktree.

    A factory (not a shared module-level server) because the verify node runs
    specialists concurrently; each needs its own worktree captured in the closure.

    Returns:
        The object from create_sdk_mcp_server(name="sandbox", ...), suitable for
        ClaudeAgentOptions(mcp_servers={"sandbox": server}).
    """

    @tool(
        "run_tests",
        "worktree 内のテストスイートを podman サンドボックス（--network=none・"
        "メモリ上限・使い捨てコンテナ）で実行し、終了コードと出力を返す。"
        "target を省略するとスイート全体を実行する（worktree ルートからの相対パス）。"
        "podman が無い場合は SANDBOX_UNAVAILABLE を返す（ホストでは実行しない）。",
        {"target": str},
    )
    async def run_tests(args: dict[str, Any]) -> dict[str, Any]:
        target = (args.get("target") or "").strip().lstrip("/")
        return await _run_tests_impl(worktree_path, target)

    return create_sdk_mcp_server(name="sandbox", version="1.0.0", tools=[run_tests])
