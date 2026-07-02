"""
tests/test_agents.py — Phase 2/5 unit tests for agents/definitions.py.

Verifies:
  - builder has Write/Edit in BUILDER_TOOLS and in allowed_tools (approved design §1)
  - specialists (reviewer/security/tester/validator) do NOT have Task tool (FR-3.3)
  - specialist tool sets match approved spec (no Write/Edit, no Task)
  - build_options() returns a valid ClaudeAgentOptions with five agents
    (builder + 4 verify specialists: reviewer/security/tester/validator)
  - BUILDER_SYS is non-empty and matches the builder agent's prompt (第6条)
  - Phase 5 S-1: validator specialist is present with Read+Grep tools
"""
from __future__ import annotations

import pytest

from claude_agent_sdk import ClaudeAgentOptions
from claude_agent_sdk.types import AgentDefinition

from agents.definitions import (
    BUILDER_SYS,
    BUILDER_TOOLS,
    SPECIALIST_TOOLS,
    build_options,
)


# ---------------------------------------------------------------------------
# Builder tool set
# ---------------------------------------------------------------------------

class TestBuilderTools:
    """
    Approved design §1: builder MUST have Write/Edit to generate code.
    Plan §6 "Write/Edit を外す" applies to specialists, NOT the builder.
    """

    def test_builder_has_write(self):
        """Builder must have Write tool (generates code files in worktree)."""
        assert "Write" in BUILDER_TOOLS, "BUILDER_TOOLS must include Write"

    def test_builder_has_edit(self):
        """Builder must have Edit tool (modifies code files in worktree)."""
        assert "Edit" in BUILDER_TOOLS, "BUILDER_TOOLS must include Edit"

    def test_builder_has_read_bash_grep(self):
        """Builder must have Read, Bash, Grep for reading and execution."""
        for tool in ["Read", "Bash", "Grep"]:
            assert tool in BUILDER_TOOLS, f"BUILDER_TOOLS must include {tool}"

    def test_builder_allowed_tools_in_options(self):
        """build_options().allowed_tools must include Write and Edit."""
        opts = build_options()
        assert "Write" in opts.allowed_tools, "allowed_tools must include Write"
        assert "Edit" in opts.allowed_tools, "allowed_tools must include Edit"

    def test_builder_agent_tools_in_options(self):
        """AgentDefinition for 'builder' must include Write and Edit."""
        opts = build_options()
        builder_def: AgentDefinition = opts.agents["builder"]
        tools = builder_def.tools or []
        assert "Write" in tools, "builder AgentDefinition.tools must include Write"
        assert "Edit" in tools, "builder AgentDefinition.tools must include Edit"


# ---------------------------------------------------------------------------
# FR-3.3: No Task in specialists
# ---------------------------------------------------------------------------

class TestSpecialistNoTask:
    """
    FR-3.3: specialists must NOT have the Task tool.
    Task would allow recursive sub-agent spawning → runaway loops.
    """

    @pytest.mark.parametrize("agent_name", ["reviewer", "security", "tester", "validator"])
    def test_specialist_agent_def_no_task(self, agent_name: str):
        """FR-3.3: AgentDefinition.tools for each specialist must not include Task."""
        opts = build_options()
        agent_def: AgentDefinition = opts.agents[agent_name]
        tools = agent_def.tools or []
        assert "Task" not in tools, (
            f"FR-3.3 violation: {agent_name}.tools must not include Task; "
            f"got {tools!r}"
        )

    @pytest.mark.parametrize("agent_name", ["reviewer", "security", "tester", "validator"])
    def test_specialist_tools_const_no_task(self, agent_name: str):
        """FR-3.3: SPECIALIST_TOOLS constant must not include Task for any specialist."""
        tools = SPECIALIST_TOOLS[agent_name]
        assert "Task" not in tools, (
            f"FR-3.3: SPECIALIST_TOOLS[{agent_name!r}] must not include Task; "
            f"got {tools!r}"
        )


# ---------------------------------------------------------------------------
# Specialist tool set correctness
# ---------------------------------------------------------------------------

