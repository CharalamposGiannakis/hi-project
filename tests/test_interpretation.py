import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from hi_scenario import api, nebula
from hi_scenario.interpretation import assemble_interpretation
from hi_scenario.model import Scenario
from hi_scenario.rdf import to_rdf


def scenario_example(index=1):
    path = Path(__file__).resolve().parents[1] / "examples" / f"s{index}.json"
    scenario = json.loads(path.read_text(encoding="utf-8"))
    # Canonical legacy examples encode this relation by omission. Model proposals are explicit.
    scenario["goal"].setdefault("required_tasks", [task["id"] for task in scenario["tasks"]])
    return scenario


def proposal(candidate, diagnostics=None):
    return assemble_interpretation({"scenario": candidate, "diagnostics": diagnostics or []}, "test-model", "test-version")


@pytest.mark.parametrize("index", range(1, 8))
def test_keeps_all_approved_example_facts_and_references(index):
    example = scenario_example(index)
    result = proposal(example)
    assert result.interpretation.model_dump() == {
        "status": "complete", "model": "test-model", "prompt_version": "test-version", "diagnostics": [],
    }
    assert result.scenario["id"] != example["id"]
    assert {**result.scenario, "id": example["id"]} == example
    assert len(to_rdf(Scenario.model_validate(result.scenario))) == len(to_rdf(Scenario.model_validate(example)))


def test_preserves_partial_facts_without_guessing_kind_team_or_required_task_link():
    example = scenario_example()
    example["agents"] = [{"name": "Operator", "roles": ["HumanUserRole"]}]
    del example["goal"]["required_tasks"]
    result = proposal(example)
    assert result.interpretation.status == "incomplete"
    assert result.scenario["tasks"] == example["tasks"]
    assert result.scenario["agents"][0]["name"] == "Operator"
    assert result.scenario["agents"][0]["kind"] == ""
    assert len(result.scenario["agents"]) == 1
    assert result.scenario["goal"]["required_tasks"] == []
    findings = {(item.kind, item.path) for item in result.interpretation.diagnostics}
    assert ("missing_information", "agents.0.kind") in findings
    assert ("missing_information", "goal.required_tasks") in findings
    assert ("technical_validation", "agents") in findings
    with pytest.raises(ValidationError):
        Scenario.model_validate(result.scenario)


def test_reports_unsupported_terms_and_relationships_without_promoting_them():
    example = scenario_example()
    example["agents"][0]["roles"] += ["MoodSteward", example["tasks"][0]["concept"]]
    example["agents"][0]["assigned_task"] = example["tasks"][0]["id"]
    relationship = {"kind": "unsupported_relationship", "message": "Formal assignment is distinct from actual execution."}
    result = proposal(example, [relationship])
    assert result.interpretation.status == "incomplete"
    assert result.scenario["agents"][0]["roles"] == ["HumanUserRole"]
    assert "assigned_task" not in result.scenario["agents"][0]
    assert result.scenario["executions"] == example["executions"]
    assert result.interpretation.diagnostics[0].model_dump() == relationship
    suggestions = [note for note in result.interpretation.diagnostics if note.kind == "unsupported_vocabulary"]
    assert [note.path for note in suggestions] == ["agents.0.roles.1", "agents.0.roles.2"]
    assert "MoodSteward" in suggestions[0].message
    Scenario.model_validate(result.scenario)


def test_recovers_known_records_and_never_guesses_an_ambiguous_reference():
    example = scenario_example()
    task = example["tasks"][0]
    example["tasks"] = [
        {**task, "id": "invalid id"}, None,
        {**task, "id": "ambiguous", "name": "First task"},
        {**task, "id": "ambiguous", "name": "Second task"},
    ]
    example["goal"]["required_tasks"] = ["invalid id", "ambiguous"]
    result = proposal(example)
    tasks = result.scenario["tasks"]
    assert len({task["id"] for task in tasks}) == 3
    assert [task["name"] for task in tasks] == [task["name"], "First task", "Second task"]
    assert result.scenario["goal"]["required_tasks"] == [tasks[0]["id"], "ambiguous"]
    assert any(note.kind == "structural" for note in result.interpretation.diagnostics)
    assert any(note.kind == "technical_validation" and note.path == "goal.required_tasks" and "ambiguous" in note.message
               for note in result.interpretation.diagnostics)


def test_null_and_bare_candidates_are_recoverable():
    null_result = proposal(None)
    assert null_result.scenario is None
    assert null_result.interpretation.status == "incomplete"
    assert null_result.interpretation.diagnostics[0].kind == "missing_information"
    bare_result = assemble_interpretation(scenario_example(), "test-model", "1")
    assert bare_result.scenario["agents"] == scenario_example()["agents"]
    assert bare_result.interpretation.status == "incomplete"
    assert any(note.kind == "structural" for note in bare_result.interpretation.diagnostics)


def test_drops_empty_placeholder_records_but_keeps_a_named_member():
    result = proposal({
        "agents": [{"id": "unspecified"}, {"name": "Known member"}],
        "context": {"concept": None, "constraints": []},
        "executions": [{"id": "unused", "concept": "", "method": None}],
    })
    assert [(agent["name"], agent["kind"]) for agent in result.scenario["agents"]] == [("Known member", "")]
    assert "context" not in result.scenario
    assert result.scenario["executions"] == []


@pytest.mark.parametrize("description", [{}, {"goal": "  "}, {"made_up": "Something"}, {"goal": 4},
                                         {"goal": "a" * 10_001, "tasks": "b" * 10_000}])
def test_invalid_description_never_reaches_provider(description, monkeypatch):
    def unexpected(_answers):
        pytest.fail("Invalid researcher input reached Nebula")

    monkeypatch.setattr(nebula, "request_interpretation", unexpected)
    with TestClient(api.app) as client:
        response = client.post("/scenarios/interpret", json={"description": description})
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert "description" in response.json()["message"]


def test_api_keeps_interpretation_separate_from_explicit_rdf_validation(monkeypatch):
    answers = {"use_case": "  A human and a machine work together.\n", "additional_notes": "No further details."}
    example = scenario_example()

    def generate(description):
        assert description == answers
        return "test-model", {"scenario": example, "diagnostics": []}

    def unexpected(_scenario):
        pytest.fail("Interpretation must not generate RDF")

    monkeypatch.setattr(nebula, "request_interpretation", generate)
    with TestClient(api.app) as client:
        with monkeypatch.context() as patch:
            patch.setattr(api, "_validated_graph", unexpected)
            response = client.post("/scenarios/interpret", json={"description": answers})
        assert response.status_code == 200
        result = response.json()
        assert result["interpretation"]["prompt_version"] == nebula.PROMPT_VERSION
        assert result["interpretation"]["model"] == "test-model"
        assert client.post("/scenarios/preview", json=result["scenario"]).status_code == 200
        assert client.post("/scenarios/preview", json=result).status_code == 422


@pytest.mark.parametrize("status_code,code", [(502, "interpretation_failed"), (503, "interpretation_unavailable"),
                                             (504, "interpretation_failed")])
def test_provider_failure_uses_existing_safe_error_shape(status_code, code, monkeypatch):
    def unavailable(_description):
        raise nebula.NebulaError(status_code, "Safe provider message")

    monkeypatch.setattr(nebula, "request_interpretation", unavailable)
    with TestClient(api.app) as client:
        response = client.post("/scenarios/interpret", json={"description": {"goal": "Example"}})
    assert response.status_code == status_code
    assert response.json() == {"code": code, "message": "Safe provider message", "issues": [], "shacl_report": None}
