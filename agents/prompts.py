"""
agents/prompts.py — specialist system-prompt loading (T-2, v12 asset loading).

第6条 (reuse): specialist role definitions live in markdown files (like the
builder's BUILDER_SYS comes from .claude/agents/builder.md), NOT hardcoded as
strings in graph/nodes.py.  This module loads them at runtime.

Separation of content and contract (design principle 2):
  - CONTENT  (what to look for) → the markdown files loaded here.
  - CONTRACT (how to report: the FINDING: format) → owned by graph/nodes.py
    (`_OUTPUT_CONTRACT`), appended programmatically.  This module never defines
    the output format, so a downstream project can swap the role files without
    breaking `_parse_findings`.

Defense boundary (design principle 3): the markdown frontmatter may declare a
`tools:` line (a v12 team-roster leftover, e.g. security_reviewer.md lists Bash).
It is IGNORED — allowed tools are decided solely by agents.definitions.SPECIALIST_TOOLS
(F-2 decision, 第4/5条).  This module strips the frontmatter and never reads `tools:`.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

# Default directory holding the v14-adapted specialist role definitions.
# Overridable via SDD_SPECIALIST_PROMPT_DIR so downstream projects can supply
# their own role files without editing code.
_DEFAULT_PROMPT_DIR: Path = (
    Path(__file__).resolve().parent.parent / "templates" / "agents" / "v14"
)

# specialist role → markdown filename (within the prompt dir).
SPECIALIST_PROMPT_FILES: dict[str, str] = {
    "security": "security_reviewer.md",
    "tester": "qa_test_engineer.md",
    "reviewer": "software_architect.md",
    "validator": "validator.md",
}

_DEFAULT_AUDIT_LOG: str = "logs/audit.jsonl"


def _prompt_dir() -> Path:
    """Resolve the prompt directory (env override → default)."""
    override = os.environ.get("SDD_SPECIALIST_PROMPT_DIR")
    return Path(override) if override else _DEFAULT_PROMPT_DIR


def _strip_frontmatter(text: str) -> str:
    """
    Remove a leading YAML frontmatter block (``---`` … ``---``) if present.

    The frontmatter's ``tools:`` line is deliberately NOT parsed — allowed tools
    come only from SPECIALIST_TOOLS (design principle 3).  Anything before/without
    a frontmatter block is returned unchanged.
    """
    if not text.startswith("---"):
        return text.lstrip("\n")
    lines = text.splitlines()
    # lines[0] == "---"; find the closing "---".
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1:]).lstrip("\n")
    # No closing fence → treat the whole thing as body (defensive).
    return text


def _warn_audit(specialist_name: str, path: Path) -> None:
    """
    Append a WARNING record to the audit log when a prompt file is missing.

    Never raises — a logging failure must not crash verify (design: fallback is
    graceful).  Uses SDD_AUDIT_LOG (or logs/audit.jsonl) like harness.hooks.
    """
    log_path = Path(os.environ.get("SDD_AUDIT_LOG", _DEFAULT_AUDIT_LOG))
    record = {
        "level": "WARNING",
        "event": "specialist_prompt_missing",
        "specialist": specialist_name,
        "path": str(path),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — logging must never break verify
        pass


def load_specialist_prompt(specialist_name: str) -> str | None:
    """
    Load a specialist's role-definition prompt (content only, frontmatter stripped).

    Returns:
        The markdown body (str) with any YAML frontmatter removed, or ``None``
        when the file is unmapped/missing/unreadable.  On a missing file a
        WARNING is written to the audit log and None is returned so the caller
        can fall back to the built-in one-liner (never crashes — AC-2.2).

    The returned content is CONTENT only; the FINDING: output CONTRACT is added
    by the caller (graph/nodes.py `_OUTPUT_CONTRACT`), keeping the two separable.
    """
    filename = SPECIALIST_PROMPT_FILES.get(specialist_name)
    if filename is None:
        return None
    path = _prompt_dir() / filename
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError):
        _warn_audit(specialist_name, path)
        return None
    body = _strip_frontmatter(raw).strip()
    return body or None
