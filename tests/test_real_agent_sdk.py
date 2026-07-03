"""
tests/test_real_agent_sdk.py — Offline tests for the real Agent SDK wiring
(.steering/20260703-real-agent-sdk-wiring).

All tests are OFFLINE: the SDK-touching `_run_query` / `query` are monkeypatched,
so no network or API key is used.  Default `pytest` stays fully offline.

Covers:
  - pure helpers: _parse_findings, _extract_cost, _resolve_artifact
  - observability: record_agent_call / sum_agent_costs (agent_call rows only)
  - real _invoke_specialist: findings parsed, cost recorded, failure isolated, FR-3.3
  - real _invoke_builder: manifest resolution + builder cost row
  - eval_node: cost is the sum of agent_call rows (real), 0.0 in stub mode
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import graph.nodes as nodes
from harness.observability import (
    read_observations,
    record_agent_call,
    sum_agent_costs,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

def _fake_result(cost=0.01, inp=100, out=50):
    return SimpleNamespace(
        total_cost_usd=cost,
        usage={"input_tokens": inp, "output_tokens": out},
        num_turns=1,
        result=None,
    )


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

class TestParseFindings:
    def test_extracts_finding_lines_with_role(self):
        text = "FINDING: SQL injection in query\nsome noise\nFINDING: hardcoded secret"
        out = nodes._parse_findings(text, "security")
        assert out == [
            "[security] SQL injection in query",
            "[security] hardcoded secret",
        ]

    def test_no_findings_returns_empty(self):
        assert nodes._parse_findings("all good, nothing to report", "reviewer") == []

    def test_empty_text_returns_empty(self):
        assert nodes._parse_findings("", "tester") == []


class TestExtractCost:
    def test_dict_usage(self):
        cost, toks = nodes._extract_cost(_fake_result(cost=0.02, inp=10, out=5))
        assert cost == 0.02
        assert toks == {"input": 10, "output": 5}

    def test_object_usage(self):
        rm = SimpleNamespace(
            total_cost_usd=0.03,
            usage=SimpleNamespace(input_tokens=7, output_tokens=3),
        )
        cost, toks = nodes._extract_cost(rm)
        assert cost == 0.03
        assert toks == {"input": 7, "output": 3}

    def test_missing_fields_default_zero(self):
        cost, toks = nodes._extract_cost(SimpleNamespace())
        assert cost == 0.0
        assert toks == {"input": 0, "output": 0}


class TestResolveArtifact:
    def test_manifest_primary_relative(self, tmp_path):
        (tmp_path / ".sdd").mkdir()
        (tmp_path / ".sdd" / "artifact_manifest.json").write_text(
            json.dumps({"primary_artifact": "src/main.py"})
        )
        assert nodes._resolve_artifact(str(tmp_path)) == str(tmp_path / "src/main.py")

    def test_fallback_artifact_txt(self, tmp_path):
        assert nodes._resolve_artifact(str(tmp_path)) == str(tmp_path / "artifact.txt")

    def test_bad_manifest_falls_back(self, tmp_path):
        (tmp_path / ".sdd").mkdir()
        (tmp_path / ".sdd" / "artifact_manifest.json").write_text("{not json")
        assert nodes._resolve_artifact(str(tmp_path)) == str(tmp_path / "artifact.txt")


# ---------------------------------------------------------------------------
# observability: agent_call rows
# ---------------------------------------------------------------------------

class TestAgentCostRecords:
    def test_record_and_sum(self, tmp_path, monkeypatch):
        store = tmp_path / "obs.jsonl"
        monkeypatch.setenv("SDD_OBS_STORE", str(store))
        record_agent_call("taskA", "builder", 0.01, {"input": 100, "output": 50})
        record_agent_call("taskA", "security", 0.02, {"input": 200, "output": 20})
        cost, toks = sum_agent_costs("taskA")
        assert abs(cost - 0.03) < 1e-9
        assert toks == {"input": 300, "output": 70}

    def test_sum_excludes_eval_rows(self, tmp_path, monkeypatch):
        store = tmp_path / "obs.jsonl"
        monkeypatch.setenv("SDD_OBS_STORE", str(store))
        # eval-run record (no record_type) must NOT be counted
        nodes.record_run("taskB", total_cost_usd=99.0, tokens={"input": 9, "output": 9})
        record_agent_call("taskB", "tester", 0.05, {"input": 1, "output": 1})
        cost, toks = sum_agent_costs("taskB")
        assert abs(cost - 0.05) < 1e-9
        assert toks == {"input": 1, "output": 1}

    def test_no_rows_returns_zero(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SDD_OBS_STORE", str(tmp_path / "obs.jsonl"))
        assert sum_agent_costs("nope") == (0.0, {"input": 0, "output": 0})


# ---------------------------------------------------------------------------
# real _invoke_specialist
# ---------------------------------------------------------------------------

class TestRealSpecialist:
    def test_findings_parsed_and_cost_recorded(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SDD_RUN_REAL_VERIFY", "1")
        monkeypatch.setenv("SDD_OBS_STORE", str(tmp_path / "obs.jsonl"))
        artifact = tmp_path / "artifact.txt"
        artifact.write_text("code")

        captured = {}

        async def fake_run_query(prompt, options):
            captured["options"] = options
            return "FINDING: os.system with user input\n", _fake_result(cost=0.04)

        monkeypatch.setattr(nodes, "_run_query", fake_run_query)

        out = asyncio.run(
            nodes._invoke_specialist("security", str(artifact), "taskX")
        )
        assert out == ["[security] os.system with user input"]
        # FR-3.3: real options must not grant the Task tool
        assert "Task" not in captured["options"].allowed_tools
        # cost recorded as an agent_call row keyed by task_id
        cost, _ = sum_agent_costs("taskX")
        assert abs(cost - 0.04) < 1e-9

    def test_failure_isolated_to_error_finding(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SDD_RUN_REAL_VERIFY", "1")
        monkeypatch.setenv("SDD_OBS_STORE", str(tmp_path / "obs.jsonl"))

        async def boom(prompt, options):
            raise RuntimeError("api exploded")

        monkeypatch.setattr(nodes, "_run_query", boom)
        out = asyncio.run(nodes._invoke_specialist("tester", "/x/artifact.txt", "t"))
        assert len(out) == 1
        assert out[0].startswith("[tester] ERROR:")
        assert "api exploded" in out[0]

    def test_stub_mode_unaffected(self, monkeypatch):
        monkeypatch.delenv("SDD_RUN_REAL_VERIFY", raising=False)
        out = asyncio.run(nodes._invoke_specialist("reviewer", "/x/a.txt", "t"))
        assert out == []


# ---------------------------------------------------------------------------
# real _invoke_builder
# ---------------------------------------------------------------------------

class TestRealBuilder:
    def test_manifest_and_cost(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SDD_RUN_REAL_BUILDER", "1")
        monkeypatch.setenv("SDD_OBS_STORE", str(tmp_path / "obs.jsonl"))
        (tmp_path / ".sdd").mkdir()
        (tmp_path / ".sdd" / "artifact_manifest.json").write_text(
            json.dumps({"primary_artifact": "out.py"})
        )

        async def fake_run_query(prompt, options):
            return "done", _fake_result(cost=0.07, inp=500, out=300)

        monkeypatch.setattr(nodes, "_run_query", fake_run_query)

        path = asyncio.run(
            nodes._invoke_builder("prompt", options=None, cwd=str(tmp_path))
        )
        assert path == str(tmp_path / "out.py")
        # builder cost is keyed by the worktree dir name (slug)
        cost, toks = sum_agent_costs(tmp_path.name)
        assert abs(cost - 0.07) < 1e-9
        assert toks == {"input": 500, "output": 300}


# ---------------------------------------------------------------------------
# eval_node cost aggregation
# ---------------------------------------------------------------------------

class TestEvalCostAggregation:
    def test_eval_records_summed_real_cost(self, tmp_path, monkeypatch):
        store = tmp_path / "obs.jsonl"
        monkeypatch.setenv("SDD_OBS_STORE", str(store))
        # Simulate specialists + builder having run for task 'feat-1'
        record_agent_call("feat-1", "security", 0.02, {"input": 100, "output": 10})
        record_agent_call("feat-1", "validator", 0.01, {"input": 50, "output": 5})

        monkeypatch.setattr(
            nodes,
            "_eval_suite_evaluate",
            lambda state_or_artifact, findings: {
                "eval_score": 0.8,
                "regressed": False,
                "security_findings": [],
            },
        )
        state = {"task_id": "feat-1", "attempt": 0, "verify_findings": []}
        nodes.eval_node(state)

        eval_rows = [
            r for r in read_observations(store) if r.get("record_type") != "agent_call"
        ]
        assert eval_rows, "eval_node must write a run record"
        latest = eval_rows[-1]
        assert abs(latest["total_cost_usd"] - 0.03) < 1e-9
        assert latest["tokens"] == {"input": 150, "output": 15}

    def test_stub_mode_zero_cost(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SDD_OBS_STORE", str(tmp_path / "obs.jsonl"))
        monkeypatch.setattr(
            nodes,
            "_eval_suite_evaluate",
            lambda state_or_artifact, findings: {
                "eval_score": 0.6,
                "regressed": False,
                "security_findings": [],
            },
        )
        nodes.eval_node({"task_id": "feat-2", "attempt": 0, "verify_findings": []})
        rows = [
            r for r in read_observations(tmp_path / "obs.jsonl")
            if r.get("record_type") != "agent_call"
        ]
        assert rows[-1]["total_cost_usd"] == 0.0
        assert rows[-1]["tokens"] == {"input": 0, "output": 0}
