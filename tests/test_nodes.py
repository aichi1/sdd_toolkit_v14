"""
tests/test_nodes.py — Unit tests for graph/nodes.py.

Tests node state-input/output contracts in isolation.
Where nodes call external systems (carve_worktree, merge_worktree, interrupt),
we monkeypatch the name imported into graph.nodes so the unit stays fast.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

import graph.nodes as nodes_module
from graph.nodes import build, review, spec_load


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_state(**overrides) -> dict:
    """Minimal valid TaskState dict for node unit tests."""
    state: dict[str, Any] = {
        "task_id": "unit-task",
        "spec_path": "/tmp/spec.md",      # overridden per test
        "constitution_digest": "",
        "context_slice_ids": [],
        "worktree_path": "",
        "build_artifact_ref": "",
        "verify_findings": [],
        "eval_score": None,
        "attempt": 0,
        "decision": None,
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# spec_load
# ---------------------------------------------------------------------------

class TestSpecLoad:
    def test_spec_load_sets_path_fields_only(self, tmp_path: Path, monkeypatch):
        """
        spec_load must return spec_path, constitution_digest, worktree_path.
        No body content (第2条).
        """
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# spec")
        constitution_file = tmp_path / "constitution.md"
        constitution_file.write_text("# constitution")

        monkeypatch.setenv("SDD_CONSTITUTION_PATH", str(constitution_file))
        # Avoid real git calls
        monkeypatch.setattr(
            nodes_module, "carve_worktree",
            lambda task_id, base_repo=".": str(tmp_path / "wt"),
        )

        result = spec_load(_base_state(spec_path=str(spec_file)))

        assert "spec_path" in result
        assert "constitution_digest" in result
        assert "worktree_path" in result
        # No body content
        for forbidden in ("body", "diff", "log", "content", "text", "code"):
            assert forbidden not in result, f"Body field {forbidden!r} in spec_load result"

    def test_spec_load_digest_is_short(self, tmp_path: Path, monkeypatch):
        """
        constitution_digest must be ≤30 chars (第2条: short hash, not full text).
        Format: sha256:<16 hex chars> = 23 chars total.
        """
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("spec")
        constitution_file = tmp_path / "constitution.md"
        constitution_file.write_text("constitution text here")

        monkeypatch.setenv("SDD_CONSTITUTION_PATH", str(constitution_file))
        monkeypatch.setattr(
            nodes_module, "carve_worktree",
            lambda task_id, base_repo=".": str(tmp_path / "wt"),
        )

        result = spec_load(_base_state(spec_path=str(spec_file)))
        digest = result["constitution_digest"]

        assert len(digest) <= 30, f"Digest too long ({len(digest)}): {digest!r}"
        assert digest.startswith("sha256:"), f"Digest must start with 'sha256:': {digest!r}"

    def test_spec_load_idempotent_skips_recarve(self, tmp_path: Path, monkeypatch):
        """
        If worktree_path is already set and exists, spec_load must not re-carve
        (interrupt-resume idempotency, 第3条 / NFR-2).
        """
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("spec")
        constitution_file = tmp_path / "constitution.md"
        constitution_file.write_text("constitution")

        # Existing worktree path that "exists" on disk
        existing_wt = tmp_path / "existing-wt"
        existing_wt.mkdir()

        carve_calls: list = []
        monkeypatch.setenv("SDD_CONSTITUTION_PATH", str(constitution_file))
        monkeypatch.setattr(
            nodes_module, "carve_worktree",
            lambda task_id, base_repo=".": carve_calls.append(task_id) or "NEW",
        )

        result = spec_load(
            _base_state(spec_path=str(spec_file), worktree_path=str(existing_wt))
        )

        assert len(carve_calls) == 0, "carve_worktree must not be called when worktree exists"
        assert result["worktree_path"] == str(existing_wt)

    def test_fr11_spec_path_and_digest_nonempty(self, tmp_path: Path, monkeypatch):
        """
        FR-1.1: TaskState.spec_path and constitution_digest must both be non-empty
        after spec_load, and no body content must appear in state.

        AC (FR-1.1): spec_path non-empty, constitution_digest non-empty,
        body text NOT in state.
        """
        spec_file = tmp_path / "spec.md"
        spec_file.write_text("# Project Spec\n\n## T1: First task\n\nDo the thing.")
        constitution_file = tmp_path / "constitution.md"
        constitution_file.write_text("# Constitution\n\n## 第1条: Test\n- 原則: test\n")

        monkeypatch.setenv("SDD_CONSTITUTION_PATH", str(constitution_file))
        monkeypatch.setattr(
            nodes_module, "carve_worktree",
            lambda task_id, base_repo=".": str(tmp_path / "wt"),
        )

        result = spec_load(_base_state(spec_path=str(spec_file)))

        # FR-1.1: spec_path non-empty
        assert result.get("spec_path"), (
            "FR-1.1: spec_path must be non-empty in state after spec_load"
        )
        # FR-1.1: constitution_digest non-empty
        digest = result.get("constitution_digest", "")
        assert digest, (
            "FR-1.1: constitution_digest must be non-empty in state after spec_load"
        )
        # FR-1.1: digest is a short hash (not full body text)
        assert len(digest) < 100, (
            f"FR-1.1: constitution_digest must be a short hash, not full body "
            f"(got {len(digest)} chars)"
        )
        assert digest.startswith("sha256:"), (
            f"FR-1.1: constitution_digest must start with 'sha256:'; got {digest!r}"
        )
        # FR-1.1 / 第2条: body text must NOT appear in state
        body_text = constitution_file.read_text()
        for key, val in result.items():
            if isinstance(val, str):
                assert val != body_text, (
                    f"FR-1.1 violation: state[{key!r}] is the full constitution body"
                )
                # Verify: the body marker text "# Constitution" is not stored in state
                assert "# Constitution" not in val, (
                    f"FR-1.1 / 第2条: body heading found in state[{key!r}] = {val!r}"
                )


# ---------------------------------------------------------------------------
# build (stub)
# ---------------------------------------------------------------------------

class TestBuild:
    @pytest.fixture
    def wt_repo(self, tmp_path: Path) -> str:
        """Minimal git repo to act as the worktree (build commits here)."""
        repo = tmp_path / "wt"
        repo.mkdir()
        import os
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t.com",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t.com"}
        subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "t@t.com"],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "T"],
            check=True, capture_output=True,
        )
        # Initial commit required before we can commit more
        (repo / ".gitkeep").write_text("")
        subprocess.run(
            ["git", "-C", str(repo), "add", "."], check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "commit", "-m", "init"],
            check=True, capture_output=True, env=env,
        )
        return str(repo)

    def test_build_writes_artifact_file(self, wt_repo: str):
        """build() must write artifact.txt with the correct content."""
        state = _base_state(
            task_id="build-test",
            worktree_path=wt_repo,
            attempt=2,
        )
        result = build(state)

        artifact = Path(wt_repo) / "artifact.txt"
        assert artifact.exists(), "artifact.txt must be created in worktree"
        text = artifact.read_text()
        assert "STUB artifact for build-test" in text, f"Content mismatch: {text!r}"
        assert "attempt 2" in text, f"Attempt not in content: {text!r}"

    def test_build_returns_correct_dict(self, wt_repo: str):
        """
        build() must return build_artifact_ref (path) and verify_findings=None.

        Phase 4 S1 resolution: build() returns None (not []) for verify_findings
        so that the reduce_findings reducer resets findings to [] for this new
        round.  An empty list [] was a no-op with the old operator.add reducer
        and could not signal "reset stale findings from the previous round".
        """
        state = _base_state(worktree_path=wt_repo, attempt=0)
        result = build(state)

        assert "build_artifact_ref" in result
        assert result["build_artifact_ref"] == str(Path(wt_repo) / "artifact.txt")
        assert result["verify_findings"] is None, (
            "Phase 4 S1: verify_findings must be None (triggers reduce_findings "
            "reset to [] for this new round, not a no-op [])"
        )


# ---------------------------------------------------------------------------
# review
# ---------------------------------------------------------------------------

class TestReview:
    def _review_state(self) -> dict:
        return _base_state(
            worktree_path="/tmp/wt-review",
            build_artifact_ref="/tmp/wt-review/artifact.txt",
            verify_findings=["finding-A"],
            eval_score=0.85,
            attempt=1,
        )

    def test_review_reject_does_not_call_merge(self, monkeypatch):
        """
        FR-5.3 / 第3条: on reject, merge_worktree must NOT be called.
        """
        merge_calls: list = []
        monkeypatch.setattr(nodes_module, "interrupt", lambda p: {"action": "reject"})
        monkeypatch.setattr(
            nodes_module, "merge_worktree",
            lambda wt, base_repo=".": merge_calls.append(wt),
        )

        result = review(self._review_state())

        assert len(merge_calls) == 0, (
            "merge_worktree must not be called on reject (第3条 / FR-5.3)"
        )

    def test_review_reject_increments_attempt(self, monkeypatch):
        """reject must route back to build with attempt+1."""
        monkeypatch.setattr(nodes_module, "interrupt", lambda p: {"action": "reject"})
        monkeypatch.setattr(nodes_module, "merge_worktree", lambda wt, base_repo=".": None)

        state = self._review_state()
        result = review(state)

        assert result.update["attempt"] == state["attempt"] + 1
        assert result.update["decision"] == "rejected"
        assert result.goto == "build"

    def test_review_approve_calls_merge_exactly_once(self, monkeypatch):
        """
        第3条: on approve, merge_worktree must be called exactly once.
        """
        merge_calls: list = []
        monkeypatch.setattr(nodes_module, "interrupt", lambda p: {"action": "approve"})
        monkeypatch.setattr(
            nodes_module, "merge_worktree",
            lambda wt, base_repo=".": merge_calls.append(wt),
        )

        result = review(self._review_state())

        assert len(merge_calls) == 1, (
            f"merge_worktree must be called exactly once on approve; got {len(merge_calls)}"
        )

    def test_review_approve_sets_decision_approved(self, monkeypatch):
        """On approve, returned Command must update decision to 'approved'."""
        monkeypatch.setattr(nodes_module, "interrupt", lambda p: {"action": "approve"})
        monkeypatch.setattr(nodes_module, "merge_worktree", lambda wt, base_repo=".": None)

        from langgraph.graph import END
        result = review(self._review_state())

        assert result.update["decision"] == "approved"
        assert result.goto == END
