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


ROOT = Path(__file__).resolve().parent.parent
BASE = "urn:hi-app:scenario:s1:"
EXECUTION_PREDICATES = {
    RDF.type, HI.hasExecutionConcept, HI.hasMethodConcept, HI.realizesTask,
    HI.performedBy, HI.performsExecution, HI.towardsGoal,
}


@pytest.fixture
def payload():
    data = json.loads((ROOT / "examples" / "s1.json").read_text(encoding="utf-8"))
    data.pop("experiments", None)
    data.pop("evaluations", None)
    data.pop("interactions", None)
    return data


def test_s1_reproduces_all_twenty_one_supported_execution_triples(payload):
    graph = to_rdf(Scenario.model_validate(payload))
    source = Graph().parse(ONTOLOGY_DIR / "scenarios_kgs.ttl", format="turtle")
    s1 = Namespace("https://w3id.org/hi-ontology/scenarios/1/")
    identities = {
        s1.ExecutionDataCollection: URIRef(BASE + "execution:data-collection"),
        s1.ExecutionConflictResolution: URIRef(BASE + "execution:conflict-resolution"),
        s1.ExecutionExplanation: URIRef(BASE + "execution:explanation"),
        s1.HumanUser: URIRef(BASE + "agent:human-user"),
        s1.AIAssistant: URIRef(BASE + "agent:ai-assistant"),
        s1.TaskDataCollection: URIRef(BASE + "task:data-collection"),
        s1.TaskConflictResolution: URIRef(BASE + "task:conflict-resolution"),
        s1.TaskExplanation: URIRef(BASE + "task:explanation"),
        s1.GoalUserWellbeing: URIRef(BASE + "goal:user-wellbeing"),
    }
    executions = set(source.subjects(RDF.type, HI.TaskExecution)) & identities.keys()
    expected = {
        (identities.get(s, s), p, identities.get(o, o))
        for s, p, o in source
        if p in EXECUTION_PREDICATES and (s in executions or o in executions)
    }
    payload.pop("executions")
    legacy = to_rdf(Scenario.model_validate(payload))
    assert len(expected) == 21
    assert set(graph) - set(legacy) == expected
    assert set(legacy) <= set(graph) and len(graph) == 84
    for predicate in (HI.evaluatedBy, HI.hasInteractionEpisode, HI.isEligibleForTask, HI.executesTask, HI.isAssignedToTask):
        assert not list(graph.triples((None, predicate, None)))
    conforms, _, report = validate_rdf(graph)
    assert conforms, report


def test_s3_distinct_juror_executions_realize_the_same_task(payload):
    source = Graph().parse(ONTOLOGY_DIR / "scenarios_kgs.ttl", format="turtle")
    s3 = Namespace("https://w3id.org/hi-ontology/scenarios/3/")
    payload.update({
        "id": "s3",
        "use_case": {"id": "deliberation", "name": "Group deliberation", "concept": "GroupDeliberationUseCase"},
        "goal": {"id": "verdict", "name": "Fair accurate verdict", "concept": "FairAccurateVerdictGoal"},
        "tasks": [{"id": "statement", "name": "Provide statement", "concept": "ProvideStatementTask"}],
        "agents": [
            {"id": "juror-1", "name": "Juror", "kind": "human", "roles": ["JurorRole"]},
            {"id": "juror-2", "name": "Juror", "kind": "human", "roles": ["JurorRole"]},
            {"id": "ai", "name": "AI advisor", "kind": "artificial", "roles": ["AIAdvisorRole"]},
        ],
        "context": None, "capabilities": [], "executions": [],
    })
    identities = {
        s3.TaskProvideStatement: URIRef("urn:hi-app:scenario:s3:task:statement"),
        s3.GoalFairAccurateVerdict: URIRef("urn:hi-app:scenario:s3:goal:verdict"),
    }
    for number in (1, 2):
        node = s3[f"ExecProvideStatement{number}"]
        agent = source.value(node, HI.performedBy)
        assert source.value(node, HI.realizesTask) == s3.TaskProvideStatement
        assert source.value(node, HI.hasMethodConcept) is None
        payload["executions"].append({
            "id": f"statement-{number}",
            "concept": str(source.value(node, HI.hasExecutionConcept)).removeprefix(str(HINT)),
            "task": "statement", "agent": f"juror-{number}",
        })
        identities[node] = URIRef(f"urn:hi-app:scenario:s3:execution:statement-{number}")
        identities[agent] = URIRef(f"urn:hi-app:scenario:s3:agent:juror-{number}")
    graph = to_rdf(Scenario.model_validate(payload))
    expected = {
        (identities[s], p, identities.get(o, o))
        for s, p, o in source if s in identities and p in EXECUTION_PREDICATES
        and (s in (s3.ExecProvideStatement1, s3.ExecProvideStatement2) or p == HI.performsExecution)
    }
    payload["executions"] = []
    assert len(expected) == 12
    assert set(graph) - set(to_rdf(Scenario.model_validate(payload))) == expected
    assert len(set(graph.subjects(HI.realizesTask, identities[s3.TaskProvideStatement]))) == 2


