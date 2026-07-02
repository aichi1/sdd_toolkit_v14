"""
review/app.py — FastAPI local review UI for sdd_toolkit_v14 (Phase 7 / T7.1).

FR-5.2: GET /review displays the interrupt payload (diff_ref, findings,
        eval_score) and provides Approve/Reject buttons that send
        Command(resume={"action":"approve"|"reject"}) to the graph.

FR-5.3 / 第3条: This web layer is SIDE-EFFECT-FREE with respect to git/merge.
        All merge logic lives exclusively inside the `review` graph node's
        approve branch (graph/nodes.py::review() → merge_worktree call).
        The web layer only forwards Command(resume=...) to the graph — no
        file writes, no git calls, no subprocess, no external notifications.

N2: NO ntfy / Telegram / external notification services are used.
    Everything runs on localhost only. Single process. No egress.

CLI resume coexists (Phase 1):
    Any caller that issues:
        graph.invoke(Command(resume={"action":"approve"|"reject"}), config)
    with the same thread_id works alongside the web UI. Both paths send the
    same Command to the same graph node. The graph is agnostic to who sends it.

Interrupt payload access (langgraph 1.2.7):
    state = graph.get_state(config)   # StateSnapshot (NamedTuple)
    state.interrupts                  # tuple[Interrupt, ...] — directly on snapshot
    state.interrupts[0].value         # dict: {kind, diff_ref, findings, eval_score}

    Verified: StateSnapshot._fields includes 'interrupts' (direct field, not via tasks).
    Fallback: state.interrupts empty → 404 "no pending interrupt" (not a crash).

Standalone usage:
    python -m review.app              # uses __main__ block below
    # For factory-mode: uvicorn review.app:create_app --factory
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from langgraph.types import Command


# ---------------------------------------------------------------------------
# HTML rendering helpers (side-effect-free pure functions)
# ---------------------------------------------------------------------------

def _esc(s: Any) -> str:
    """Minimal HTML entity escaping."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _findings_html(findings: list[str] | None) -> str:
    """Render findings list as an HTML <ul>."""
    if not findings:
        return "<em>(none)</em>"
    items = "\n".join(f"<li>{_esc(f)}</li>" for f in findings)
    return f"<ul>\n{items}\n</ul>"


def _render_index_page() -> str:
    """Render the friendly index / landing page."""
    return """\
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>SDD Review UI</title>
  <style>
    body { font-family: monospace; max-width: 800px; margin: 2em auto; }
    code { background: #f0f0f0; padding: 0.1em 0.3em; border-radius: 2px; }
  </style>
</head>
<body>
  <h1>SDD Review UI</h1>
  <p>Local approval gate for sdd_toolkit_v14. <strong>N2: no external notifications.</strong></p>

  <h2>Usage</h2>
  <ul>
    <li>HTML review page: <code>/review?thread_id=YOUR_THREAD_ID</code></li>
    <li>JSON payload:    <code>/review.json?thread_id=YOUR_THREAD_ID</code></li>
    <li>Approve:         <code>POST /approve</code> (form field: thread_id)</li>
    <li>Reject:          <code>POST /reject</code>  (form field: thread_id)</li>
  </ul>

  <h2>Architecture notes</h2>
  <ul>
    <li><strong>第3条 — web-layer side-effect-free:</strong>
        This UI only forwards <code>Command(resume=...)</code> to the graph.
        Merge logic (<code>merge_worktree</code>) lives exclusively inside
        <code>graph/nodes.py::review()</code> approve branch.</li>
    <li><strong>CLI resume coexists:</strong>
        <code>graph.invoke(Command(resume={"action":"approve"}), config)</code>
        and the web UI are equivalent — same Command, same graph, same thread.</li>
    <li><strong>N2 — local only:</strong>
        No ntfy / Telegram / external service. Single process.</li>
  </ul>
</body>
</html>"""