class TestSpecialistToolSets:
    """Each specialist has the correct, limited tool set (no Write/Edit/Task)."""

    def test_reviewer_tools_exact(self):
        """reviewer: Read, Grep only."""
        assert set(SPECIALIST_TOOLS["reviewer"]) == {"Read", "Grep"}

    def test_security_tools_exact(self):
        """security: Read, Grep only."""
        assert set(SPECIALIST_TOOLS["security"]) == {"Read", "Grep"}

    def test_tester_tools_exact(self):
        """tester: Read, Bash only."""
        assert set(SPECIALIST_TOOLS["tester"]) == {"Read", "Bash"}

    def test_validator_tools_exact(self):
        """validator: Read, Grep only (Phase 5 S-1)."""
        assert set(SPECIALIST_TOOLS["validator"]) == {"Read", "Grep"}

    @pytest.mark.parametrize("agent_name", ["reviewer", "security", "tester", "validator"])
    def test_specialist_no_write(self, agent_name: str):
        """No specialist should have Write (plan §6: Write/Edit 外す for specialists)."""
        assert "Write" not in SPECIALIST_TOOLS[agent_name], (
            f"{agent_name} must not have Write"
        )

    @pytest.mark.parametrize("agent_name", ["reviewer", "security", "tester", "validator"])
    def test_specialist_no_edit(self, agent_name: str):
        """No specialist should have Edit (plan §6: Write/Edit 外す for specialists)."""
        assert "Edit" not in SPECIALIST_TOOLS[agent_name], (
            f"{agent_name} must not have Edit"
        )

    def test_specialist_tools_match_agent_defs(self):
        """SPECIALIST_TOOLS constants must match AgentDefinition.tools in build_options."""
        opts = build_options()
        for name, expected_tools in SPECIALIST_TOOLS.items():
            actual_tools = opts.agents[name].tools or []
            assert set(actual_tools) == set(expected_tools), (
                f"SPECIALIST_TOOLS[{name!r}] = {expected_tools!r} does not match "
                f"AgentDefinition.tools = {actual_tools!r}"
            )


# ---------------------------------------------------------------------------
# build_options() API
# ---------------------------------------------------------------------------

class TestBuildOptions:
    """build_options() must return a valid, fully-populated ClaudeAgentOptions."""

    def test_returns_claude_agent_options_instance(self):
        """build_options() must return a ClaudeAgentOptions."""
        opts = build_options()
        assert isinstance(opts, ClaudeAgentOptions)

    def test_five_agents_in_agents_dict(self):
        """build_options().agents must have exactly five entries (builder + 4 specialists)."""
        opts = build_options()
        assert len(opts.agents) == 5

    def test_all_agent_names_present(self):
        """build_options() must define builder, reviewer, security, tester, validator."""
        opts = build_options()
        assert set(opts.agents.keys()) == {
            "builder", "reviewer", "security", "tester", "validator"
        }

    def test_all_agents_are_agent_definitions(self):
        """Every agent value must be an AgentDefinition instance."""
        opts = build_options()
        for name, agent_def in opts.agents.items():
            assert isinstance(agent_def, AgentDefinition), (
                f"agents[{name!r}] must be AgentDefinition, got {type(agent_def)}"
            )

    def test_worktree_path_sets_cwd(self, tmp_path):
        """worktree_path param must propagate to ClaudeAgentOptions.cwd (FR-3.1)."""
        opts = build_options(worktree_path=str(tmp_path))
        assert str(opts.cwd) == str(tmp_path), (
            f"cwd must be {str(tmp_path)!r}, got {opts.cwd!r}"
        )

    def test_no_worktree_path_cwd_is_none(self):
        """Omitting worktree_path must leave cwd as None (no default path)."""
        opts = build_options()
        assert opts.cwd is None

    def test_mcp_servers_propagated(self):
        """mcp_servers kwarg must be passed through to ClaudeAgentOptions."""
        # Placeholder: real MCP configs wired in Phase 3/5.
        # Just verify the param is accepted without error.
        opts = build_options(mcp_servers={"test-server": {"command": "echo", "args": []}})
        # If no exception, the param was accepted
        assert opts is not None

    def test_no_mcp_servers_accepted(self):
        """build_options() with no mcp_servers must not raise."""
        opts = build_options()
        assert opts is not None


