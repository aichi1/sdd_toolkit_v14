"""
tests/test_specialist_prompts.py — specialist prompt file-loading (T-2/T-3).

Verifies that specialist system prompts are loaded from role-definition markdown
(content) with the FINDING: output contract appended by code (contract), that the
frontmatter `tools:` never influences allowed tools (defense boundary), and that
each role file carries the required sections.

OFFLINE: `_run_query` is monkeypatched; no real API call.
"""

import asyncio

import pytest

from agents.definitions import SPECIALIST_TOOLS
from agents.prompts import (
    SPECIALIST_PROMPT_FILES,
    load_specialist_prompt,
)
from graph import nodes

# Identifiable heading from each loaded role file (proves the file was loaded).
_ROLE_MARKERS = {
    "security": "security reviewer (v14 verify)",
    "tester": "QA / test engineer (v14 verify)",
    "reviewer": "software architect (v14 verify)",
    "validator": "validator (v14 verify)",
}


def _capture_options(monkeypatch, tmp_path, specialist_name):
    """Run real-mode _invoke_specialist with _run_query stubbed; return options."""
    captured = {}

    async def fake_run_query(prompt, options):
        captured["options"] = options
        return "", None

    monkeypatch.setenv("SDD_RUN_REAL_VERIFY", "1")
    monkeypatch.setenv("SDD_OBS_STORE", str(tmp_path / "obs.jsonl"))
    monkeypatch.setattr(nodes, "_run_query", fake_run_query)

    asyncio.run(
        nodes._invoke_specialist(
            specialist_name, str(tmp_path / "artifact.txt"), "taskP",
            worktree_path=str(tmp_path),
        )
    )
    return captured["options"]


class TestPromptLoadedIntoSystemPrompt:
    @pytest.mark.parametrize("name", list(_ROLE_MARKERS))
    def test_system_prompt_has_content_and_contract(self, name, monkeypatch, tmp_path):
        """AC-2.1: system_prompt has (a) loaded-file marker and (b) FINDING: contract."""
        opts = _capture_options(monkeypatch, tmp_path, name)
        sp = opts.system_prompt
        # (a) content from the role file
        assert _ROLE_MARKERS[name] in sp, f"{name}: role file content not loaded"
        # (b) output contract owned by code
        assert "FINDING:" in sp
        assert "[HIGH|MED|LOW]" in sp

    @pytest.mark.parametrize("name", list(_ROLE_MARKERS))
    def test_frontmatter_stripped(self, name, monkeypatch, tmp_path):
        """The YAML frontmatter (name:/description:/tools:) must not leak in."""
        opts = _capture_options(monkeypatch, tmp_path, name)
        first_line = opts.system_prompt.lstrip().splitlines()[0]
        assert not first_line.startswith("tools:")
        assert "tools: Read, Glob, Grep, Bash" not in opts.system_prompt


class TestDefenseBoundaryUnaffected:
    def test_frontmatter_tools_do_not_grant_bash(self, monkeypatch, tmp_path):
        """AC-2.3: security_reviewer.md frontmatter lists Bash, but options.allowed_tools
        is decided ONLY by SPECIALIST_TOOLS (F-2) — Bash must not appear."""
        opts = _capture_options(monkeypatch, tmp_path, "security")
        assert set(opts.allowed_tools) == set(SPECIALIST_TOOLS["security"])
        assert "Bash" not in opts.allowed_tools


class TestFallback:
    def test_missing_file_falls_back_without_crash(self, monkeypatch, tmp_path):
        """AC-2.2: an empty prompt dir → fallback one-liner, no exception, WARNING logged."""
        empty = tmp_path / "empty_prompts"
        empty.mkdir()
        audit = tmp_path / "audit.jsonl"
        monkeypatch.setenv("SDD_SPECIALIST_PROMPT_DIR", str(empty))
        monkeypatch.setenv("SDD_AUDIT_LOG", str(audit))

        # load returns None (missing) and writes a WARNING
        assert load_specialist_prompt("security") is None
        assert audit.exists()
        assert "specialist_prompt_missing" in audit.read_text(encoding="utf-8")

    def test_missing_file_system_prompt_still_has_contract(self, monkeypatch, tmp_path):
        """Even in fallback, the FINDING: contract is appended (contract is code-owned)."""
        empty = tmp_path / "empty_prompts"
        empty.mkdir()
        monkeypatch.setenv("SDD_SPECIALIST_PROMPT_DIR", str(empty))
        monkeypatch.setenv("SDD_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
        opts = _capture_options(monkeypatch, tmp_path, "security")
        assert "FINDING:" in opts.system_prompt
        # fallback one-liner mentions the role
        assert "security" in opts.system_prompt


class TestPromptDirOverride:
    def test_env_override_preferred(self, monkeypatch, tmp_path):
        """AC-2.4: SDD_SPECIALIST_PROMPT_DIR redirects the load source."""
        custom = tmp_path / "custom"
        custom.mkdir()
        (custom / "security_reviewer.md").write_text(
            "---\nname: x\ntools: Bash\n---\n# CUSTOM SECURITY ROLE\ncheck things\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("SDD_SPECIALIST_PROMPT_DIR", str(custom))
        loaded = load_specialist_prompt("security")
        assert "CUSTOM SECURITY ROLE" in loaded
        assert "tools: Bash" not in loaded  # frontmatter still stripped


class TestRoleFileStructure:
    @pytest.mark.parametrize("name", list(SPECIALIST_PROMPT_FILES))
    def test_required_sections_present(self, name):
        """AC-3.1: each role file has checklist / out-of-scope / evidence sections."""
        body = load_specialist_prompt(name)
        assert body is not None, f"{name}: role file missing"
        assert "担当チェックリスト" in body, f"{name}: missing checklist section"
        assert "関心外" in body, f"{name}: missing out-of-scope section"
        assert "根拠必須" in body, f"{name}: missing evidence-required section"
