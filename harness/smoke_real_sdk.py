"""
harness/smoke_real_sdk.py — Manual, opt-in smoke test for the real Agent SDK.

Runs ONE minimal `query()` and prints the reply + total_cost_usd.  This is NOT
part of the automated pytest suite (it makes a real model call).  Run it by hand
to confirm authentication and cost reporting are wired:

    python3 -m harness.smoke_real_sdk

Authentication (Claude Agent SDK resolves these in order):
  1. ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN  → billed to the API (metered).
  2. The Claude Code login (Pro/Max subscription)  → billed to the subscription.

If ANTHROPIC_API_KEY is set, this script WARNS — the call would be API-metered,
not drawn from your subscription.  Unset it to use the Claude Code login.

Exit codes: 0 = reply received; 1 = SDK error (auth/network).
"""
from __future__ import annotations

import asyncio
import os
import sys

from claude_agent_sdk import ClaudeAgentOptions, query


async def _smoke() -> int:
    if os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "[warn] ANTHROPIC_API_KEY is set — this call will be API-metered "
            "(separate billing), NOT drawn from your Claude subscription. "
            "Unset it to use the Claude Code login.\n",
            file=sys.stderr,
        )

    options = ClaudeAgentOptions(max_turns=1)
    reply_parts: list[str] = []
    total_cost = None
    try:
        async for msg in query(
            prompt="Reply with exactly the word: OK", options=options
        ):
            if hasattr(msg, "total_cost_usd"):
                total_cost = getattr(msg, "total_cost_usd", None)
                if getattr(msg, "result", None):
                    reply_parts.append(str(msg.result))
            elif hasattr(msg, "content"):
                for block in (msg.content or []):
                    text = getattr(block, "text", None)
                    if text:
                        reply_parts.append(str(text))
    except Exception as exc:  # noqa: BLE001
        print(f"[error] SDK query failed: {exc}", file=sys.stderr)
        return 1

    reply = " ".join(p.strip() for p in reply_parts if p.strip())
    print(f"reply         : {reply or '(empty)'}")
    print(f"total_cost_usd: {total_cost}")
    print("smoke OK — the real Agent SDK is reachable and reports cost.")
    return 0


def main() -> int:
    return asyncio.run(_smoke())


if __name__ == "__main__":
    raise SystemExit(main())
