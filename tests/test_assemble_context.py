"""
tests/test_assemble_context.py — Tests for assemble_context node and assemble_prompt.

Coverage:
  第2条: assemble_context returns context_slice_ids (list[str]), no body text.
  FR-2.1: context_slice_ids count < total chunks in the indexed collection.
  FR-2.2: assemble_prompt produces an identical head block for the same
          constitution_digest across two calls (cache-hit condition).
  FR-2.2: two calls to assemble_context with identical state yield identical
          context_slice_ids (determinism of LocalHashEmbedding + ordering).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from graph.nodes import assemble_context, assemble_prompt, _IMMUTABLE_HEADER, _SLICES_HEADER
from mcp_servers.context_server import (
    _DEFAULT_K,
    _build_collection,
    _reset_collection_cache,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_docs(tmp_path: Path) -> Path:
    """
    Minimal docs/ directory: enough headings so total chunks > _DEFAULT_K
    (ensuring FR-2.1 — returned count < total — can be tested).
    """
    docs = tmp_path / "docs"
    docs.mkdir()

    (docs / "requirements.md").write_text(
        "# Requirements\n\n"
        "## FR-1 Constitutional Layer\n\nSpec is truth.\n\n"
        "## FR-2 Context Engineering\n\nSlice selection.\n\n"
        "## FR-3 PEV Harness\n\nBuild in worktree.\n\n"
        "## FR-4 Eval\n\nRegression detection.\n\n"
        "## FR-5 Approval Gate\n\nHuman-in-the-loop.\n",
        encoding="utf-8",
    )
    (docs / "plan.md").write_text(
        "# Plan\n\n"
        "## Architecture\n\nLangGraph + Agent SDK.\n\n"
        "## MCP Servers\n\ncontext_server and constitution_server.\n\n"
        "## State Schema\n\nLean: paths and IDs.\n",
        encoding="utf-8",
    )
    (docs / "constitution.md").write_text(
        "# Constitution\n\n"
        "## Article 2\n\nState stays lean.\n\n"
        "## Article 6\n\nReuse existing assets.\n",
        encoding="utf-8",
    )
    return docs


@pytest.fixture(autouse=True)
def clear_cache_around_test():
    """Reset collection cache before and after every test."""
    _reset_collection_cache()
    yield
    _reset_collection_cache()


@pytest.fixture
def base_state(tmp_docs: Path) -> dict[str, Any]:
    """Minimal TaskState dict for assemble_context unit tests."""
    return {
        "task_id": "test-task-context",
        "spec_path": str(tmp_docs / "requirements.md"),
        "constitution_digest": "sha256:abcdef01",
        "context_slice_ids": [],
        "worktree_path": "",
        "build_artifact_ref": "",
        "verify_findings": [],
        "eval_score": None,
        "attempt": 0,
        "decision": None,
    }


# ---------------------------------------------------------------------------
# assemble_prompt (pure function)
# ---------------------------------------------------------------------------

class TestAssemblePrompt:
    def test_fr22_head_block_identical_same_digest(self):
        """
        FR-2.2: The head block (before [TASK-SPECIFIC SLICES]) must be
        byte-identical for the same constitution_digest, regardless of slice_ids.
        This is the prompt-cache hit condition.
        """
        digest = "sha256:deadbeef12345678"
        ids_a = ["requirements::000", "plan::001"]
        ids_b = ["constitution::002", "tasks::000"]

        prompt_a = assemble_prompt(digest, ids_a)
        prompt_b = assemble_prompt(digest, ids_b)

        # Extract head block (everything up to and NOT including the slices header)
        head_a = prompt_a.split(_SLICES_HEADER)[0]
        head_b = prompt_b.split(_SLICES_HEADER)[0]

        assert head_a == head_b, (
            "FR-2.2: head blocks must be byte-identical for same constitution_digest.\n"
            f"  Head A: {head_a!r}\n"
            f"  Head B: {head_b!r}"
        )

    def test_fr22_identical_input_identical_full_prompt(self):
        """
        FR-2.2: same (digest, slice_ids) pair produces byte-identical output.
        This is the STRICT cache condition.
        """
        digest = "sha256:aabbcc"
        ids = ["requirements::001", "plan::000"]

        p1 = assemble_prompt(digest, ids)
        p2 = assemble_prompt(digest, ids)

        assert p1 == p2, "assemble_prompt must be a pure deterministic function"

    def test_immutable_block_comes_first(self):
        """
        FR-2.2 ordering: the immutable constitution block must appear BEFORE
        any task-specific slice content.
        """
        prompt = assemble_prompt("sha256:abc", ["req::001"])
        immutable_pos = prompt.find(_IMMUTABLE_HEADER)
        slices_pos = prompt.find(_SLICES_HEADER)

        assert immutable_pos != -1, f"{_IMMUTABLE_HEADER!r} not found in prompt"
        assert slices_pos != -1, f"{_SLICES_HEADER!r} not found in prompt"
        assert immutable_pos < slices_pos, (
            "Immutable block must appear before task-specific slices "
            "(FR-2.2 prompt-cache head-block ordering)"
        )

    def test_digest_appears_in_head(self):
        """constitution_digest value must appear in the head block."""
        digest = "sha256:unique-test-value"
        prompt = assemble_prompt(digest, [])
        assert digest in prompt, f"Digest {digest!r} must appear in the prompt"

    def test_slice_ids_appear_after_header(self):
        """Slice IDs must appear after the [TASK-SPECIFIC SLICES] header."""
        ids = ["requirements::002", "constitution::001"]
        prompt = assemble_prompt("sha256:xyz", ids)
        slices_section = prompt.split(_SLICES_HEADER, 1)[-1]
        for sid in ids:
            assert sid in slices_section, (
                f"Slice ID {sid!r} must appear in the slices section"
            )

    def test_empty_slice_ids_handled(self):
        """assemble_prompt must not crash with empty slice list."""
        prompt = assemble_prompt("sha256:abc", [])
        assert _IMMUTABLE_HEADER in prompt
        assert _SLICES_HEADER in prompt


# ---------------------------------------------------------------------------
# assemble_context (graph node)
# ---------------------------------------------------------------------------

class TestAssembleContext:
    def test_article2_returns_ids_only(self, base_state: dict, tmp_docs: Path, monkeypatch):
        """
        第2条: assemble_context must return only context_slice_ids (IDs),
        never body text of spec chunks.
        """
        monkeypatch.setenv("SDD_DOCS_DIR", str(tmp_docs))
        result = assemble_context(base_state)

        assert "context_slice_ids" in result, (
            "assemble_context must return 'context_slice_ids' key"
        )
        # No body-content keys
        forbidden = {"body", "content", "text", "chunks", "documents", "diff", "code"}
        for key in forbidden:
            assert key not in result, (
                f"第2条: body-content key {key!r} must not appear in assemble_context result"
            )

    def test_context_slice_ids_is_list_of_str(
        self, base_state: dict, tmp_docs: Path, monkeypatch
    ):
        """context_slice_ids must be a list of str (chunk IDs)."""
        monkeypatch.setenv("SDD_DOCS_DIR", str(tmp_docs))
        result = assemble_context(base_state)

        ids = result["context_slice_ids"]
        assert isinstance(ids, list), f"Expected list, got {type(ids)!r}"
        for item in ids:
            assert isinstance(item, str), (
                f"第2条: expected str chunk ID, got {type(item)!r}: {item!r}"
            )

    def test_fr21_returned_count_less_than_total(
        self, base_state: dict, tmp_docs: Path, monkeypatch
    ):
        """
        FR-2.1: context_slice_ids count must be < total chunks in the collection.
        This confirms that slice selection is active (not all chunks returned).
        """
        monkeypatch.setenv("SDD_DOCS_DIR", str(tmp_docs))
        _, total = _build_collection(tmp_docs)

        result = assemble_context(base_state)
        ids = result["context_slice_ids"]

        assert total > 0, "Collection must be non-empty for this test to be meaningful"
        assert len(ids) < total, (
            f"FR-2.1 violation: assemble_context returned {len(ids)} IDs "
            f"== total {total}. Selection must yield fewer than all chunks."
        )

    def test_fr22_same_state_same_ids_twice(
        self, base_state: dict, tmp_docs: Path, monkeypatch
    ):
        """
        FR-2.2: calling assemble_context twice with the SAME state and same
        docs directory must yield identical context_slice_ids.
        Determinism of LocalHashEmbedding + sorted ordering guarantees this.
        """
        monkeypatch.setenv("SDD_DOCS_DIR", str(tmp_docs))
        result1 = assemble_context(base_state)
        result2 = assemble_context(base_state)

        ids1 = result1["context_slice_ids"]
        ids2 = result2["context_slice_ids"]

        assert ids1 == ids2, (
            "FR-2.2: assemble_context must be deterministic — "
            "same state must yield same context_slice_ids in the same order"
        )

    def test_fr22_same_ids_yields_same_head_block(
        self, base_state: dict, tmp_docs: Path, monkeypatch
    ):
        """
        FR-2.2 end-to-end: same state → same IDs → same assemble_prompt head block.
        This is the complete prompt-cache hit condition.
        """
        monkeypatch.setenv("SDD_DOCS_DIR", str(tmp_docs))

        result1 = assemble_context(base_state)
        result2 = assemble_context(base_state)

        digest = base_state["constitution_digest"]
        prompt1 = assemble_prompt(digest, result1["context_slice_ids"])
        prompt2 = assemble_prompt(digest, result2["context_slice_ids"])

        head1 = prompt1.split(_SLICES_HEADER)[0]
        head2 = prompt2.split(_SLICES_HEADER)[0]

        assert head1 == head2, (
            "FR-2.2 end-to-end: identical state must produce identical prompt "
            "head block (cache-hit condition).\n"
            f"  head1: {head1!r}\n"
            f"  head2: {head2!r}"
        )

    def test_result_keys_are_minimal(
        self, base_state: dict, tmp_docs: Path, monkeypatch
    ):
        """
        assemble_context should return a minimal dict — the node contract
        requires returning only the state keys it updates.
        """
        monkeypatch.setenv("SDD_DOCS_DIR", str(tmp_docs))
        result = assemble_context(base_state)

        # Must have context_slice_ids; may have other update keys
        assert "context_slice_ids" in result, (
            "assemble_context must include context_slice_ids in its return dict"
        )

    def test_handles_empty_docs_gracefully(
        self, base_state: dict, tmp_path: Path, monkeypatch
    ):
        """
        assemble_context must not crash when the docs directory is empty.
        Returns an empty context_slice_ids list.
        """
        empty_docs = tmp_path / "empty_docs"
        empty_docs.mkdir()
        monkeypatch.setenv("SDD_DOCS_DIR", str(empty_docs))

        result = assemble_context(base_state)

        assert result["context_slice_ids"] == [], (
            "Empty docs directory should yield empty context_slice_ids"
        )
