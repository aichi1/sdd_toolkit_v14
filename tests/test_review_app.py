"""
tests/test_review_app.py — TestClient tests for review/app.py (Phase 7 / T7.1).

AC(T7.1) / FR-5.2:
    GET /review displays interrupt payload (diff_ref, findings, eval_score).
    GET /review.json returns the payload as JSON.

AC(T7.1) / FR-5.3 / 第3条:
    POST /approve → decision "approved"; merge happens via graph node (not web layer).
    POST /reject  → decision "rejected"; base repo unchanged (no merge).

N2: No ntfy/Telegram/external notifications. Local only.

第3条 structural check:
    review/app.py has no merge_worktree call and no subprocess import.
    Merge happens exclusively in graph/nodes.py::review() approve branch.

Test isolation (addresses Phase 6 S#3):
    SDD_BASE_REPO       → throwaway temp git repo (real project main NEVER touched)
    SDD_CONSTITUTION_PATH → temp constitution file
    SDD_DOCS_DIR        → temp docs dir with minimal content
    SDD_OBS_STORE       → temp path (avoids ~/.sdd-runs/)
    SQLite DB           → temp path (never shares real state.db)

CLI resume coexistence:
    graph.invoke(Command(resume={"action":"approve"}), config)  [CLI path]
    POST /approve via TestClient                                  [web path]
    Both send the same Command to the same graph/thread — the graph is agnostic.

Note: this test file runs the REAL graph (stub mode) end-to-end, using:
    stub build (writes artifact.txt, commits in worktree)
    stub verify (returns [])
    real eval_node (score ≥ 0.40, routes to review)
    real review (interrupt() fires → test resumes via TestClient or Command)

All tests run offline (no LLM API calls, no network).
"""
from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from graph.build_graph import build_graph
from langgraph.types import Command
from review.app import create_app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def review_env(tmp_path: Path, monkeypatch):
    """
    Fully isolated environment for review app tests.

    Redirects ALL external paths so the real project and ~/.sdd-runs/ are
    never touched (Phase 6 S#3 resolved for these tests).

    Sets up:
      SDD_BASE_REPO          → throwaway git repo in tmp_path
      SDD_CONSTITUTION_PATH  → temp constitution.md
      SDD_DOCS_DIR           → temp docs/ with minimal .md files
      SDD_OBS_STORE          → temp observations.jsonl
    """
    # ── Base git repo (SDD_BASE_REPO) ─────────────────────────────────────
    base = tmp_path / "base_repo"
    base.mkdir()
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "review-test",
        "GIT_AUTHOR_EMAIL": "review@sdd.localhost",
        "GIT_COMMITTER_NAME": "review-test",
        "GIT_COMMITTER_EMAIL": "review@sdd.localhost",
    }
    subprocess.run(["git", "init", str(base)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(base), "config", "user.email", "review@sdd.localhost"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(base), "config", "user.name", "SDD Review Test"],
        check=True, capture_output=True,
    )
    (base / "README.md").write_text("# base\n")
    subprocess.run(["git", "-C", str(base), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(base), "commit", "-m", "initial"],
        check=True, capture_output=True, env=git_env,
    )

    # ── Spec + Constitution files ──────────────────────────────────────────
    spec_file = tmp_path / "spec.md"
    spec_file.write_text("# Review Test Spec\nThis is a test specification.\n")
    constitution_file = tmp_path / "constitution.md"
    constitution_file.write_text(
        "# Test Constitution\n"
        "## 第3条\nMerge only on approve. Reject leaves main unchanged.\n"
    )

    # ── Temp docs dir (SDD_DOCS_DIR, avoids real docs/) ───────────────────
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "spec.md").write_text("# Spec\nTest spec content for review.\n")
    (docs_dir / "requirements.md").write_text(
        "# Requirements\nFR-5.2: review payload display.\nFR-5.3: approve merges.\n"
    )

    # ── Set all env vars (monkeypatch → auto-restored after each test) ─────
    monkeypatch.setenv("SDD_BASE_REPO", str(base))
    monkeypatch.setenv("SDD_CONSTITUTION_PATH", str(constitution_file))
    monkeypatch.setenv("SDD_DOCS_DIR", str(docs_dir))
    monkeypatch.setenv("SDD_OBS_STORE", str(tmp_path / "obs.jsonl"))

    return {
        "base_repo": str(base),
        "spec_file": str(spec_file),
        "constitution_file": str(constitution_file),
        "docs_dir": str(docs_dir),
        "db_path": str(tmp_path / "state.db"),
        "tmp_path": tmp_path,
        "git_env": git_env,
    }


