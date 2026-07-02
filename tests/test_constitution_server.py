"""
tests/test_constitution_server.py — Phase 5 (T5.1) tests for constitution_server.

FR-1.2: list_articles / get_article registered on "law" MCP server.
         Parsing correctness: 10 articles found in specs/constitution.md.
         Direct-callable helpers work without MCP handshake.

Tests
─────
  - list_articles registered as an MCP tool on the "law" server
  - get_article registered as an MCP tool on the "law" server
  - exactly 2 tools registered on the law server
  - parsing: 10 articles found in specs/constitution.md
  - article IDs follow "第N条" format
  - article numbers 1–10 are present
  - each article has non-empty title and text
  - get_article_text(n) returns correct article by number
  - get_article_text("第N条") returns correct article by id string
  - get_article_text with unknown id raises KeyError
  - list_articles MCP tool returns correct structure
  - get_article MCP tool returns correct structure
  - no real API calls (create_sdk_mcp_server is in-process)
"""
from __future__ import annotations

import asyncio
import textwrap
from pathlib import Path
from typing import Any

import pytest

from mcp_servers.constitution_server import (
    Article,
    _parse_articles,
    _reset_article_cache,
    constitution_server,
    get_article,
    get_article_text,
    list_articles,
    load_articles,
)


# ---------------------------------------------------------------------------
# Fixture: minimal constitution markdown for parse tests
# ---------------------------------------------------------------------------

_SAMPLE_CONSTITUTION = textwrap.dedent("""\
    # Constitution — Test Edition

    各条項は「原則」と「強制点」をセットで持つ。

    ---

    ## 第1条: 仕様が唯一の真実源

    - **原則**: 実装は仕様から導出される。
    - **強制点**: verify ノードが各成果物を照合する。

    ## 第2条: 状態は薄く保つ

    - **原則**: 状態にはパスと ID のみを載せる。
    - **強制点**: チェックポイントサイズを計測する。

    ## 第3条: 副作用は承認の後

    - **原則**: 不可逆な副作用は interrupt 後の分岐にのみ書く。
    - **強制点**: review ノードのコードレビュー。

    ## 第4条: 隔離

    - **原則**: worktree + podman で物理分離する。
    - **強制点**: sandbox.py の実装レビュー。

    ## 第5条: 二層防御

    - **原則**: ソフト境界とハード境界を両方持つ。
    - **強制点**: PreToolUse フックと cgroups v2 を両方確認する。

    ## 第6条: 再利用

    - **原則**: 既存資産を再利用し、二重化しない。
    - **強制点**: 同一責務の再実装を Validator が検出したら FAIL。

    ## 第7条: 評価ゲート

    - **原則**: eval_suite を通過してから次フェーズへ進む。
    - **強制点**: eval ノードの条件エッジ。

    ## 第8条: 可観測性

    - **原則**: すべての run をトレースする。
    - **強制点**: LangSmith または OTel にトレースを出すこと。

    ## 第9条: 外殻は決定論的

    - **原則**: 制御フローは LangGraph に閉じる。
    - **強制点**: 状態遷移がグラフのエッジとして明示されていること。

    ## 第10条: セキュリティは構築時から

    - **原則**: セキュリティは後付けにしない。
    - **強制点**: security サブエージェントが eval_suite に含まれること。

    ---

    ## 改正手続き

    憲法の変更は仕様変更として扱う。
""")


@pytest.fixture
def sample_articles() -> list[Article]:
    """Parse the minimal sample constitution."""
    return _parse_articles(_SAMPLE_CONSTITUTION)


@pytest.fixture
def constitution_file(tmp_path: Path) -> Path:
    """Write sample constitution to a temp file."""
    f = tmp_path / "constitution.md"
    f.write_text(_SAMPLE_CONSTITUTION, encoding="utf-8")
    _reset_article_cache()
    return f


# ---------------------------------------------------------------------------
# Tests: MCP server registration (FR-1.2)
# ---------------------------------------------------------------------------

