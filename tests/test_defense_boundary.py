"""
tests/test_defense_boundary.py — defense-boundary wiring fix (2026-07-03).

Verifies the F-1..F-6 fix that re-connected the 第4/5条 two-layer defense to the
real Agent SDK execution paths (regression introduced by the real-mode wiring):

  AC-1.1/1.3  real specialist options carry hooks=make_hooks() (PreToolUse present)
  AC-1.2      no forced permission bypass — permission_mode left at SDK default
  AC-1.4      the PreToolUse callback DENIES a forbidden Bash command (rm -rf)
  AC-3.1      build_options() always attaches non-None hooks (builder path)
  AC-3.2      the builder-path hook likewise denies a forbidden command
  AC-6.1      specialist cwd == worktree ROOT even when the artifact is in a subdir

All tests are OFFLINE: the SDK-touching `_run_query` is monkeypatched; no real
API call is made.  make_hooks() only builds callbacks — it never reaches out.
"""

import asyncio
from pathlib import Path

from agents.definitions import build_options
from harness.hooks import make_hooks
from graph import nodes


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _pre_tool_use_callback(hooks: dict):
    """Extract the PreToolUse callback from a make_hooks()-style dict."""
    assert hooks is not None, "hooks must not be None"
    assert "PreToolUse" in hooks, "hooks must contain a PreToolUse matcher"
    matcher = hooks["PreToolUse"][0]
    return matcher.hooks[0]


def _capture_specialist_options(monkeypatch, tmp_path, *, artifact_ref, worktree_path):
    """Run real-mode _invoke_specialist with _run_query stubbed; return options."""
    captured = {}

    async def fake_run_query(prompt, options):
        captured["options"] = options
        return "", None  # no findings, no ResultMessage

    monkeypatch.setenv("SDD_RUN_REAL_VERIFY", "1")
    monkeypatch.setenv("SDD_OBS_STORE", str(tmp_path / "obs.jsonl"))
    monkeypatch.setattr(nodes, "_run_query", fake_run_query)

    asyncio.run(
        nodes._invoke_specialist(
            "reviewer", artifact_ref, "taskB", worktree_path=worktree_path
        )
    )
    return captured["options"]


# ---------------------------------------------------------------------------
# F-1: specialist hooks wiring
# ---------------------------------------------------------------------------

class TestSpecialistHooksWired:
    def test_specialist_options_carry_pretooluse_hooks(self, monkeypatch, tmp_path):
        """AC-1.3: real specialist options.hooks is non-None with a PreToolUse matcher."""
        opts = _capture_specialist_options(
            monkeypatch, tmp_path,
            artifact_ref=str(tmp_path / "artifact.txt"),
            worktree_path=str(tmp_path),
        )
        assert opts.hooks is not None
        assert "PreToolUse" in opts.hooks

    def test_specialist_options_have_no_bypass(self, monkeypatch, tmp_path):
        """AC-1.1: real specialist must NOT disable the permission system.

        permission_mode is left at the SDK default (None) — the permission
        system stays active and the hooks provide the soft boundary.
        """
        opts = _capture_specialist_options(
            monkeypatch, tmp_path,
            artifact_ref=str(tmp_path / "artifact.txt"),
            worktree_path=str(tmp_path),
        )
        assert getattr(opts, "permission_mode", None) is None


# ---------------------------------------------------------------------------
# F-1/F-3: the PreToolUse callback actually denies dangerous ops
# ---------------------------------------------------------------------------

class TestHookDeniesForbiddenCommand:
    def test_specialist_hook_denies_rm_rf(self):
        """AC-1.4: the make_hooks() PreToolUse callback denies `rm -rf`."""
        cb = _pre_tool_use_callback(make_hooks())
        decision = asyncio.run(
            cb({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}, None, None)
        )
        out = decision["hookSpecificOutput"]
        assert out["permissionDecision"] == "deny"

    def test_builder_hook_denies_rm_rf(self):
        """AC-3.2: the builder-path hook (from build_options) denies `rm -rf`."""
        cb = _pre_tool_use_callback(build_options().hooks)
        decision = asyncio.run(
            cb({"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}, None, None)
        )
        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_hook_allows_safe_read(self):
        """Sanity: safe read-only tools are auto-approved (no approval flood)."""
        cb = _pre_tool_use_callback(make_hooks())
        decision = asyncio.run(
            cb({"tool_name": "Read", "tool_input": {"file_path": "/x/a.txt"}}, None, None)
        )
        assert decision["hookSpecificOutput"]["permissionDecision"] == "allow"


# ---------------------------------------------------------------------------
# F-3: build_options always attaches hooks
# ---------------------------------------------------------------------------

class TestBuildOptionsHooks:
    def test_default_hooks_non_none(self):
        """AC-3.1: build_options() with no hooks arg still attaches make_hooks()."""
        opts = build_options()
        assert opts.hooks is not None
        assert "PreToolUse" in opts.hooks

    def test_hooks_none_defaults_to_make_hooks(self):
        """Explicitly passing hooks=None must NOT leave the builder unguarded."""
        opts = build_options(hooks=None)
        assert opts.hooks is not None
        assert "PreToolUse" in opts.hooks

    def test_explicit_hooks_override_respected(self):
        """A caller-supplied hooks dict is used verbatim (override path)."""
        sentinel = {"PreToolUse": []}
        opts = build_options(hooks=sentinel)
        assert opts.hooks is sentinel


# ---------------------------------------------------------------------------
# F-6: specialist cwd is the worktree root, not the artifact's parent
# ---------------------------------------------------------------------------

class TestSpecialistCwd:
    def test_cwd_is_worktree_root_for_subdir_artifact(self, monkeypatch, tmp_path):
        """AC-6.1: artifact in a subdir → cwd is the worktree root (not the subdir)."""
        root = tmp_path / "wt"
        (root / "src").mkdir(parents=True)
        artifact = root / "src" / "main.py"
        artifact.write_text("print('hi')\n")

        opts = _capture_specialist_options(
            monkeypatch, tmp_path,
            artifact_ref=str(artifact),
            worktree_path=str(root),
        )
        assert opts.cwd == str(root)

    def test_cwd_falls_back_to_artifact_parent_when_no_worktree(self, monkeypatch, tmp_path):
        """When worktree_path is empty, cwd falls back to the artifact's parent."""
        artifact = tmp_path / "flat" / "artifact.txt"
        artifact.parent.mkdir(parents=True)
        artifact.write_text("x\n")

        opts = _capture_specialist_options(
            monkeypatch, tmp_path,
            artifact_ref=str(artifact),
            worktree_path="",
        )
        assert opts.cwd == str(artifact.parent)
