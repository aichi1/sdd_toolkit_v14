"""
tests/test_context_server.py — Tests for mcp_servers/context_server.py.

Coverage:
  FR-2.1: retrieve_slice_ids() returns fewer chunks than total indexed.
  FR-2.2: deterministic ordering — same query yields same result order.
  LocalHashEmbedding: deterministic, network-free, correct shape.
  _chunk_docs: chunks are produced, IDs are stable across two calls.
  spec_slice tool: registered in context_server and has correct name.
  第2条: retrieve_slice_ids returns str IDs only, no body text.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from mcp_servers.context_server import (
    LocalHashEmbedding,
    _build_collection,
    _chunk_docs,
    _registered_tools,
    _reset_collection_cache,
    context_server,
    retrieve_slice_ids,
    spec_slice,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_docs(tmp_path: Path) -> Path:
    """
    A minimal docs/ directory with several markdown files and headings.
    Large enough that k=5 < total chunks (FR-2.1).
    """
    docs = tmp_path / "docs"
    docs.mkdir()

    (docs / "requirements.md").write_text(
        "# Requirements\n\n"
        "## FR-1 Constitutional Layer\n\nSpec must be the single source of truth.\n\n"
        "## FR-2 Context Engineering\n\nOnly relevant slices injected.\n\n"
        "## FR-3 PEV Harness\n\nBuild runs in worktree.\n",
        encoding="utf-8",
    )
    (docs / "plan.md").write_text(
        "# Architecture Plan\n\n"
        "## Nodes\n\nspec_load assemble_context build review.\n\n"
        "## MCP Servers\n\ncontext_server constitution_server.\n\n"
        "## State Schema\n\nLean state: paths and IDs only.\n",
        encoding="utf-8",
    )
    (docs / "constitution.md").write_text(
        "# Constitution\n\n"
        "## Article 1\n\nSpec is truth.\n\n"
        "## Article 2\n\nState stays lean.\n\n"
        "## Article 6\n\nReuse existing assets.\n",
        encoding="utf-8",
    )
    (docs / "tasks.md").write_text(
        "# Tasks\n\n"
        "## Phase 1\n\nMinimal graph.\n\n"
        "## Phase 2\n\nAgent internals.\n\n"
        "## Phase 3\n\nContext engineering.\n",
        encoding="utf-8",
    )
    # A file that should be excluded from chunking
    (docs / "_manifest.json").write_text('{"version": "1"}', encoding="utf-8")

    return docs


@pytest.fixture(autouse=True)
def clear_cache():
    """Reset the module-level collection cache before every test."""
    _reset_collection_cache()
    yield
    _reset_collection_cache()


# ---------------------------------------------------------------------------
# LocalHashEmbedding
# ---------------------------------------------------------------------------

class TestLocalHashEmbedding:
    def test_deterministic_same_input_same_output(self):
        """FR-2.2: same document yields identical embedding on two calls."""
        ef = LocalHashEmbedding()
        docs = ["context engineering spec slice chromadb"]
        vec1 = list(ef(docs)[0])  # may be numpy array — convert for comparison
        vec2 = list(ef(docs)[0])
        assert vec1 == vec2, "Embedding must be deterministic across calls"

    def test_output_dimension_is_512(self):
        """Embedding dimension must be exactly 512."""
        ef = LocalHashEmbedding()
        vec = list(ef(["hello world"])[0])
        assert len(vec) == 512, f"Expected dim=512, got {len(vec)}"

    def test_l2_norm_is_approximately_one(self):
        """Embedding vectors must be L2-normalised (norm ≈ 1.0)."""
        import math
        ef = LocalHashEmbedding()
        vec = list(ef(["fr-2.1 spec slice selection deterministic"])[0])
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 1e-5, f"Norm should be ~1.0, got {norm}"

    def test_different_inputs_different_outputs(self):
        """Different texts should (almost certainly) yield different embeddings."""
        ef = LocalHashEmbedding()
        v1 = list(ef(["constitutional law article one"])[0])
        v2 = list(ef(["git worktree build artifact path"])[0])
        assert v1 != v2, "Different documents must not produce identical embeddings"

    def test_empty_document_handled_gracefully(self):
        """Empty document should not crash; returns normalised zero vector."""
        ef = LocalHashEmbedding()
        vec = ef([""])[0]
        # All-zeros normalise to zeros (norm=0 → divide by 1 guard)
        assert len(vec) == 512

    def test_no_network_calls(self, monkeypatch):
        """
        LocalHashEmbedding must not call urllib, requests, httpx, or socket.connect.
        We verify by patching socket.create_connection to raise and confirming
        no network call is made during embedding.
        """
        import socket

        original = socket.create_connection

        def _forbid(*args, **kwargs):
            raise AssertionError(
                "LocalHashEmbedding made a network call — embedding must be offline"
            )

        monkeypatch.setattr(socket, "create_connection", _forbid)
        ef = LocalHashEmbedding()
        # Should not raise
        ef(["spec slice retrieval chromadb fr-2.1"])


# ---------------------------------------------------------------------------
# _chunk_docs
# ---------------------------------------------------------------------------

class TestChunkDocs:
    def test_chunks_produced_from_docs(self, tmp_docs: Path):
        """Docs directory should yield multiple chunks."""
        chunks = _chunk_docs(tmp_docs)
        assert len(chunks) >= 4, f"Expected ≥4 chunks, got {len(chunks)}"

    def test_manifest_excluded(self, tmp_docs: Path):
        """_manifest.json must not appear in chunks (exclusion rule)."""
        chunks = _chunk_docs(tmp_docs)
        ids = [c[0] for c in chunks]
        assert not any("manifest" in cid for cid in ids), (
            "_manifest files should be excluded from chunking"
        )

    def test_chunk_ids_are_stable(self, tmp_docs: Path):
        """Same docs dir yields identical chunk IDs on two calls (deterministic)."""
        chunks1 = _chunk_docs(tmp_docs)
        chunks2 = _chunk_docs(tmp_docs)
        ids1 = [c[0] for c in chunks1]
        ids2 = [c[0] for c in chunks2]
        assert ids1 == ids2, "Chunk IDs must be deterministic across calls"

    def test_chunk_ids_format(self, tmp_docs: Path):
        """Chunk IDs must follow '{stem}::{index:03d}' format."""
        chunks = _chunk_docs(tmp_docs)
        for chunk_id, _text, _src in chunks:
            parts = chunk_id.split("::")
            assert len(parts) == 2, f"Bad chunk ID format: {chunk_id!r}"
            assert parts[1].isdigit(), f"Index part not numeric: {chunk_id!r}"

    def test_each_chunk_has_non_empty_text(self, tmp_docs: Path):
        """Every chunk must have non-empty text content."""
        chunks = _chunk_docs(tmp_docs)
        for chunk_id, text, _src in chunks:
            assert text.strip(), f"Chunk {chunk_id!r} has empty text"


# ---------------------------------------------------------------------------
# retrieve_slice_ids (FR-2.1 + FR-2.2)
# ---------------------------------------------------------------------------

class TestRetrieveSliceIds:
    def test_fr21_returned_count_less_than_total(self, tmp_docs: Path):
        """
        FR-2.1: retrieve_slice_ids must return fewer chunks than total indexed.

        This proves that "selection is active" — not all chunks are returned,
        only the most relevant ones.
        """
        _, total = _build_collection(tmp_docs)
        ids = retrieve_slice_ids(
            query="context engineering spec slice",
            k=_DEFAULT_K(),
            docs_dir=tmp_docs,
        )
        assert total > 0, "Collection must be non-empty"
        assert len(ids) < total, (
            f"FR-2.1 violation: returned {len(ids)} == total {total}. "
            "Selection must return fewer chunks than the total."
        )

    def test_fr21_returned_count_at_most_k(self, tmp_docs: Path):
        """retrieve_slice_ids must return at most k results."""
        k = 3
        ids = retrieve_slice_ids(query="spec", k=k, docs_dir=tmp_docs)
        assert len(ids) <= k, f"Returned {len(ids)} IDs, expected ≤{k}"

    def test_fr22_deterministic_ordering(self, tmp_docs: Path):
        """
        FR-2.2: identical (query, k, docs_dir) triple always yields the same
        ordered ID list.  This is the cache-hit condition in assemble_prompt.
        """
        query = "constitution article lean state spec"
        k = 3
        ids1 = retrieve_slice_ids(query=query, k=k, docs_dir=tmp_docs)
        ids2 = retrieve_slice_ids(query=query, k=k, docs_dir=tmp_docs)
        assert ids1 == ids2, (
            "FR-2.2: retrieve_slice_ids must be deterministic — "
            "same input must yield same ordered ID list"
        )

    def test_returns_list_of_str(self, tmp_docs: Path):
        """第2条: returned values are str IDs, not dicts or tuples."""
        ids = retrieve_slice_ids(query="build artifact", k=2, docs_dir=tmp_docs)
        for item in ids:
            assert isinstance(item, str), (
                f"第2条: expected str chunk ID, got {type(item)!r}: {item!r}"
            )

    def test_empty_docs_returns_empty_list(self, tmp_path: Path):
        """Empty docs directory returns empty list (no crash)."""
        empty_docs = tmp_path / "empty_docs"
        empty_docs.mkdir()
        ids = retrieve_slice_ids(query="anything", k=5, docs_dir=empty_docs)
        assert ids == [], f"Expected [], got {ids}"


def _DEFAULT_K() -> int:
    """Return the module's default k value (imported here to keep tests DRY)."""
    from mcp_servers.context_server import _DEFAULT_K
    return _DEFAULT_K