class TestServerRegistration:
    """
    FR-1.2: constitution_server must be named "law" and register
    list_articles + get_article tools.

    Note: create_sdk_mcp_server returns a dict-like mapping with keys
    'name', 'type', 'instance'.  Access via constitution_server["name"],
    constitution_server["type"], constitution_server["instance"].

    The @tool decorator wraps functions into SdkMcpTool objects.
    Access the original coroutine via tool_obj.handler; the name via tool_obj.name.
    """

    def test_server_is_named_law(self):
        """constitution_server must be the 'law' MCP server."""
        # create_sdk_mcp_server returns a dict-like object
        assert constitution_server["name"] == "law", (
            f"Server name must be 'law', got {constitution_server['name']!r}"
        )

    def test_server_type_is_sdk(self):
        """constitution_server type must be 'sdk' (in-process, not stdio)."""
        assert constitution_server["type"] == "sdk", (
            f"Expected server type 'sdk', got {constitution_server['type']!r}"
        )

    def test_server_has_instance(self):
        """constitution_server must have an 'instance' key with MCP server object."""
        assert "instance" in constitution_server, (
            "constitution_server must have an 'instance' key"
        )
        assert constitution_server["instance"] is not None

    def test_server_list_tools_handler_registered(self):
        """ListToolsRequest handler must be registered on the law server instance."""
        from mcp.types import ListToolsRequest

        instance = constitution_server.get("instance")
        assert instance is not None
        assert ListToolsRequest in instance.request_handlers, (
            "ListToolsRequest handler must be registered — confirms tools are wired"
        )

    def test_list_articles_tool_registered(self):
        """list_articles must be registered on the law server (via _registered_tools)."""
        from mcp_servers.constitution_server import _registered_tools
        tool_names = [t.name for t in _registered_tools]
        assert "list_articles" in tool_names, (
            f"list_articles not found in registered tools: {tool_names}"
        )

    def test_get_article_tool_registered(self):
        """get_article must be registered on the law server (via _registered_tools)."""
        from mcp_servers.constitution_server import _registered_tools
        tool_names = [t.name for t in _registered_tools]
        assert "get_article" in tool_names, (
            f"get_article not found in registered tools: {tool_names}"
        )

    def test_exactly_two_tools_registered(self):
        """Exactly 2 tools must be registered on the law server (list_articles, get_article)."""
        from mcp_servers.constitution_server import _registered_tools
        assert len(_registered_tools) == 2, (
            f"Expected 2 tools; got {len(_registered_tools)}"
        )

    def test_list_articles_has_handler(self):
        """list_articles SdkMcpTool must expose a callable .handler attribute."""
        from mcp_servers.constitution_server import _registered_tools
        la = next(t for t in _registered_tools if t.name == "list_articles")
        assert callable(la.handler), "list_articles.handler must be callable"

    def test_get_article_has_handler(self):
        """get_article SdkMcpTool must expose a callable .handler attribute."""
        from mcp_servers.constitution_server import _registered_tools
        ga = next(t for t in _registered_tools if t.name == "get_article")
        assert callable(ga.handler), "get_article.handler must be callable"


# ---------------------------------------------------------------------------
# Tests: parsing correctness (10 articles)
# ---------------------------------------------------------------------------

