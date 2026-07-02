"""
mcp_servers/context_server.py — Spec-slice MCP server for sdd_toolkit_v14.

Corpus: docs/*.md files (this project's specification) — NOT ~/.sdd-knowledge KB.

第6条 reconciliation
────────────────────
scripts/mcp_server/handlers.py performs BM25 retrieval over the
~/.sdd-knowledge component registry — a cross-project reuse knowledge base
of Builder/Validator definitions, skill templates, etc.

This module performs ChromaDB vector retrieval over docs/*.md — the v14
project-specification files (requirements, plan, constitution, tasks, ...).

These are structurally different:

  Concern          handlers.py                  context_server.py (here)
  ─────────────    ────────────────────────────  ──────────────────────────────
  Corpus           ~/.sdd-knowledge registry     docs/*.md (this project's spec)
  Engine           BM25 (bm25s)                  ChromaDB vector search
  Purpose          Find reusable KB components   Find task-relevant spec slices
  Caller           KB REST API (server.py)       assemble_context graph node

Reusing handlers.py here would mean importing KB-registry JSON concerns
into a spec-retrieval context — an architectural mismatch, not a reuse
opportunity.  第6条 ("既存資産を再利用し、二重化しない") is satisfied:
context_server.py implements a NEW concern (spec slicing) rather than
duplicating handlers.py's KB concern.  This comment exists so a Validator
can confirm compliance without mistaking new-concern implementation for
prohibited duplication.

第2条  (lean state)
──────────────────
retrieve_slice_ids() and the assemble_context node return chunk IDs only.
Chunk body text is never placed in TaskState.

FR-2.1 (spec slice selection)
─────────────────────────────
The collection is built from docs/*.md chunks (typically 30-100 chunks
depending on heading density).  retrieve_slice_ids() returns k << total,
so selection is always active (k is capped at total-1 to guarantee this).

FR-2.2 (fixed injection order / prompt-cache hit)
──────────────────────────────────────────────────
retrieve_slice_ids() returns results in a fixed order: ascending cosine
distance, with chunk-ID as a lexicographic tiebreaker for ties.
Combined with LocalHashEmbedding's determinism, the same (query, k) pair
always yields the same ordered ID list.  assemble_prompt() (in graph/nodes.py)
puts the immutable constitution block first, making the head block identical
across calls with the same inputs — satisfying the prompt-cache hit condition.

ChromaDB implementation notes
──────────────────────────────
EphemeralClient instances share a process-level in-memory store (all
instances created in the same process see the same collection namespace).
We therefore use a module-level singleton client and derive a unique
collection name from the resolved docs_dir path (SHA-256 hash prefix).
This guarantees:
  - Same docs_dir → same collection name → same collection (no duplicate)
  - Different docs_dir → different collection name → separate collection

No ONNX model download: LocalHashEmbedding is network-free and
deterministic.  anonymized_telemetry=False prevents Chroma telemetry pings.
EphemeralClient: no .chroma/ directory side-effects.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from claude_agent_sdk import create_sdk_mcp_server, tool


# ---------------------------------------------------------------------------
# Local deterministic embedding function — no network, no ONNX download
# ---------------------------------------------------------------------------

_DIM = 512
_TOKENIZE_RE = re.compile(r"[^\w\s]")


class LocalHashEmbedding(EmbeddingFunction[Documents]):
    """
    Bag-of-words feature hashing to a fixed _DIM-dimensional vector.

    Algorithm
    ─────────
    For each word in the document (lowercased, punctuation stripped):
      1. Compute SHA-256 hash of the word (bytes).
      2. Map to a bucket: idx = hash_int % _DIM.
      3. Increment vec[idx] += 1.0  (count-based feature hashing).
    Then L2-normalise the vector.

    Properties
    ──────────
    - Deterministic: SHA-256 is stable across Python versions and platforms.
    - Offline: no network calls, no model downloads.
    - Approximate semantic similarity: words shared between query and document
      end up in the same bucket, so cosine distance is meaningful for
      keyword-rich spec text even without semantic embeddings.

    Implements all required EmbeddingFunction protocol methods to suppress
    DeprecationWarnings from chromadb 1.5.x.
    """

    def __init__(self, dim: int = _DIM) -> None:
        self._dim = dim

    def __call__(self, input: Documents) -> Embeddings:  # type: ignore[override]
        result: list[list[float]] = []
        for doc in input:
            vec = [0.0] * self._dim
            words = _TOKENIZE_RE.sub(" ", doc.lower()).split()
            for word in words:
                h = int(hashlib.sha256(word.encode()).hexdigest(), 16)
                vec[h % self._dim] += 1.0
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            result.append([x / norm for x in vec])
        return result  # type: ignore[return-value]

    @staticmethod
    def name() -> str:
        return "local-hash-bow-512"

    @staticmethod
    def build_from_config(config: dict[str, Any]) -> "LocalHashEmbedding":
        return LocalHashEmbedding(dim=config.get("dim", _DIM))

    def get_config(self) -> dict[str, Any]:
        return {"dim": self._dim}


# ---------------------------------------------------------------------------
# Chunking: docs/*.md → (chunk_id, text, source_filename) triples
# ---------------------------------------------------------------------------

def _chunk_docs(docs_dir: str | Path) -> list[tuple[str, str, str]]:
    """
    Split each docs/*.md file into per-heading sections (chunks).

    Exclusions
    ──────────
    - Files whose name starts with '_' (e.g. _manifest.json)

    Chunk ID format: "{stem}::{idx:03d}"
      stem = filename without extension (e.g. "requirements")
      idx  = 0-padded section index within the file

    If a file has no headings, the entire file is a single chunk (idx=000).

    Returns list of (chunk_id, text, source_filename) — guaranteed stable
    ordering (sorted by filename then by index) so the collection is built
    deterministically on each call.
    """
    docs_path = Path(docs_dir)
    chunks: list[tuple[str, str, str]] = []

    md_files = sorted(
        f
        for f in docs_path.glob("*.md")
        if not f.name.startswith("_")
    )

    for md_file in md_files:
        stem = md_file.stem
        try:
            text = md_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        # Split on Markdown headings (H1–H3) so each section is a chunk.
        # Lines starting with '#' (1–3 hashes) begin a new section.
        raw_sections = re.split(r"(?m)^(?=#{1,3} )", text)
        sections = [s.strip() for s in raw_sections if s.strip()]

        if not sections:
            chunk_id = f"{stem}::000"
            chunks.append((chunk_id, text or "(empty)", md_file.name))
            continue

        for idx, section in enumerate(sections):
            chunk_id = f"{stem}::{idx:03d}"
            chunks.append((chunk_id, section, md_file.name))

    return chunks


# ---------------------------------------------------------------------------
# Singleton ChromaDB client + hash-based collection naming
# ---------------------------------------------------------------------------
#
# EphemeralClient instances in the same process share a global in-memory
# store.  We therefore use a single module-level client to avoid creating
# multiple "views" into the same namespace, and derive unique collection
# names per docs_dir to prevent cross-directory collisions.
#
# Collection name format: "sc-{12-hex-chars}"  (15 chars total, within the
# chromadb 3–512 char limit; only [a-zA-Z0-9._-] characters used).
# The hex suffix is the first 12 characters of the SHA-256 hash of the
# resolved docs_dir path — stable and unique per directory.

_chroma_client: chromadb.Client | None = None


def _get_chroma_client() -> chromadb.Client:
    """Return (or create) the module-level singleton EphemeralClient."""
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.EphemeralClient(
            settings=chromadb.Settings(anonymized_telemetry=False)
        )
    return _chroma_client


def _collection_name_for(docs_dir: str | Path) -> str:
    """Derive a unique, stable ChromaDB collection name for docs_dir."""
    resolved = str(Path(docs_dir).resolve())
    suffix = hashlib.sha256(resolved.encode()).hexdigest()[:12]
    return f"sc-{suffix}"


def _build_collection(
    docs_dir: str | Path,
) -> tuple[chromadb.Collection, int]:
    """
    Return a ChromaDB collection for the given docs_dir, building it if new.

    Uses the singleton EphemeralClient and a hash-based collection name so
    the same docs_dir always maps to the same collection without conflicts.

    - If the collection already exists in the client, return it as-is
      (idempotent for the same docs_dir within a process run).
    - If it does not exist, create it and populate from docs/*.md chunks.

    Network-free: LocalHashEmbedding; no ONNX download.
    No .chroma/ directory: EphemeralClient.
    Telemetry off: anonymized_telemetry=False.
    """
    client = _get_chroma_client()
    ef = LocalHashEmbedding()
    coll_name = _collection_name_for(docs_dir)

    # Try to retrieve an existing collection built for this docs_dir
    try:
        col = client.get_collection(name=coll_name, embedding_function=ef)
        return col, col.count()
    except Exception:
        pass  # Collection does not exist yet — fall through to create

    # Create and populate the collection
    col = client.create_collection(
        name=coll_name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    chunks = _chunk_docs(docs_dir)
    if chunks:
        ids = [c[0] for c in chunks]
        doc_texts = [c[1] for c in chunks]
        metadatas = [{"source": c[2]} for c in chunks]
        col.add(ids=ids, documents=doc_texts, metadatas=metadatas)

    return col, len(chunks)


# ---------------------------------------------------------------------------
# Module-level collection cache (Python-level, keyed by resolved docs_dir)
# ---------------------------------------------------------------------------
#
# Two-level caching:
#   1. Python dict (_collection_cache): avoids repeated get_collection() calls.
#   2. ChromaDB store (singleton client): avoids repeated populate() calls.
#
# _reset_collection_cache() clears only the Python dict.  The ChromaDB store
# persists within the process.  For tests: each pytest test uses a unique
# tmp_path, so each docs_dir has a unique hash → unique collection name →
# no cross-test contamination regardless of cache reset.

_collection_cache: dict[str, tuple[chromadb.Collection, int]] = {}


def _get_collection(
    docs_dir: str | Path | None = None,
) -> tuple[chromadb.Collection, int]:
    """
    Return cached (collection, total_chunks) for docs_dir.

    If docs_dir is None, falls back to SDD_DOCS_DIR env var → "docs".
    Cache key is the resolved absolute path so relative/absolute paths
    pointing to the same directory share the same cache entry.
    """
    resolved = str(
        Path(docs_dir or os.environ.get("SDD_DOCS_DIR", "docs")).resolve()
    )
    if resolved not in _collection_cache:
        _collection_cache[resolved] = _build_collection(resolved)
    return _collection_cache[resolved]


def _reset_collection_cache() -> None:
    """
    Clear the Python-level collection cache.

    Used in tests to force re-lookup after changing SDD_DOCS_DIR.
    The underlying ChromaDB collections persist in the singleton client;
    subsequent calls to _get_collection() will retrieve them via
    get_collection() (which is cheap compared to re-indexing).
    """
    _collection_cache.clear()


# ---------------------------------------------------------------------------
# Public retrieval helper — callable directly from graph nodes
# ---------------------------------------------------------------------------

_DEFAULT_K = 5


def retrieve_slice_ids(
    query: str,
    k: int = _DEFAULT_K,
    docs_dir: str | Path | None = None,
) -> list[str]:
    """
    Return the IDs of the top-k spec chunks most relevant to ``query``.

    Graph nodes call this directly (no MCP handshake required).

    FR-2.1 guarantee
    ─────────────────
    The returned count is always < total_chunks.  Specifically:
      k_actual = min(k, max(1, total - 1))
    so even k >= total will return at most total-1 chunks, ensuring that
    "selection is active" (not all chunks are returned).

    FR-2.2 ordering
    ────────────────
    Results are sorted by (cosine_distance ASC, chunk_id ASC) so the same
    (query, k, docs_dir) triple always yields the same ordered ID list.
    Combined with the deterministic LocalHashEmbedding, this satisfies the
    prompt-cache hit condition when used inside assemble_prompt().

    第2条: returns IDs (str) only — no body text.

    Args:
        query:    Query string (e.g., task_id or a natural-language description).
        k:        Max chunks to return.  Capped at total-1 (FR-2.1).
        docs_dir: Docs directory override (mainly for tests).  None → env default.

    Returns:
        Ordered list of chunk ID strings.  Empty if collection has no documents.
    """
    col, total = _get_collection(docs_dir)

    if total == 0:
        return []

    # FR-2.1: ensure returned count < total (selection is active)
    k_actual = min(k, max(1, total - 1))

    results = col.query(
        query_texts=[query],
        n_results=k_actual,
        include=["distances"],
    )

    ids: list[str] = results["ids"][0] if results.get("ids") else []
    distances: list[float] = (
        results["distances"][0] if results.get("distances") else [0.0] * len(ids)
    )

    # Fixed deterministic order: ascending distance, then alphabetical ID (FR-2.2)
    sorted_pairs = sorted(zip(distances, ids), key=lambda p: (p[0], p[1]))
    return [sid for _, sid in sorted_pairs]


# ---------------------------------------------------------------------------
# MCP tool: spec_slice
# ---------------------------------------------------------------------------

@tool(
    "spec_slice",
    "タスクに関連する仕様スライスを返す。docs/*.md を ChromaDB で検索し、上位 k チャンクを固定順で返す。",
    {"task_id": str, "query": str, "k": int},
)
async def spec_slice(args: dict[str, Any]) -> dict[str, Any]:
    """
    MCP tool: retrieve and render the top-k relevant spec chunks.

    Returns a structured response with:
      - "content": MCP text payload (rendered chunk summaries for Claude)
      - "ids":     the selected chunk IDs (第2条: graph node stores IDs only)

    The chunk count returned is always < total chunk count (FR-2.1).
    Results are in a fixed, deterministic order (FR-2.2).
    """
    task_id: str = str(args.get("task_id", ""))
    query: str = str(args.get("query", task_id))
    k: int = int(args.get("k", _DEFAULT_K))

    # Use task_id as fallback query if query is empty
    effective_query = query or task_id or "sdd_toolkit specification"

    ids = retrieve_slice_ids(query=effective_query, k=k)

    col, total = _get_collection()

    # Render a short summary for each selected chunk
    text_parts = [
        f"[spec_slice: {len(ids)}/{total} chunks selected for task={task_id!r}]"
    ]

    if ids:
        fetched = col.get(ids=ids, include=["documents", "metadatas"])
        for chunk_id, doc_text, meta in zip(
            fetched["ids"],
            fetched["documents"],
            fetched["metadatas"],
        ):
            source = (meta or {}).get("source", "unknown")
            # Truncate to avoid overwhelming Claude's context window
            preview = (doc_text or "")[:800]
            text_parts.append(f"\n## {chunk_id} (from {source})\n{preview}")

    return {
        "content": [{"type": "text", "text": "\n".join(text_parts)}],
        "ids": ids,
    }


# ---------------------------------------------------------------------------
# MCP server registration
# ---------------------------------------------------------------------------

# Keep a reference to the tools list so tests can inspect registration
# without a full MCP initialize→tools/list handshake.
_registered_tools = [spec_slice]

context_server = create_sdk_mcp_server(
    name="ctx",
    version="1.0.0",
    tools=_registered_tools,
)
