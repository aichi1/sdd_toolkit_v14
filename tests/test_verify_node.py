"""
tests/test_verify_node.py — Phase 4 (T4.3) unit tests for the verify node.

FR-3.2 / FR-3.3 / S1 verification:
  FR-3.2: 4 specialists run in parallel; findings merged without overwrite.
  FR-3.3: specialists have no Task tool (verified via agents.definitions).
  S1:     reject→rebuild→reverify cycle does NOT accumulate stale findings.
  Seam:   _invoke_specialist is monkeypatched → zero real API calls.

Test strategy:
  - Mock _invoke_specialist with async functions returning controlled findings.
  - Call verify() directly with a minimal TaskState dict.
  - Assert the returned verify_findings list contains all specialists' output.
  - Simulate the full reduce_findings cycle to verify S1 non-accumulation.
  - Test FR-3.3 by inspecting SPECIALIST_TOOLS (no Task entry).
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

import graph.nodes as nodes_module
from graph.nodes import _invoke_specialist, verify, _run_verify_parallel
from graph.state import reduce_findings
from agents.definitions import SPECIALIST_TOOLS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_state(**overrides) -> dict[str, Any]:
    """Minimal valid TaskState dict for verify node tests."""
    state: dict[str, Any] = {
        "task_id": "verify-test-task",
        "spec_path": "/tmp/spec.md",
        "constitution_digest": "sha256:aabbccdd",
        "context_slice_ids": [],
        "worktree_path": "/tmp/wt",
        "build_artifact_ref": "/tmp/wt/artifact.txt",
        "verify_findings": [],
        "eval_score": None,
        "attempt": 0,
        "decision": None,
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# Tests: FR-3.2 — parallel execution, no overwrite
# ---------------------------------------------------------------------------

class TestVerifyNodeParallelMerge:
    """
    FR-3.2: verify() must run 4 specialists in parallel and merge their
    findings without any specialist's output being overwritten.
    """

    def test_all_four_specialists_called(self, monkeypatch):
        """
        FR-3.2: _invoke_specialist must be called for all 4 specialists.
        (validator, tester, reviewer, security)
        """
        calls: list[str] = []

        async def mock_specialist(name: str, artifact_ref: str, task_id: str, worktree_path: str = "") -> list[str]:
            calls.append(name)
            return [f"{name}:finding"]

        monkeypatch.setattr(nodes_module, "_invoke_specialist", mock_specialist)

        verify(_base_state())

        assert set(calls) == {"validator", "tester", "reviewer", "security"}, (
            f"FR-3.2: expected 4 specialist calls; got {calls!r}"
        )

    def test_findings_from_all_specialists_present(self, monkeypatch):
        """
        FR-3.2: The returned verify_findings must include contributions from
        ALL 4 specialists — none must be overwritten by another.
        """
        async def mock_specialist(name: str, artifact_ref: str, task_id: str, worktree_path: str = "") -> list[str]:
            return [f"{name}:result-1", f"{name}:result-2"]

        monkeypatch.setattr(nodes_module, "_invoke_specialist", mock_specialist)

        result = verify(_base_state())
        findings = result["verify_findings"]

        for specialist in ("validator", "tester", "reviewer", "security"):
            assert f"{specialist}:result-1" in findings, (
                f"FR-3.2: {specialist} finding-1 missing — was overwritten?"
            )
            assert f"{specialist}:result-2" in findings, (
                f"FR-3.2: {specialist} finding-2 missing — was overwritten?"
            )

    def test_total_finding_count_is_sum_of_all_specialists(self, monkeypatch):
        """
        FR-3.2: no findings must be lost in the merge.
        4 specialists × 2 findings each = 8 total.
        """
        async def mock_specialist(name: str, artifact_ref: str, task_id: str, worktree_path: str = "") -> list[str]:
            return [f"{name}:a", f"{name}:b"]

        monkeypatch.setattr(nodes_module, "_invoke_specialist", mock_specialist)

        result = verify(_base_state())
        findings = result["verify_findings"]

        assert len(findings) == 8, (
            f"FR-3.2: expected 8 findings (4×2); got {len(findings)}: {findings!r}"
        )

    def test_verify_returns_dict_with_verify_findings_key(self, monkeypatch):
        """verify() must return a dict with 'verify_findings' key."""
        async def mock_specialist(name, artifact_ref, task_id, worktree_path=""):
            return []

        monkeypatch.setattr(nodes_module, "_invoke_specialist", mock_specialist)

        result = verify(_base_state())

        assert isinstance(result, dict), "verify() must return a dict"
        assert "verify_findings" in result, "result must have 'verify_findings' key"
        assert isinstance(result["verify_findings"], list)

    def test_verify_returns_empty_when_no_findings(self, monkeypatch):
        """verify() returns [] when all specialists find nothing."""
        async def mock_specialist(name, artifact_ref, task_id, worktree_path=""):
            return []

        monkeypatch.setattr(nodes_module, "_invoke_specialist", mock_specialist)

        result = verify(_base_state())
        assert result["verify_findings"] == []

    def test_verify_passes_artifact_ref_to_specialists(self, monkeypatch):
        """Each specialist must receive the build_artifact_ref from state."""
        received_refs: list[str] = []

        async def mock_specialist(name: str, artifact_ref: str, task_id: str, worktree_path: str = "") -> list[str]:
            received_refs.append(artifact_ref)
            return []

        monkeypatch.setattr(nodes_module, "_invoke_specialist", mock_specialist)

        expected_ref = "/tmp/wt/artifact.txt"
        verify(_base_state(build_artifact_ref=expected_ref))

        assert all(ref == expected_ref for ref in received_refs), (
            f"All specialists must receive artifact_ref={expected_ref!r}; "
            f"got {received_refs!r}"
        )

    def test_verify_passes_task_id_to_specialists(self, monkeypatch):
        """Each specialist must receive the task_id from state."""
        received_ids: list[str] = []

        async def mock_specialist(name: str, artifact_ref: str, task_id: str, worktree_path: str = "") -> list[str]:
            received_ids.append(task_id)
            return []

        monkeypatch.setattr(nodes_module, "_invoke_specialist", mock_specialist)

        verify(_base_state(task_id="my-special-task"))

        assert all(tid == "my-special-task" for tid in received_ids), (
            f"All specialists must receive task_id; got {received_ids!r}"
        )


# ---------------------------------------------------------------------------
# Tests: FR-3.3 — specialists must NOT have Task tool
# ---------------------------------------------------------------------------

class TestSpecialistsNoTask:
    """
    FR-3.3: Each specialist sub-agent's tool list must NOT include 'Task'.
    Task would allow recursive sub-agent spawning → unbound loops.
    """

    @pytest.mark.parametrize("specialist", ["reviewer", "security", "tester", "validator"])
    def test_specialist_tools_no_task(self, specialist: str):
        """
        FR-3.3: SPECIALIST_TOOLS[specialist] must not include 'Task'.
        Verified via agents.definitions.SPECIALIST_TOOLS constant.
        Phase 5 S-1: covers all 4 verify specialists including validator.
        """
        tools = SPECIALIST_TOOLS[specialist]
        assert "Task" not in tools, (
            f"FR-3.3 violation: SPECIALIST_TOOLS[{specialist!r}] must not "
            f"include 'Task'; got {tools!r}"
        )

    def test_all_four_specialists_covered(self):
        """
        SPECIALIST_TOOLS must define tools for all 4 verify specialist types.
        Phase 5 S-1: added validator to complete the set.
        """
        expected = {"reviewer", "security", "tester", "validator"}
        assert set(SPECIALIST_TOOLS.keys()) >= expected, (
            f"Missing specialist definitions: {expected - set(SPECIALIST_TOOLS.keys())}"
        )


# ---------------------------------------------------------------------------
# Tests: S1 resolved — non-accumulation across reject→rebuild cycles
# ---------------------------------------------------------------------------

class TestS1NonAccumulation:
    """
    S1 resolved: verify_findings must NOT accumulate across reject→rebuild→reverify.

    Verify:
      1. reduce_findings(old, None) → []    (build round reset)
      2. reduce_findings([], [findings]) → [findings]  (verify append)
      3. Full round-trip: round 1 findings NOT present in round 2 state.
    """

    def test_verify_combined_with_build_reset_via_reducer(self, monkeypatch):
        """
        S1: simulate two build→verify rounds; verify round 2 has only round 2 findings.

        Round 1: build (reset) → verify ([f1, f2]) → state: [f1, f2]
        Round 2: build (reset) → verify ([f3, f4]) → state: [f3, f4]
        Assert: round 2 state does NOT contain f1, f2.
        """
        round_findings = {"current": ["f1", "f2"]}

        async def mock_specialist(name, artifact_ref, task_id, worktree_path=""):
            return [round_findings["current"][0], round_findings["current"][1]]

        monkeypatch.setattr(nodes_module, "_invoke_specialist", mock_specialist)

        # --- Round 1 ---
        state_vf: list[str] = []  # initial state

        # build node returns None → reduce_findings([], None) = []
        state_vf = reduce_findings(state_vf, None)
        assert state_vf == [], "S1: build round 1 must reset to []"

        # verify round 1 returns findings, reducer appends
        round1_result = verify(_base_state())
        state_vf = reduce_findings(state_vf, round1_result["verify_findings"])
        assert "f1" in state_vf
        assert "f2" in state_vf

        # --- Reject → Round 2 ---
        round_findings["current"] = ["f3", "f4"]

        # build node returns None → reduce_findings([f1,f2], None) = []
        state_vf = reduce_findings(state_vf, None)
        assert state_vf == [], (
            "S1: build round 2 must reset to [] — old findings must be cleared"
        )

        # verify round 2 appends fresh findings
        round2_result = verify(_base_state())
        state_vf = reduce_findings(state_vf, round2_result["verify_findings"])

        assert "f3" in state_vf, "Round 2 findings must be present"
        assert "f4" in state_vf, "Round 2 findings must be present"
        assert "f1" not in state_vf, "S1: stale f1 from round 1 must NOT appear in round 2"
        assert "f2" not in state_vf, "S1: stale f2 from round 1 must NOT appear in round 2"

    def test_multiple_parallel_findings_within_one_round_not_overwritten(self, monkeypatch):
        """
        FR-3.2 (parallel within round): within a single verify call, findings
        from all 4 specialists must be present (none lost due to overwrite).
        """
        async def mock_specialist(name, artifact_ref, task_id, worktree_path=""):
            return [f"{name}-finding"]

        monkeypatch.setattr(nodes_module, "_invoke_specialist", mock_specialist)

        # Simulate state after build reset
        state_vf = reduce_findings([], None)
        assert state_vf == []

        # verify returns merged findings from all 4
        result = verify(_base_state())
        state_vf = reduce_findings(state_vf, result["verify_findings"])

        for name in ("validator", "tester", "reviewer", "security"):
            assert f"{name}-finding" in state_vf, (
                f"FR-3.2: {name} finding missing — parallel merge may have overwritten"
            )


# ---------------------------------------------------------------------------
# Tests: _invoke_specialist seam (no real API calls)
# ---------------------------------------------------------------------------

class TestInvokeSpecialistSeam:
    """
    Verify the injectable seam _invoke_specialist:
      - In stub mode (no SDD_RUN_REAL_VERIFY), returns [] without API calls.
      - Is monkeypatchable for test isolation.
      - No real API or network calls.
    """

    def test_stub_mode_returns_empty_list(self, monkeypatch):
        """_invoke_specialist returns [] in stub mode (no SDD_RUN_REAL_VERIFY)."""
        monkeypatch.delenv("SDD_RUN_REAL_VERIFY", raising=False)
        result = asyncio.run(_invoke_specialist("validator", "/tmp/art.txt", "task-1"))
        assert result == [], (
            "_invoke_specialist stub mode must return [] (no API call)"
        )

    def test_stub_mode_for_all_specialist_names(self, monkeypatch):
        """All 4 specialist names return [] in stub mode."""
        monkeypatch.delenv("SDD_RUN_REAL_VERIFY", raising=False)
        for name in ("validator", "tester", "reviewer", "security"):
            result = asyncio.run(_invoke_specialist(name, "/tmp/art.txt", "task"))
            assert result == [], f"{name} stub must return []"

    def test_seam_is_monkeypatchable(self, monkeypatch):
        """_invoke_specialist can be replaced by monkeypatch in tests."""
        async def spy(name, artifact_ref, task_id, worktree_path=""):
            return [f"mocked-{name}"]

        monkeypatch.setattr(nodes_module, "_invoke_specialist", spy)

        result = verify(_base_state())
        findings = result["verify_findings"]

        assert "mocked-validator" in findings
        assert "mocked-tester" in findings
        assert "mocked-reviewer" in findings
        assert "mocked-security" in findings

    def test_no_real_api_calls_without_env_var(self, monkeypatch):
        """
        Without SDD_RUN_REAL_VERIFY=1, _invoke_specialist must not make
        any network/API calls.  Verify by confirming it returns immediately
        without raising network-related exceptions.
        """
        import socket

        monkeypatch.delenv("SDD_RUN_REAL_VERIFY", raising=False)

        # Block all network access (belt-and-suspenders)
        original_getaddrinfo = socket.getaddrinfo

        def blocked_getaddrinfo(*args, **kwargs):
            raise OSError("Network blocked in test: no real API calls allowed")

        monkeypatch.setattr(socket, "getaddrinfo", blocked_getaddrinfo)

        # Must not raise (stub returns [] without touching the network)
        result = asyncio.run(_invoke_specialist("validator", "/tmp/art.txt", "task"))
        assert result == []

    def test_real_mode_runs_via_query_seam(self, tmp_path, monkeypatch):
        """
        Post-v14 wiring: SDD_RUN_REAL_VERIFY=1 no longer raises NotImplementedError.
        It runs the specialist via the mockable _run_query seam, parses
        'FINDING:' lines, and records the call's cost.  (The former
        NotImplementedError contract is replaced — see .steering/
        20260703-real-agent-sdk-wiring.)  Full offline coverage lives in
        tests/test_real_agent_sdk.py; this test just guards the seam contract.
        """
        import graph.nodes as nodes_mod

        monkeypatch.setenv("SDD_RUN_REAL_VERIFY", "1")
        monkeypatch.setenv("SDD_OBS_STORE", str(tmp_path / "obs.jsonl"))

        async def fake_run_query(prompt, options):
            from types import SimpleNamespace
            rm = SimpleNamespace(total_cost_usd=0.0, usage={}, result=None, num_turns=1)
            return "FINDING: example issue", rm

        monkeypatch.setattr(nodes_mod, "_run_query", fake_run_query)
        result = asyncio.run(_invoke_specialist("validator", "/tmp/art.txt", "task"))
        assert result == ["[validator] example issue"]


# ---------------------------------------------------------------------------
# Tests: _run_verify_parallel async helper
# ---------------------------------------------------------------------------

class TestRunVerifyParallel:
    """Tests for the internal _run_verify_parallel coroutine."""

    def test_returns_list(self, monkeypatch):
        """_run_verify_parallel must return a list."""
        async def mock_specialist(name, artifact_ref, task_id, worktree_path=""):
            return []

        monkeypatch.setattr(nodes_module, "_invoke_specialist", mock_specialist)
        result = asyncio.run(_run_verify_parallel(_base_state()))
        assert isinstance(result, list)

    def test_merges_all_specialist_results(self, monkeypatch):
        """_run_verify_parallel merges results from all 4 specialists."""
        async def mock_specialist(name, artifact_ref, task_id, worktree_path=""):
            return [f"{name}:x"]

        monkeypatch.setattr(nodes_module, "_invoke_specialist", mock_specialist)
        result = asyncio.run(_run_verify_parallel(_base_state()))
        assert len(result) == 4
        for name in ("validator", "tester", "reviewer", "security"):
            assert f"{name}:x" in result