class TestArticleParsing:
    """Parsing specs/constitution.md must yield 10 articles."""

    def test_sample_yields_ten_articles(self, sample_articles: list[Article]):
        """Sample constitution must parse to exactly 10 articles."""
        assert len(sample_articles) == 10, (
            f"Expected 10 articles, got {len(sample_articles)}: "
            f"{[a.id for a in sample_articles]}"
        )

    def test_article_ids_follow_format(self, sample_articles: list[Article]):
        """All article IDs must follow '第N条' format."""
        import re
        pattern = re.compile(r"^第\d+条$")
        for art in sample_articles:
            assert pattern.match(art.id), (
                f"Article id {art.id!r} does not match '第N条' format"
            )

    def test_article_numbers_1_to_10(self, sample_articles: list[Article]):
        """Article numbers must be 1 through 10."""
        numbers = sorted(a.number for a in sample_articles)
        assert numbers == list(range(1, 11)), (
            f"Expected article numbers 1-10, got {numbers}"
        )

    def test_each_article_has_nonempty_title(self, sample_articles: list[Article]):
        """Each article must have a non-empty title string."""
        for art in sample_articles:
            assert art.title.strip(), (
                f"Article {art.id} has empty title"
            )

    def test_each_article_has_nonempty_text(self, sample_articles: list[Article]):
        """Each article must have non-empty section text."""
        for art in sample_articles:
            assert art.text.strip(), (
                f"Article {art.id} has empty text"
            )

    def test_article_text_includes_heading(self, sample_articles: list[Article]):
        """Article text must include the '## 第N条' heading."""
        for art in sample_articles:
            assert f"## {art.id}" in art.text, (
                f"Article {art.id!r} text does not include its heading"
            )

    def test_first_article_title(self, sample_articles: list[Article]):
        """First article must be 第1条 with correct title."""
        first = sample_articles[0]
        assert first.number == 1
        assert first.id == "第1条"
        assert "仕様" in first.title

    def test_tenth_article_id(self, sample_articles: list[Article]):
        """Tenth article must be 第10条."""
        tenth = sample_articles[9]
        assert tenth.id == "第10条"
        assert tenth.number == 10

    def test_real_constitution_has_ten_articles(self):
        """specs/constitution.md (the real distributable) must have 10 articles."""
        real_path = Path("specs/constitution.md")
        if not real_path.exists():
            pytest.skip("specs/constitution.md not found — skipping real-file test")
        articles = load_articles(real_path)
        assert len(articles) == 10, (
            f"specs/constitution.md must contain 10 articles; found {len(articles)}: "
            f"{[a.id for a in articles]}"
        )


# ---------------------------------------------------------------------------
# Tests: get_article_text direct-callable helper
# ---------------------------------------------------------------------------

class TestGetArticleText:
    """Direct-callable get_article_text(n, path) — no MCP handshake."""

    def test_get_by_integer(self, constitution_file: Path):
        """get_article_text(1, path) returns article 第1条 text."""
        text = get_article_text(1, constitution_file)
        assert "第1条" in text

    def test_get_by_string_id(self, constitution_file: Path):
        """get_article_text('第1条', path) returns article 第1条 text."""
        text = get_article_text("第1条", constitution_file)
        assert "第1条" in text

    def test_get_by_numeric_string(self, constitution_file: Path):
        """get_article_text('1', path) returns article 第1条 text."""
        text = get_article_text("1", constitution_file)
        assert "第1条" in text

    def test_get_article_10(self, constitution_file: Path):
        """get_article_text(10, path) returns 第10条 text."""
        text = get_article_text(10, constitution_file)
        assert "第10条" in text

    def test_get_article_text_contains_principle(self, constitution_file: Path):
        """Returned text must include 原則 content."""
        text = get_article_text(1, constitution_file)
        assert "原則" in text

    def test_unknown_integer_raises_key_error(self, constitution_file: Path):
        """get_article_text(99, path) must raise KeyError."""
        with pytest.raises(KeyError):
            get_article_text(99, constitution_file)

    def test_unknown_string_raises_key_error(self, constitution_file: Path):
        """get_article_text('第99条', path) must raise KeyError."""
        with pytest.raises(KeyError):
            get_article_text("第99条", constitution_file)

    def test_get_all_ten_articles(self, constitution_file: Path):
        """get_article_text(n, path) succeeds for all n in 1..10."""
        for n in range(1, 11):
            text = get_article_text(n, constitution_file)
            assert f"第{n}条" in text, (
                f"get_article_text({n}) does not contain '第{n}条'"
            )


# ---------------------------------------------------------------------------
# Tests: MCP tool functions (async, no real API calls)
# ---------------------------------------------------------------------------