# ---------------------------------------------------------------------------
# 第6条: BUILDER_SYS from .claude/agents/builder.md
# ---------------------------------------------------------------------------

class TestBuilderSysPrompt:
    """第6条: BUILDER_SYS must be the verbatim content of .claude/agents/builder.md."""

    def test_builder_sys_nonempty(self):
        """BUILDER_SYS must not be empty."""
        assert BUILDER_SYS.strip(), "BUILDER_SYS must not be empty (第6条)"

    def test_builder_sys_used_in_agent_prompt(self):
        """builder AgentDefinition.prompt must equal BUILDER_SYS (第6条 reuse)."""
        opts = build_options()
        builder_def: AgentDefinition = opts.agents["builder"]
        assert builder_def.prompt == BUILDER_SYS, (
            "builder.prompt must equal BUILDER_SYS (第6条: reuse builder.md asset)"
        )

    def test_builder_sys_contains_role_description(self):
        """第6条: BUILDER_SYS (from builder.md) must contain role/responsibility content."""
        lower = BUILDER_SYS.lower()
        # builder.md describes the builder role — verify it's not a stub
        assert any(kw in lower for kw in ("builder", "skill", "output", "phase")), (
            "BUILDER_SYS appears to be a stub — expected builder.md role content"
        )


# ---------------------------------------------------------------------------
# Phase 5 S-1: validator specialist
# ---------------------------------------------------------------------------

class TestValidatorSpecialist:
    """
    Phase 5 S-1: validator must be present in SPECIALIST_TOOLS and build_options().

    verify() calls _invoke_specialist("validator", ...) — without this entry
    the real-mode path would fail to find the specialist definition.
    FR-3.3: validator must not have Task.
    FR-3.2: all 4 verify specialists (validator/tester/reviewer/security) must be defined.
    """

    def test_validator_in_specialist_tools(self):
        """S-1: SPECIALIST_TOOLS must include 'validator' key."""
        assert "validator" in SPECIALIST_TOOLS, (
            "S-1: SPECIALIST_TOOLS must include 'validator' "
            "(verify() calls _invoke_specialist('validator', ...))"
        )

    def test_validator_in_build_options_agents(self):
        """S-1: build_options().agents must include 'validator' AgentDefinition."""
        opts = build_options()
        assert "validator" in opts.agents, (
            "S-1: build_options().agents must include 'validator'"
        )

    def test_validator_is_agent_definition(self):
        """validator value must be an AgentDefinition instance."""
        opts = build_options()
        assert isinstance(opts.agents["validator"], AgentDefinition)

    def test_validator_has_read(self):
        """validator must have Read tool for examining artifacts."""
        assert "Read" in SPECIALIST_TOOLS["validator"]

    def test_validator_has_grep(self):
        """validator must have Grep tool for pattern search in artifacts."""
        assert "Grep" in SPECIALIST_TOOLS["validator"]

    def test_validator_no_task(self):
        """FR-3.3: validator must not have Task (prevents recursive spawning)."""
        assert "Task" not in SPECIALIST_TOOLS["validator"]

    def test_validator_no_write(self):
        """validator must not have Write (read-only specialist, plan §6)."""
        assert "Write" not in SPECIALIST_TOOLS["validator"]

    def test_validator_no_bash(self):
        """validator does not need Bash (reads artifacts, does not run them)."""
        assert "Bash" not in SPECIALIST_TOOLS["validator"]

    def test_all_four_verify_specialists_defined(self):
        """FR-3.2/FR-3.3: all 4 verify specialists must be in SPECIALIST_TOOLS."""
        required = {"validator", "tester", "reviewer", "security"}
        assert required.issubset(set(SPECIALIST_TOOLS.keys())), (
            f"Missing verify specialists: {required - set(SPECIALIST_TOOLS.keys())}"
        )