# ---------------------------------------------------------------------------
# spec_slice tool registration (AC T3.1)
# ---------------------------------------------------------------------------

class TestSpecSliceRegistration:
    def test_spec_slice_is_sdkmcptool(self):
        """spec_slice must be a SdkMcpTool (result of @tool decorator)."""
        from claude_agent_sdk import SdkMcpTool
        assert isinstance(spec_slice, SdkMcpTool), (
            f"spec_slice must be a SdkMcpTool, got {type(spec_slice)!r}"
        )

    def test_spec_slice_name_is_correct(self):
        """Tool name must be exactly 'spec_slice'."""
        assert spec_slice.name == "spec_slice", (
            f"Expected tool name 'spec_slice', got {spec_slice.name!r}"
        )

    def test_spec_slice_in_registered_tools(self):
        """
        spec_slice must appear in the _registered_tools list passed to
        create_sdk_mcp_server.  This proves registration without a full
        MCP initialize→tools/list handshake.
        """
        assert spec_slice in _registered_tools, (
            "spec_slice must be in _registered_tools (the list passed to "
            "create_sdk_mcp_server)"
        )

    def test_context_server_name(self):
        """MCP server name must be 'ctx' (as registered in .mcp.json)."""
        assert context_server["name"] == "ctx", (
            f"Expected server name 'ctx', got {context_server['name']!r}"
        )

    def test_context_server_is_sdk_type(self):
        """Server type must be 'sdk' (in-process, not stdio subprocess)."""
        assert context_server["type"] == "sdk", (
            f"Expected server type 'sdk', got {context_server['type']!r}"
        )

    def test_context_server_has_mcp_instance(self):
        """
        context_server must contain an MCP Server instance with a
        ListToolsRequest handler — indirect proof that spec_slice is wired.
        """
        from mcp.types import ListToolsRequest

        instance = context_server.get("instance")
        assert instance is not None, "context_server must have an 'instance' key"
        assert ListToolsRequest in instance.request_handlers, (
            "ListToolsRequest handler must be registered — "
            "confirms tool(s) were wired to the server"
        )