class TestMcpTools:
    """
    Test the MCP tool logic via the .handler attribute of SdkMcpTool objects.

    The @tool decorator wraps async functions into SdkMcpTool objects.
    Original coroutines are accessible via tool_obj.handler — call those in tests
    to avoid the "SdkMcpTool object is not callable" error.

    No real API or network calls: create_sdk_mcp_server is in-process.
    """

    def _get_handler(self, tool_obj):
        """Return the callable async handler from an SdkMcpTool."""
        return tool_obj.handler

    def test_list_articles_handler_returns_dict(self, constitution_file: Path, monkeypatch):
        """list_articles handler must return a dict with 'articles' and 'content' keys."""
        monkeypatch.setenv("SDD_CONSTITUTION_PATH", str(constitution_file))
        _reset_article_cache()
        result = asyncio.run(self._get_handler(list_articles)({}))
        assert isinstance(result, dict), "list_articles must return a dict"
        assert "articles" in result, "result must have 'articles' key"
        assert "content" in result, "result must have 'content' key"

    def test_list_articles_handler_returns_ten_items(self, constitution_file: Path, monkeypatch):
        """list_articles handler must return 10 article entries."""
        monkeypatch.setenv("SDD_CONSTITUTION_PATH", str(constitution_file))
        _reset_article_cache()
        result = asyncio.run(self._get_handler(list_articles)({}))
        items = result["articles"]
        assert len(items) == 10, (
            f"list_articles must return 10 articles; got {len(items)}"
        )

    def test_list_articles_items_have_id_and_title(self, constitution_file: Path, monkeypatch):
        """Each item in list_articles must have 'id' and 'title' fields."""
        monkeypatch.setenv("SDD_CONSTITUTION_PATH", str(constitution_file))
        _reset_article_cache()
        result = asyncio.run(self._get_handler(list_articles)({}))
        for item in result["articles"]:
            assert "id" in item, f"Article item missing 'id': {item}"
            assert "title" in item, f"Article item missing 'title': {item}"

    def test_list_articles_content_is_text_type(self, constitution_file: Path, monkeypatch):
        """list_articles handler content[0] must be type 'text'."""
        monkeypatch.setenv("SDD_CONSTITUTION_PATH", str(constitution_file))
        _reset_article_cache()
        result = asyncio.run(self._get_handler(list_articles)({}))
        assert result["content"][0]["type"] == "text"

    def test_get_article_handler_by_id(self, constitution_file: Path, monkeypatch):
        """get_article handler({'article_id': '第1条'}) must return article text."""
        monkeypatch.setenv("SDD_CONSTITUTION_PATH", str(constitution_file))
        _reset_article_cache()
        result = asyncio.run(self._get_handler(get_article)({"article_id": "第1条"}))
        assert result.get("found") is True
        text = result["content"][0]["text"]
        assert "第1条" in text

    def test_get_article_handler_by_number_string(self, constitution_file: Path, monkeypatch):
        """get_article handler({'article_id': '10'}) returns 第10条."""
        monkeypatch.setenv("SDD_CONSTITUTION_PATH", str(constitution_file))
        _reset_article_cache()
        result = asyncio.run(self._get_handler(get_article)({"article_id": "10"}))
        assert result.get("found") is True

    def test_get_article_handler_unknown_returns_found_false(self, constitution_file: Path, monkeypatch):
        """get_article handler({'article_id': '第99条'}) must return found=False."""
        monkeypatch.setenv("SDD_CONSTITUTION_PATH", str(constitution_file))
        _reset_article_cache()
        result = asyncio.run(self._get_handler(get_article)({"article_id": "第99条"}))
        assert result.get("found") is False

    def test_no_real_api_calls(self, constitution_file: Path, monkeypatch):
        """
        FR-1.2 no-network: list_articles and get_article must not make
        any network calls (in-process MCP, not a stdio handshake).
        """
        import socket

        def blocked(*args, **kwargs):
            raise OSError("Network blocked in test")

        monkeypatch.setenv("SDD_CONSTITUTION_PATH", str(constitution_file))
        _reset_article_cache()
        monkeypatch.setattr(socket, "getaddrinfo", blocked)

        # Must not raise network error
        result = asyncio.run(self._get_handler(list_articles)({}))
        assert len(result["articles"]) == 10