def _render_review_page(
    thread_id: str,
    kind: str,
    diff_ref: str,
    findings: list[str] | None,
    eval_score: float | None,
) -> str:
    """Render the full review HTML page with Approve/Reject buttons."""
    score_str = f"{eval_score:.3f}" if eval_score is not None else "N/A"
    return f"""\
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>SDD Review — {_esc(thread_id)}</title>
  <style>
    body {{ font-family: monospace; max-width: 900px; margin: 2em auto; }}
    .payload {{ background: #f5f5f5; padding: 1em; border-radius: 4px; }}
    .actions {{ margin-top: 2em; display: flex; gap: 1em; }}
    .actions form {{ display: inline; }}
    .btn-approve {{
      background: #28a745; color: white; padding: 0.6em 2em;
      border: none; cursor: pointer; font-size: 1em; border-radius: 3px;
    }}
    .btn-reject {{
      background: #dc3545; color: white; padding: 0.6em 2em;
      border: none; cursor: pointer; font-size: 1em; border-radius: 3px;
    }}
    code {{ background: #e8e8e8; padding: 0.1em 0.3em; border-radius: 2px; }}
    .note {{ font-size: 0.85em; color: #555; margin-top: 2em; border-top: 1px solid #ccc; padding-top: 1em; }}
  </style>
</head>
<body>
  <h1>SDD Review Gate</h1>
  <p><strong>Thread:</strong> <code>{_esc(thread_id)}</code></p>

  <div class="payload">
    <h2>Interrupt Payload</h2>
    <p><strong>Kind:</strong> {_esc(kind)}</p>
    <p><strong>Diff Ref:</strong> <code>{_esc(diff_ref)}</code></p>
    <p><strong>Eval Score:</strong> {_esc(score_str)}</p>
    <h3>Findings</h3>
    {_findings_html(findings)}
  </div>

  <div class="actions">
    <form method="post" action="/approve">
      <input type="hidden" name="thread_id" value="{_esc(thread_id)}">
      <button class="btn-approve" type="submit">Approve</button>
    </form>
    <form method="post" action="/reject">
      <input type="hidden" name="thread_id" value="{_esc(thread_id)}">
      <button class="btn-reject" type="submit">Reject</button>
    </form>
  </div>

  <div class="note">
    <strong>第3条 — web-layer is side-effect-free:</strong>
    Merge happens only inside the graph node (<code>graph/nodes.py::review()</code>
    approve branch). This UI only sends <code>Command(resume=...)</code>.<br>
    <strong>CLI resume coexists:</strong>
    <code>graph.invoke(Command(resume={{&quot;action&quot;:&quot;approve&quot;}}), config)</code>
    is equivalent to the Approve button above.
  </div>
</body>
</html>"""


