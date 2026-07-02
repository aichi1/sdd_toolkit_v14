"""
mcp_servers/constitution_server.py — Constitution Law MCP server for sdd_toolkit_v14.

FR-1.2: Exposes two MCP tools:
  - list_articles: returns all article ids and titles
  - get_article:   returns the full text of a specific article

第6条 (AMENDED) reconciliation
────────────────────────────────
constitution-clause retrieval is a NEW responsibility distinct from handlers.py.
handlers.py performs BM25 retrieval over ~/.sdd-knowledge (cross-project KB).
This module parses and serves specs/constitution.md (per-project constitutional
law articles) — a separate corpus and concern.  No handlers.py import is needed
or appropriate here; not importing it is NOT a 第6条 violation (the amended
enforcement tests "re-implemented an existing concern", not "imported handlers").

This server is therefore a thin facade over the parsed constitution file,
keeping its own business logic minimal — consistent with the spirit of 第6条.

第2条 (lean state)
──────────────────
load_articles() returns structured objects (id, title, text).  The graph nodes
that call get_article_text() receive only the constitutional text for one article
— no bulk body is stored in TaskState.

Direct-callable helpers (no MCP handshake)
──────────────────────────────────────────
  load_articles(path)       → list[Article]
  get_article_text(n, path) → str   (n = int like 1, or str like "第1条")

These are designed for use by graph nodes and the eval_suite without needing
a full MCP initialize→tools/list handshake.

Path resolution
───────────────
Default path: SDD_CONSTITUTION_PATH env var → "specs/constitution.md".
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import create_sdk_mcp_server, tool


# ---------------------------------------------------------------------------
# Article data model
# ---------------------------------------------------------------------------

@dataclass
class Article:
    """
    Represents a single constitutional article parsed from constitution.md.

    Fields
    ──────
    id      : canonical identifier, e.g. "第1条"
    number  : integer article number, e.g. 1
    title   : article title (the part after "第N条: "), e.g. "仕様が唯一の真実源"
    text    : full section text including the heading line and all bullet points
    """
    id: str           # "第1条", "第2条", …
    number: int       # 1, 2, …
    title: str        # "仕様が唯一の真実源", …
    text: str         # full markdown section text


# ---------------------------------------------------------------------------
# Parser: specs/constitution.md → list[Article]
# ---------------------------------------------------------------------------

# Pattern to match article headings: "## 第N条: Title"
# Captures:  group(1) = full id ("第10条"), group(2) = number digits, group(3) = title
_ARTICLE_HEADING_RE = re.compile(
    r"^## (第(\d+)条)(?:[：:][ \t]*(.*?))?[ \t]*$",
    re.MULTILINE,
)


def load_articles(path: str | Path | None = None) -> list[Article]:
    """
    Parse constitution.md and return all articles.

    Args:
        path: Path to the constitution file.  None → SDD_CONSTITUTION_PATH env
              var → "specs/constitution.md".

    Returns:
        List of Article objects in article-number order.

    Raises:
        FileNotFoundError: if the constitution file does not exist.
    """
    resolved_path = Path(
        path
        or os.environ.get("SDD_CONSTITUTION_PATH", "specs/constitution.md")
    )
    text = resolved_path.read_text(encoding="utf-8", errors="replace")
    return _parse_articles(text)


def _parse_articles(text: str) -> list[Article]:
    """
    Internal: parse raw constitution markdown text into Article objects.

    Splits on "## 第N条" headings.  Each section's text runs from its heading
    line up to (but not including) the next "## 第N条" heading or EOF.
    The closing 改正手続き section and any non-article ## headings are ignored.
    """
    articles: list[Article] = []

    # Find all heading positions
    matches = list(_ARTICLE_HEADING_RE.finditer(text))
    if not matches:
        return articles

    for i, match in enumerate(matches):
        article_id = match.group(1)           # e.g. "第1条"
        number_str = match.group(2)           # e.g. "1"
        title = (match.group(3) or "").strip()
        number = int(number_str)

        # Section text: from the heading line start to the next heading (or EOF)
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start:end].rstrip()

        articles.append(Article(
            id=article_id,
            number=number,
            title=title,
            text=section_text,
        ))

    return articles


# ---------------------------------------------------------------------------
# Module-level article cache (keyed by resolved path string)
# ---------------------------------------------------------------------------

_article_cache: dict[str, list[Article]] = {}


def _get_articles(path: str | Path | None = None) -> list[Article]:
    """Return cached articles for the given path (or default path)."""
    resolved = str(
        Path(
            path or os.environ.get("SDD_CONSTITUTION_PATH", "specs/constitution.md")
        ).resolve()
    )
    if resolved not in _article_cache:
        _article_cache[resolved] = load_articles(resolved)
    return _article_cache[resolved]


def _reset_article_cache() -> None:
    """Clear the article cache.  Used in tests."""
    _article_cache.clear()


# ---------------------------------------------------------------------------
# Direct-callable helper: get_article_text
# ---------------------------------------------------------------------------

def get_article_text(
    article_ref: int | str,
    path: str | Path | None = None,
) -> str:
    """
    Return the full text of a specific article without an MCP handshake.

    Args:
        article_ref: Article number (int, e.g. 1) or article id (str, e.g. "第1条").
        path:        Path override for tests.  None → env / default.

    Returns:
        The full markdown text of the article section.

    Raises:
        KeyError:   if the article is not found.
        FileNotFoundError: if the constitution file does not exist.
    """
    articles = _get_articles(path)

    # Normalize lookup key
    if isinstance(article_ref, int):
        target_number = article_ref
        for art in articles:
            if art.number == target_number:
                return art.text
        raise KeyError(f"Article number {article_ref} not found in constitution")

    # String: accept "第1条", "第10条", or plain "1", "10"
    ref_str = str(article_ref).strip()
    # Try direct id match ("第N条")
    for art in articles:
        if art.id == ref_str:
            return art.text
    # Try numeric string ("1" → number 1)
    try:
        num = int(ref_str)
        return get_article_text(num, path)
    except (ValueError, KeyError):
        pass
    raise KeyError(f"Article {article_ref!r} not found in constitution")


# ---------------------------------------------------------------------------
# MCP tools
# ---------------------------------------------------------------------------

@tool(
    "list_articles",
    "憲法の全条項の ID とタイトルを返す。",
    {},
)
async def list_articles(args: dict[str, Any]) -> dict[str, Any]:
    """
    MCP tool: list all constitutional articles.

    Returns a structured response containing all article ids and titles.

    FR-1.2: This tool must be registered on the "law" MCP server and
    discoverable via initialize→tools/list.
    """
    articles = _get_articles()
    items = [
        {"id": art.id, "number": art.number, "title": art.title}
        for art in articles
    ]
    text = "\n".join(
        f"- {a['id']}: {a['title']}" for a in items
    )
    return {
        "content": [{"type": "text", "text": text}],
        "articles": items,
    }


@tool(
    "get_article",
    "指定した条項の全文を返す。article_id に 'first_article' や数字(1, 2, ...)または '第1条' 形式を指定する。",
    {"article_id": str},
)
async def get_article(args: dict[str, Any]) -> dict[str, Any]:
    """
    MCP tool: retrieve the full text of a specific constitutional article.

    Args (in args dict):
        article_id: The article to retrieve.  Accepted formats:
                    - "第1条", "第10条"  (canonical id)
                    - "1", "10"          (numeric string)
                    - 1, 10             (integer)

    Returns:
        Full markdown text of the article section.

    FR-1.2: This tool must be registered on the "law" MCP server and
    discoverable via initialize→tools/list.
    """
    article_id = args.get("article_id", "")
    try:
        text = get_article_text(article_id)
        return {
            "content": [{"type": "text", "text": text}],
            "article_id": article_id,
            "found": True,
        }
    except KeyError as exc:
        return {
            "content": [{"type": "text", "text": f"Article not found: {exc}"}],
            "article_id": article_id,
            "found": False,
        }


# ---------------------------------------------------------------------------
# MCP server registration
# ---------------------------------------------------------------------------

# Keep a reference so tests can inspect without a full MCP handshake
_registered_tools = [list_articles, get_article]

constitution_server = create_sdk_mcp_server(
    name="law",
    version="1.0.0",
    tools=_registered_tools,
)