def test_optional_methods_legacy_json_and_explicit_performance_without_capabilities(payload):
    payload.pop("executions")
    legacy = to_rdf(Scenario.model_validate(payload))
    payload["executions"] = []
    assert len(legacy) == 63
    assert to_ntriples(to_rdf(Scenario.model_validate(payload))) == to_ntriples(legacy)
    payload["capabilities"] = []
    payload["executions"] = [{
        "id": "explicit", "concept": "DataCollectionTaskExecution", "task": "data-collection", "agent": "ai-assistant",
    }]
    graph = to_rdf(Scenario.model_validate(payload))
    assert len(graph) == 49
    assert not list(graph.triples((None, HI.hasMethodConcept, None)))
    payload["executions"][0]["method"] = None
    assert set(to_rdf(Scenario.model_validate(payload))) == set(graph)
    assert not list(graph.triples((None, HI.isEligibleForTask, None)))


def test_repeated_executions_keep_stable_identities_and_deterministic_rdf(payload):
    payload["executions"].append({**payload["executions"][0], "id": "repeat"})
    scenario = Scenario.model_validate(payload)
    assert Scenario.model_validate_json(scenario.model_dump_json()) == scenario
    original = to_rdf(scenario)
    assert len(set(original.subjects(HI.realizesTask, URIRef(BASE + "task:data-collection")))) == 2
    payload["executions"].reverse()
    assert to_ntriples(to_rdf(Scenario.model_validate(payload))) == to_ntriples(original)
    assert set(Graph().parse(data=to_ntriples(original), format="nt")) == set(original)
    payload["executions"][0]["concept"] = "ExplanationTaskExecution"
    payload["goal"]["id"] = "new-goal"
    changed = to_rdf(Scenario.model_validate(payload))
    assert set(changed.subjects(RDF.type, HI.TaskExecution)) == set(original.subjects(RDF.type, HI.TaskExecution))
    assert set(changed.objects(None, HI.towardsGoal)) == {URIRef(BASE + "goal:new-goal")}
    payload["id"] = "other"
    assert set(to_rdf(Scenario.model_validate(payload)).subjects()).isdisjoint(original.subjects())


@pytest.mark.parametrize(("field", "value", "message"), [
    ("agent", "missing", "unknown agent ID"), ("agent", "data-collection", "unknown agent ID"),
    ("task", "missing", "unknown task ID"), ("task", "human-user", "unknown task ID"),
    ("id", "explanation", "Duplicate execution IDs"),
])
@pytest.mark.parametrize("endpoint", ["/scenarios/preview", "/scenarios"])
def test_invalid_execution_references_and_ids_return_422(payload, field, value, message, endpoint):
    payload["executions"][0][field] = value
    with TestClient(app) as client:
        response = client.post(endpoint, json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert message in response.json()["issues"][0]["message"]


@pytest.mark.parametrize(("field", "concept"), [
    ("concept", "MadeUpExecution"), ("concept", "DataCollectionTask"),
    ("method", "MadeUpMethod"), ("method", "DataCollectionTaskExecution"),
])
@pytest.mark.parametrize("endpoint", ["/scenarios/preview", "/scenarios"])
def test_invalid_execution_vocabulary_returns_422(payload, field, concept, endpoint):
    payload["executions"][0][field] = concept
    with TestClient(app) as client:
        response = client.post(endpoint, json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_vocabulary"


@pytest.mark.parametrize("execution", [
    {}, {"id": "bad:id"}, {"agent": ["human-user"]}, {"task": None},
    {"method": ""}, {"method": 123}, {"goal": "user-wellbeing"}, {"evaluation": "unsupported"},
])
def test_invalid_execution_structure_is_rejected(payload, execution):
    payload["executions"] = [{**payload["executions"][0], **execution}] if execution else [{}]
    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)