def _render_decision_page(thread_id: str, decision: str, action: str) -> str:
    """Render the post-approve/reject confirmation page."""
    review_link = f"/review?thread_id={_esc(thread_id)}"
    extra = ""
    if action == "reject":
        extra = (
            f'<p>Graph has looped back to build. '
            f'<a href="{review_link}">View next interrupt</a> when ready.</p>'
        )
    return f"""\
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <title>SDD Review — Decision: {_esc(decision)}</title>
  <style>body {{ font-family: monospace; max-width: 800px; margin: 2em auto; }}</style>
</head>
<body>
  <h1>Decision: {_esc(decision)}</h1>
  <p><strong>Thread:</strong> <code>{_esc(thread_id)}</code></p>
  {extra}
  <p><a href="/">Back to index</a></p>
</body>
</html>"""


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(graph=None) -> FastAPI:
    """
    Create and return the FastAPI review application.

    Args:
        graph: A compiled LangGraph graph (CompiledGraph from build_graph()).
               If None, the default graph is built via build_graph() using
               "state.db" in the current working directory (FR-5.1).
               Pass a custom/stub graph in tests to avoid touching real state.

    Side-effect policy (第3条 / FR-5.3):
        This web layer is COMPLETELY SIDE-EFFECT-FREE.
          - GET /review and GET /review.json: read-only via graph.get_state().
          - POST /approve and POST /reject: forward Command(resume=...) via
            graph.invoke(). All merge logic (merge_worktree, git operations)
            lives exclusively in graph/nodes.py::review() approve branch.
          - No subprocess, no file writes, no external network calls (N2).

    CLI resume coexistence:
        graph.invoke(Command(resume={"action":"approve"}), config)   # CLI
        POST /approve (thread_id)                                      # web UI
        Both are equivalent — same Command to the same graph/thread.

    Returns:
        FastAPI application instance.
    """
    if graph is None:
        # Lazy import: only builds the default graph when needed (not at import time).
        # This avoids creating state.db in the current directory during test collection.
        from graph.build_graph import build_graph as _build_graph
        graph = _build_graph()

    app = FastAPI(
        title="SDD Review UI",
        description=(
            "Local FastAPI review面 for sdd_toolkit_v14 Phase 7 (T7.1). "
            "Displays interrupt() payload and forwards approve/reject Command to the graph. "
            "第3条: web layer is side-effect-free — merge only in graph node. "
            "N2: no external notifications."
        ),
        version="1.0.0",
    )

    # ── GET / ─────────────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        """Friendly index page with usage instructions (N2 note, 第3条 note)."""
        return _render_index_page()

    # ── GET /review ───────────────────────────────────────────────────────

    @app.get("/review")
    def get_review(request: Request, thread_id: str):
        """
        Fetch the pending interrupt payload for thread_id and render a review page.

        FR-5.2: displays kind, diff_ref, findings, eval_score with Approve/Reject.

        Interrupt access path (langgraph 1.2.7):
            state = graph.get_state(config)
            state.interrupts[0].value   # {kind, diff_ref, findings, eval_score}
            StateSnapshot.interrupts is a direct field (verified against installed version).

        Graceful handling:
            Non-existent thread or completed graph → state.interrupts is empty
            → returns 404 with a clear explanatory message (not a crash).

        Content negotiation:
            Accept: application/json  → JSON response (same as /review.json).
            Default                   → HTML page with Approve/Reject buttons.
        """
        config = {"configurable": {"thread_id": thread_id}}

        try:
            state = graph.get_state(config)
        except Exception as exc:
            return JSONResponse(
                {"error": f"failed to get state: {exc}", "thread_id": thread_id},
                status_code=500,
            )

        # No pending interrupt: graceful 404
        if not state.interrupts:
            accept = request.headers.get("accept", "")
            if "application/json" in accept:
                return JSONResponse(
                    {"error": "no pending interrupt", "thread_id": thread_id},
                    status_code=404,
                )
            return HTMLResponse(
                f"""\
<!DOCTYPE html><html><body>
<h1>No Pending Interrupt</h1>
<p>Thread <code>{_esc(thread_id)}</code> has no pending review interrupt.</p>
<p>The thread may not exist, or the graph has already completed.</p>
<p><a href="/">Back to index</a></p>
</body></html>""",
                status_code=404,
            )

        # Extract payload from interrupt value
        payload: dict = state.interrupts[0].value or {}
        kind: str = payload.get("kind", "")
        diff_ref: str = payload.get("diff_ref", "")
        findings: list[str] = payload.get("findings", []) or []
        eval_score: float | None = payload.get("eval_score", None)

        # Content negotiation
        accept = request.headers.get("accept", "")
        if "application/json" in accept:
            return JSONResponse({
                "kind": kind,
                "diff_ref": diff_ref,
                "findings": findings,
                "eval_score": eval_score,
                "thread_id": thread_id,
            })

        return HTMLResponse(
            _render_review_page(thread_id, kind, diff_ref, findings, eval_score)
        )

    # ── GET /review.json ──────────────────────────────────────────────────

    @app.get("/review.json")
    def get_review_json(thread_id: str):
        """
        JSON variant of /review — returns interrupt payload as JSON.

        Useful for CLI/programmatic access without setting Accept headers.
        Returns 404 JSON if no pending interrupt.
        """
        config = {"configurable": {"thread_id": thread_id}}

        try:
            state = graph.get_state(config)
        except Exception as exc:
            return JSONResponse(
                {"error": f"failed to get state: {exc}", "thread_id": thread_id},
                status_code=500,
            )

        if not state.interrupts:
            return JSONResponse(
                {"error": "no pending interrupt", "thread_id": thread_id},
                status_code=404,
            )

        payload: dict = state.interrupts[0].value or {}
        return JSONResponse({
            "kind": payload.get("kind", ""),
            "diff_ref": payload.get("diff_ref", ""),
            "findings": payload.get("findings", []) or [],
            "eval_score": payload.get("eval_score", None),
            "thread_id": thread_id,
        })

    # ── POST /approve ─────────────────────────────────────────────────────

    @app.post("/approve", response_class=HTMLResponse)
    def post_approve(thread_id: str = Form(...)) -> HTMLResponse:
        """
        Resume the graph with action="approve".

        Sends: graph.invoke(Command(resume={"action": "approve"}), config)

        第3条 / FR-5.3 — side-effect-free web layer:
            This endpoint ONLY forwards the resume signal to the graph.
            merge_worktree() is called inside graph/nodes.py::review() approve
            branch — NEVER here. The web layer has no git operations, no
            subprocess calls, no file writes.

        Returns an HTML page showing the resulting decision.
        """
        config = {"configurable": {"thread_id": thread_id}}
        # Forward Command to the graph — all merge logic is in the graph node.
        result = graph.invoke(Command(resume={"action": "approve"}), config)
        decision: str = (result.get("decision", "unknown") if result else "unknown")
        return HTMLResponse(_render_decision_page(thread_id, decision, "approve"))

    # ── POST /reject ──────────────────────────────────────────────────────

    @app.post("/reject", response_class=HTMLResponse)
    def post_reject(thread_id: str = Form(...)) -> HTMLResponse:
        """
        Resume the graph with action="reject".

        Sends: graph.invoke(Command(resume={"action": "reject"}), config)

        第3条: reject does NOT merge. The graph's review node routes back
        to build (no merge_worktree call on this path). Main branch unchanged.

        After reject, the graph loops back: build → verify → eval → review
        (another interrupt). The state at the next interrupt has decision="rejected".

        Returns an HTML page showing the resulting decision with a link to
        the next review interrupt.
        """
        config = {"configurable": {"thread_id": thread_id}}
        # Forward Command to the graph — no merge on reject (第3条).
        result = graph.invoke(Command(resume={"action": "reject"}), config)
        decision: str = (result.get("decision", "unknown") if result else "unknown")
        return HTMLResponse(_render_decision_page(thread_id, decision, "reject"))

    return app


# ---------------------------------------------------------------------------
# Standalone entry point (N2: localhost only, no external services)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    # N2: localhost only (127.0.0.1), single process, no external notifications.
    # Creates default graph via build_graph() using state.db in current directory.
    # CLI resume coexists: graph.invoke(Command(resume=...), config) also works.
    _standalone_app = create_app()
    uvicorn.run(_standalone_app, host="127.0.0.1", port=8765)
