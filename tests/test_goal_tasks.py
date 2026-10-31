import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF

from hi_scenario.api import app
from hi_scenario.model import Scenario
from hi_scenario.rdf import HI, HINT, ONTOLOGY_DIR, to_ntriples, to_rdf
from hi_scenario.validation import validate_rdf


BASE = "urn:hi-app:scenario:s1:"
GOAL = URIRef(BASE + "goal:user-wellbeing")


@pytest.fixture
def payload():
    return json.loads((Path(__file__).resolve().parent.parent / "examples" / "s1.json").read_text(encoding="utf-8"))


def test_explicit_subset_changes_only_goal_requirements(payload):
    legacy = to_rdf(Scenario.model_validate(payload))
    payload["goal"]["required_tasks"] = ["data-collection"]
    scenario = Scenario.model_validate(payload)
    graph = to_rdf(scenario)
    assert set(graph.objects(GOAL, HI.requiresTask)) == {URIRef(BASE + "task:data-collection")}
    assert set(graph.subjects(RDF.type, HI.Task)) == {URIRef(BASE + "task:" + task.id) for task in scenario.tasks}
    assert set(graph) == set(legacy) - {
        (GOAL, HI.requiresTask, URIRef(BASE + "task:" + id))
        for id in ("conflict-resolution", "explanation")
    }
    # Executions and capabilities still reference tasks outside the selected requirements.
    assert (URIRef(BASE + "execution:explanation"), HI.realizesTask, URIRef(BASE + "task:explanation")) in graph
    assert Scenario.model_validate_json(scenario.model_dump_json()) == scenario
    assert validate_rdf(graph)[0]


def test_legacy_omission_and_explicit_all_preserve_complete_s1(payload):
    legacy = Scenario.model_validate(payload)
    assert legacy.goal.required_tasks is None
    assert "required_tasks" not in legacy.model_dump()["goal"]
    assert Scenario.model_validate_json(legacy.model_dump_json()) == legacy
    payload["goal"]["required_tasks"] = [task["id"] for task in payload["tasks"]]
    explicit = Scenario.model_validate(payload)
    assert to_ntriples(to_rdf(explicit)) == to_ntriples(to_rdf(legacy))
    assert len(to_rdf(explicit)) == 127
    payload["goal"]["required_tasks"].reverse()
    assert to_ntriples(to_rdf(Scenario.model_validate(payload))) == to_ntriples(to_rdf(legacy))


@pytest.mark.parametrize("references", [
    [], None, ["data-collection", "data-collection"], ["missing"],
    ["data-collection", "missing"], "data-collection", [123], ["task:injected"],
])
@pytest.mark.parametrize("endpoint", ["/scenarios/preview", "/scenarios"])
def test_invalid_required_tasks_are_rejected_by_model_and_api(payload, references, endpoint):
    payload["goal"]["required_tasks"] = references
    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)
    with TestClient(app) as client:
        response = client.post(endpoint, json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert response.json()["issues"]


def test_s2_task_inventory_and_exact_source_goal_requirements():
    # A focused S2 goal/task scaffold, not a complete S2 fixture.
    source = Graph().parse(ONTOLOGY_DIR / "scenarios_kgs.ttl", format="turtle")
    s2 = Namespace("https://w3id.org/hi-ontology/scenarios/2/")
    tasks = sorted(node for node in source.subjects(RDF.type, HI.Task) if str(node).startswith(str(s2)))
    identities = {node: URIRef("urn:hi-app:scenario:s2-goal-tasks:task:" + str(node).removeprefix(str(s2)).lower()) for node in tasks}
    task_id = lambda node: str(node).removeprefix(str(s2)).lower()
    required = set(source.objects(s2.GoalSafeToolRetrieval, HI.requiresTask))
    assert required == {s2.TaskUnlockCabinet, s2.TaskOpenCabinet, s2.TaskRetrieveTool}
    data = {
        "id": "s2-goal-tasks",
        "use_case": {"id": "manipulation", "name": "Collaborative manipulation", "concept": "CollaborativeManipulationUseCase"},
        "goal": {"id": "safe-retrieval", "name": "Safe retrieval", "concept": "SafeRetrievalGoal", "required_tasks": [task_id(node) for node in sorted(required)]},
        "tasks": [{"id": task_id(node), "name": task_id(node), "concept": str(source.value(node, HI.hasTaskConcept)).removeprefix(str(HINT))} for node in tasks],
        "agents": [
            {"id": "robot", "name": "RobotManipulator", "kind": "artificial", "roles": ["RiskOperatorRole"]},
            {"id": "technician", "name": "HumanTechnician", "kind": "human", "roles": ["FineManipulatorRole"]},
        ],
        "executions": [{
            "id": str(node).removeprefix(str(s2)).lower(),
            "concept": str(source.value(node, HI.hasExecutionConcept)).removeprefix(str(HINT)),
            "task": task_id(source.value(node, HI.realizesTask)), "agent": "robot",
        } for node in (s2.ExecConfinedReach, s2.ExecHeavyLift)],
    }
    graph = to_rdf(Scenario.model_validate(data))
    goal = URIRef("urn:hi-app:scenario:s2-goal-tasks:goal:safe-retrieval")
    assert len(tasks) == 10
    assert set(graph.subjects(RDF.type, HI.Task)) == set(identities.values())
    assert set(graph.triples((None, HI.requiresTask, None))) == {(goal, HI.requiresTask, identities[node]) for node in required}
    assert len(list(graph.subjects(HI.realizesTask, identities[s2.TaskHeavyLift]))) == 2
    assert (goal, HI.requiresTask, identities[s2.TaskHeavyLift]) not in graph
    assert len(list(graph.triples((None, HI.towardsGoal, goal)))) == 2
    assert validate_rdf(graph)[0]