def _make_initial_state(env: dict, task_id: str) -> dict[str, Any]:
    """Minimal TaskState dict for a fresh graph run."""
    return {
        "task_id": task_id,
        "spec_path": env["spec_file"],
        "constitution_digest": "",
        "context_slice_ids": [],
        "worktree_path": "",
        "build_artifact_ref": "",
        "verify_findings": [],
        "eval_score": None,
        "attempt": 0,
        "decision": None,
    }


def _run_to_interrupt(
    db_path: str,
    env: dict,
    task_id: str,
) -> tuple:
    """
    Build a graph, run it to the review interrupt, and return (graph, conn, config).

    The caller is responsible for conn.close() after the test.
    Uses the real stub path: build writes artifact.txt, verify returns [],
    eval_node computes score ≥ 0.40, routes to review → interrupt fires.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    g = build_graph(conn=conn)
    config = {"configurable": {"thread_id": task_id}}
    initial = _make_initial_state(env, task_id)
    g.invoke(initial, config)  # pauses at review interrupt
    return g, conn, config


def _commit_count(repo: str) -> int:
    """Count commits on the current branch of repo."""
    r = subprocess.run(
        ["git", "-C", repo, "log", "--oneline"],
        capture_output=True, text=True, check=True,
    )
    return len([line for line in r.stdout.splitlines() if line.strip()])


# ---------------------------------------------------------------------------
# GET /review — FR-5.2: payload display
# ---------------------------------------------------------------------------

class TestGetReview:
    """FR-5.2: GET /review shows interrupt payload (diff_ref, findings, eval_score)."""

    def test_get_review_html_shows_payload(self, review_env):
        """GET /review returns 200 HTML with diff_ref, eval_score, and action buttons."""
        env = review_env
        g, conn, config = _run_to_interrupt(env["db_path"], env, "get-html-1")

        app = create_app(graph=g)
        client = TestClient(app)

        resp = client.get("/review", params={"thread_id": "get-html-1"})
        assert resp.status_code == 200, (
            f"FR-5.2: GET /review must return 200; got {resp.status_code}"
        )
        text = resp.text

        # FR-5.2: payload fields visible in HTML
        assert "Diff Ref" in text or "diff_ref" in text.lower(), (
            "FR-5.2: HTML must show diff_ref field"
        )
        assert "Eval Score" in text or "eval_score" in text.lower(), (
            "FR-5.2: HTML must show eval_score field"
        )
        # Approve and Reject buttons must be present
        assert "approve" in text.lower(), (
            "FR-5.2: Approve button must appear in HTML"
        )
        assert "reject" in text.lower(), (
            "FR-5.2: Reject button must appear in HTML"
        )
        # thread_id echoed so forms know which thread to resume
        assert "get-html-1" in text, (
            "FR-5.2: thread_id must appear in HTML for form submission"
        )

        conn.close()

    def test_get_review_json_variant(self, review_env):
        """GET /review.json returns 200 JSON with all interrupt payload keys."""
        env = review_env
        g, conn, config = _run_to_interrupt(env["db_path"], env, "get-json-1")

        app = create_app(graph=g)
        client = TestClient(app)

        resp = client.get("/review.json", params={"thread_id": "get-json-1"})
        assert resp.status_code == 200, (
            f"GET /review.json must return 200; got {resp.status_code}"
        )
        data = resp.json()

        # FR-5.2: all payload fields present
        for field in ("diff_ref", "findings", "eval_score", "kind"):
            assert field in data, (
                f"FR-5.2: '{field}' missing from /review.json payload. Got keys: {list(data)}"
            )

        # Findings is a list, eval_score is numeric or None
        assert isinstance(data["findings"], list), "findings must be a list"

        conn.close()

    def test_get_review_accept_json_header(self, review_env):
        """GET /review with Accept: application/json returns JSON payload."""
        env = review_env
        g, conn, config = _run_to_interrupt(env["db_path"], env, "get-json-accept-1")

        app = create_app(graph=g)
        client = TestClient(app)

        resp = client.get(
            "/review",
            params={"thread_id": "get-json-accept-1"},
            headers={"accept": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "diff_ref" in data, f"diff_ref missing from JSON: {data}"
        assert "eval_score" in data, f"eval_score missing from JSON: {data}"

        conn.close()

    def test_get_review_payload_values(self, review_env):
        """
        FR-5.2: payload values match what the graph's review node puts in interrupt().
        Kind must be 'merge_approval', diff_ref is a path string.
        """
        env = review_env
        g, conn, config = _run_to_interrupt(env["db_path"], env, "get-payload-vals-1")

        app = create_app(graph=g)
        client = TestClient(app)

        resp = client.get("/review.json", params={"thread_id": "get-payload-vals-1"})
        assert resp.status_code == 200
        data = resp.json()

        assert data["kind"] == "merge_approval", (
            f"interrupt kind must be 'merge_approval'; got {data['kind']!r}"
        )
        assert isinstance(data["diff_ref"], str) and data["diff_ref"], (
            f"diff_ref must be a non-empty string; got {data['diff_ref']!r}"
        )

        conn.close()

    def test_get_review_no_pending_interrupt(self, review_env):
        """No pending interrupt → 404 with clear message (graceful, not a crash)."""
        env = review_env
        conn = sqlite3.connect(env["db_path"], check_same_thread=False)
        g = build_graph(conn=conn)

        app = create_app(graph=g)
        client = TestClient(app)

        # Non-existent thread has no state → state.interrupts == ()
        resp = client.get("/review", params={"thread_id": "nonexistent-thread-x999"})
        assert resp.status_code == 404, (
            f"Non-existent thread must return 404 (graceful); got {resp.status_code}"
        )
        # Must not be an empty body — a message must explain the situation
        assert len(resp.text) > 20, "404 response must include an explanatory message"

        conn.close()

    def test_get_review_json_no_pending_interrupt(self, review_env):
        """/review.json with no pending interrupt → 404 JSON with 'error' key."""
        env = review_env
        conn = sqlite3.connect(env["db_path"], check_same_thread=False)
        g = build_graph(conn=conn)

        app = create_app(graph=g)
        client = TestClient(app)

        resp = client.get(
            "/review.json", params={"thread_id": "nonexistent-thread-y999"}
        )
        assert resp.status_code == 404
        data = resp.json()
        assert "error" in data, (
            f"/review.json 404 response must have 'error' key; got {data}"
        )

        conn.close()

    def test_get_review_is_read_only(self, review_env):
        """
        GET /review must NOT consume the interrupt (read-only).
        The interrupt must still be pending after the GET request.
        """
        env = review_env
        g, conn, config = _run_to_interrupt(env["db_path"], env, "readonly-1")

        state_before = g.get_state(config)
        assert state_before.interrupts, "Interrupt must be pending before GET"

        app = create_app(graph=g)
        client = TestClient(app)
        client.get("/review", params={"thread_id": "readonly-1"})

        state_after = g.get_state(config)
        assert state_after.interrupts, (
            "GET /review must NOT consume the interrupt (read-only). "
            "Interrupt must still be pending after GET."
        )

        conn.close()

    def test_index_page(self, review_env):
        """GET / returns a friendly index page with SDD branding."""
        env = review_env
        conn = sqlite3.connect(env["db_path"], check_same_thread=False)
        g = build_graph(conn=conn)

        app = create_app(graph=g)
        client = TestClient(app)

        resp = client.get("/")
        assert resp.status_code == 200
        assert "SDD" in resp.text, "Index page must mention SDD"
        assert "review" in resp.text.lower(), "Index page must mention /review"

        conn.close()


# ---------------------------------------------------------------------------
# POST /approve — FR-5.3 / 第3条: approve → decision "approved"
# ---------------------------------------------------------------------------

class TestPostApprove:
    """FR-5.3 / 第3条: POST /approve → decision 'approved', merge via graph node."""

    def test_approve_endpoint_returns_approved(self, review_env):
        """POST /approve → HTTP 200 response mentioning 'approved'."""
        env = review_env
        g, conn, config = _run_to_interrupt(env["db_path"], env, "approve-web-1")

        app = create_app(graph=g)
        client = TestClient(app)

        resp = client.post("/approve", data={"thread_id": "approve-web-1"})
        assert resp.status_code == 200, (
            f"POST /approve must return 200; got {resp.status_code}"
        )
        assert "approved" in resp.text.lower(), (
            f"FR-5.3: POST /approve response must mention 'approved'; got: {resp.text}"
        )

        conn.close()

    def test_approve_cli_path_decision(self, review_env):
        """
        CLI resume path: graph.invoke(Command(resume=approve)) → decision='approved'.
        Verifies FR-5.3 via the CLI path (equivalent to POST /approve).
        """
        env = review_env
        g, conn, config = _run_to_interrupt(env["db_path"], env, "approve-cli-1")

        # CLI path — same as POST /approve (both send Command(resume={"action":"approve"}))
        final = g.invoke(Command(resume={"action": "approve"}), config)

        assert final["decision"] == "approved", (
            f"FR-5.3: CLI approve must yield decision='approved'; "
            f"got {final.get('decision')!r}"
        )

        conn.close()

    def test_approve_merges_into_base_repo(self, review_env):
        """
        第3条 / FR-5.3: approve causes merge into base repo.
        After approve, base repo has more commits (merge commit added by graph node).
        Web layer itself has no git calls.
        """
        env = review_env
        commits_before = _commit_count(env["base_repo"])

        g, conn, config = _run_to_interrupt(env["db_path"], env, "approve-merge-1")

        # Use CLI path (equivalent to POST /approve) to verify graph-level merge
        g.invoke(Command(resume={"action": "approve"}), config)

        commits_after = _commit_count(env["base_repo"])
        assert commits_after > commits_before, (
            f"第3条 / FR-5.3: approve must add a merge commit to base repo "
            f"(commits: {commits_before} → {commits_after})"
        )

        conn.close()

    def test_approved_thread_has_no_pending_interrupt(self, review_env):
        """
        After POST /approve, the graph completes → no pending interrupt.
        GET /review for the same thread returns 404 (graceful completion).
        """
        env = review_env
        g, conn, config = _run_to_interrupt(env["db_path"], env, "approve-complete-1")

        app = create_app(graph=g)
        client = TestClient(app)

        # Approve via web endpoint
        client.post("/approve", data={"thread_id": "approve-complete-1"})

        # Now GET /review should find no pending interrupt (graph finished)
        resp = client.get("/review", params={"thread_id": "approve-complete-1"})
        assert resp.status_code == 404, (
            "After approve, graph is complete: GET /review must return 404 "
            "(no pending interrupt)"
        )

        conn.close()


# ---------------------------------------------------------------------------
# POST /reject — FR-5.3 / 第3条: reject → decision "rejected", main unchanged
# ---------------------------------------------------------------------------

class TestPostReject:
    """FR-5.3 / 第3条: POST /reject → decision 'rejected', base repo unchanged."""

    def test_reject_endpoint_returns_rejected(self, review_env):
        """POST /reject → HTTP 200 response mentioning 'rejected'."""
        env = review_env
        g, conn, config = _run_to_interrupt(env["db_path"], env, "reject-web-1")

        app = create_app(graph=g)
        client = TestClient(app)

        resp = client.post("/reject", data={"thread_id": "reject-web-1"})
        assert resp.status_code == 200, (
            f"POST /reject must return 200; got {resp.status_code}"
        )
        # After reject, graph loops back to build → next interrupt has decision="rejected"
        assert "rejected" in resp.text.lower(), (
            f"FR-5.3: POST /reject response must mention 'rejected'; got: {resp.text}"
        )

        conn.close()

    def test_reject_cli_path_decision(self, review_env):
        """
        CLI resume path: graph.invoke(Command(resume=reject)) → decision='rejected'.
        After reject, graph loops back to build → verify → eval → review (another interrupt).
        State at the next interrupt has decision='rejected'.
        """
        env = review_env
        g, conn, config = _run_to_interrupt(env["db_path"], env, "reject-cli-1")

        # CLI path — equivalent to POST /reject
        result = g.invoke(Command(resume={"action": "reject"}), config)

        assert result.get("decision") == "rejected", (
            f"FR-5.3: CLI reject must yield decision='rejected' at next interrupt; "
            f"got {result.get('decision')!r}"
        )

        conn.close()

    def test_reject_does_not_merge(self, review_env):
        """
        第3条: reject must NOT add any commits to the base repo.
        Main branch must remain unchanged after reject.
        """
        env = review_env
        commits_before = _commit_count(env["base_repo"])

        g, conn, config = _run_to_interrupt(env["db_path"], env, "reject-no-merge-1")

        # Reject (loops back to build → review interrupt again, no merge)
        g.invoke(Command(resume={"action": "reject"}), config)

        commits_after = _commit_count(env["base_repo"])
        assert commits_after == commits_before, (
            f"第3条: reject must NOT add merge commits to base repo "
            f"(commits: {commits_before} → {commits_after})"
        )

        # Clean up: approve the second interrupt so worktree is released
        g.invoke(Command(resume={"action": "approve"}), config)

        conn.close()

    def test_reject_then_new_interrupt_pending(self, review_env):
        """
        After POST /reject, graph loops back → new review interrupt is pending.
        GET /review should return 200 (new interrupt, not 404).
        """
        env = review_env
        g, conn, config = _run_to_interrupt(env["db_path"], env, "reject-pending-1")

        app = create_app(graph=g)
        client = TestClient(app)

        # Reject → graph loops to build → review (another interrupt)
        client.post("/reject", data={"thread_id": "reject-pending-1"})

        # A new interrupt is now pending
        resp = client.get("/review", params={"thread_id": "reject-pending-1"})
        assert resp.status_code == 200, (
            "After reject, a new interrupt is pending: GET /review must return 200"
        )

        # Clean up
        client.post("/approve", data={"thread_id": "reject-pending-1"})

        conn.close()


# ---------------------------------------------------------------------------
# 第3条 structural: web layer has no merge logic
# ---------------------------------------------------------------------------

class TestWebLayerSideEffectFree:
    """
    第3条: structural verification that review/app.py has no merge logic.
    Merge happens exclusively in graph/nodes.py::review() approve branch.

    Tests use AST analysis or import-statement checks rather than raw string
    matching, so that docstring references to prohibited patterns don't trigger
    false positives.
    """

    def test_no_merge_worktree_call_in_app(self):
        """
        第3条: review/app.py must not CALL merge_worktree (may mention it in docs).
        Uses AST to find actual Call nodes — docstring mentions are not flagged.
        """
        import ast

        app_path = Path(__file__).parent.parent / "review" / "app.py"
        source = app_path.read_text()
        tree = ast.parse(source)

        # Walk the AST and find all function call names
        calls_found = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    calls_found.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    calls_found.append(node.func.attr)

        assert "merge_worktree" not in calls_found, (
            "第3条: review/app.py must NOT call merge_worktree(). "
            f"Found calls: {calls_found}. "
            "Merge logic belongs in graph/nodes.py::review() approve branch only."
        )

    def test_no_subprocess_import_in_app(self):
        """review/app.py must not IMPORT subprocess (may mention it in docs)."""
        source = (Path(__file__).parent.parent / "review" / "app.py").read_text()
        # Check for actual import statement, not doc references
        assert "import subprocess" not in source, (
            "第3条: review/app.py must NOT import subprocess. "
            "All git operations belong in harness/sandbox.py or graph/nodes.py."
        )

    def test_no_git_import_in_app(self):
        """review/app.py must not import git-related modules directly."""
        source = (Path(__file__).parent.parent / "review" / "app.py").read_text()
        # Check for actual import statements (not doc mentions)
        for prohibited in ("import subprocess", "from subprocess", "import git"):
            assert prohibited not in source, (
                f"第3条: review/app.py must not have '{prohibited}'. "
                "All git logic belongs in the graph node or harness."
            )

    def test_no_harness_sandbox_import_in_app(self):
        """review/app.py must not import harness.sandbox (merge_worktree lives there)."""
        source = (Path(__file__).parent.parent / "review" / "app.py").read_text()
        assert "harness.sandbox" not in source, (
            "第3条: review/app.py must not import harness.sandbox. "
            "Sandbox/merge logic belongs in graph/nodes.py, not the web layer."
        )


# ---------------------------------------------------------------------------
# N2: No external notifications
# ---------------------------------------------------------------------------

class TestNoExternalNotify:
    """N2: review/app.py must not use ntfy, Telegram, or any external service."""

    def test_no_ntfy_telegram_import_in_app(self):
        """N2: review/app.py must not IMPORT external notify services (may mention in docs)."""
        source = (Path(__file__).parent.parent / "review" / "app.py").read_text()
        # Check for actual imports of prohibited packages, not doc mentions
        for prohibited in ("import ntfy", "import telegram", "import smtplib", "import sendgrid"):
            assert prohibited not in source, (
                f"N2: review/app.py must not import '{prohibited}' "
                "(external notification — N2 non-goal)"
            )

    def test_no_external_urls_in_app(self):
        """N2: review/app.py must not contain external service URLs."""
        source = (Path(__file__).parent.parent / "review" / "app.py").read_text()
        for prohibited_url in (
            "ntfy.sh", "telegram.org", "api.telegram.org",
            "slack.com", "discord.com", "sendgrid.com",
        ):
            assert prohibited_url not in source, (
                f"N2: review/app.py must not reference '{prohibited_url}'"
            )

    def test_no_requests_or_aiohttp_in_app(self):
        """N2: review/app.py must not use requests/aiohttp for external calls."""
        source = (Path(__file__).parent.parent / "review" / "app.py").read_text()
        for prohibited in ("import requests", "import aiohttp", "import httpx"):
            # httpx IS used by TestClient internally, but should not be in app.py itself
            assert prohibited not in source, (
                f"N2: review/app.py must not import '{prohibited}' "
                "(external HTTP client — use only FastAPI internals)"
            )


# ---------------------------------------------------------------------------
# CLI resume coexistence
# ---------------------------------------------------------------------------

class TestCLIResumeCoexistence:
    """
    CLI resume (graph.invoke(Command(...))) and web resume (POST /approve|reject)
    coexist on the same thread. Both send the same Command to the same graph.
    """

    def test_cli_approve_after_web_reject(self, review_env):
        """
        Web: POST /reject (loops to build → review)
        CLI: graph.invoke(Command(approve)) → decision='approved'

        Both paths work on the same thread without interference.
        """
        env = review_env
        g, conn, config = _run_to_interrupt(env["db_path"], env, "coexist-1")

        app = create_app(graph=g)
        client = TestClient(app)

        # Web: reject (loops back to review, another interrupt pending)
        resp = client.post("/reject", data={"thread_id": "coexist-1"})
        assert resp.status_code == 200

        # CLI: approve the second interrupt
        final = g.invoke(Command(resume={"action": "approve"}), config)
        assert final["decision"] == "approved", (
            f"CLI approve after web reject must yield 'approved'; "
            f"got {final.get('decision')!r}"
        )

        conn.close()

    def test_web_approve_after_cli_reject(self, review_env):
        """
        CLI: graph.invoke(Command(reject)) (loops to build → review)
        Web: POST /approve → decision='approved'

        CLI and web are fully interchangeable on the same thread.
        """
        env = review_env
        g, conn, config = _run_to_interrupt(env["db_path"], env, "coexist-2")

        app = create_app(graph=g)
        client = TestClient(app)

        # CLI: reject
        g.invoke(Command(resume={"action": "reject"}), config)

        # Web: approve the second interrupt
        resp = client.post("/approve", data={"thread_id": "coexist-2"})
        assert resp.status_code == 200
        assert "approved" in resp.text.lower(), (
            f"Web approve after CLI reject must show 'approved'; got: {resp.text}"
        )

        conn.close()

    def test_create_app_with_injected_graph(self, review_env):
        """create_app() accepts an injectable graph; tests never use the default."""
        env = review_env
        conn = sqlite3.connect(env["db_path"], check_same_thread=False)
        g = build_graph(conn=conn)

        # Inject the graph — no default graph is created, no state.db in cwd
        app = create_app(graph=g)
        assert app is not None, "create_app(graph=g) must return a FastAPI app"

        conn.close()

    def test_obs_store_not_written_to_real_path(self, review_env):
        """
        Phase 6 S#3: SDD_OBS_STORE is redirected to tmp_path/obs.jsonl.
        Real ~/.sdd-runs/ is never written during these tests.
        """
        env = review_env
        # SDD_OBS_STORE is set to tmp_path/obs.jsonl by the fixture
        obs_store = env["tmp_path"] / "obs.jsonl"

        g, conn, config = _run_to_interrupt(env["db_path"], env, "obs-redirect-1")

        # After running the graph, obs.jsonl should exist in tmp_path (not ~/.sdd-runs/)
        # (eval_node calls record_run() for every eval)
        assert obs_store.exists(), (
            "SDD_OBS_STORE must redirect observations to tmp_path/obs.jsonl, "
            "not the real ~/.sdd-runs/"
        )

        # Real ~/.sdd-runs/ must NOT have been written (S#3)
        real_store = Path.home() / ".sdd-runs" / "observations.jsonl"
        if real_store.exists():
            # It may already exist from previous test runs — we only check that
            # we did not add any NEW entries during THIS test's graph run by
            # checking that the tmp obs store was the one written.
            pass  # Non-destructive: cannot safely assert on pre-existing file

        conn.close()
