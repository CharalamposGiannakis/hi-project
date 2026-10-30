import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, RDFS

from hi_scenario.api import app
from hi_scenario.model import Scenario
from hi_scenario.rdf import HI, HINT, ONTOLOGY_DIR, to_ntriples, to_rdf
from hi_scenario.validation import validate_rdf


ROOT = Path(__file__).resolve().parent.parent
BASE = "urn:hi-app:scenario:s1:"


@pytest.fixture
def payload():
    data = json.loads((ROOT / "examples" / "s1.json").read_text(encoding="utf-8"))
    data.pop("executions", None)  # Isolate capabilities from execution assignments.
    return data


def test_s1_capabilities_reproduce_all_twenty_original_triples(payload):
    graph = to_rdf(Scenario.model_validate(payload))
    source = Graph().parse(ONTOLOGY_DIR / "scenarios_kgs.ttl", format="turtle")
    s1 = Namespace("https://w3id.org/hi-ontology/scenarios/1/")
    identities = {
        s1.CapabilitySensing: URIRef(BASE + "capability:sensing"),
        s1.CapabilitySelfReporting: URIRef(BASE + "capability:self-reporting"),
        s1.CapabilityReasoning: URIRef(BASE + "capability:reasoning"),
        s1.CapabilityExplanation: URIRef(BASE + "capability:explaining"),
        s1.AIAssistant: URIRef(BASE + "agent:ai-assistant"),
        s1.HumanUser: URIRef(BASE + "agent:human-user"),
        s1.TaskDataCollection: URIRef(BASE + "task:data-collection"),
        s1.TaskConflictResolution: URIRef(BASE + "task:conflict-resolution"),
        s1.TaskExplanation: URIRef(BASE + "task:explanation"),
    }
    capabilities = set(source.subjects(RDF.type, HI.Capability)) & identities.keys()
    expected = {
        (identities.get(s, s), p, identities.get(o, o))
        for s, p, o in source if s in capabilities or o in capabilities
    }
    payload.pop("capabilities")
    legacy = to_rdf(Scenario.model_validate(payload))
    assert len(expected) == 20
    assert set(graph) - set(legacy) == expected
    assert set(legacy) <= set(graph) and len(graph) == 63
    assert not list(graph.triples((None, HI.isEligibleForTask, None)))
    assert not list(graph.triples((None, HI.performsExecution, None)))
    conforms, _, report = validate_rdf(graph)
    assert conforms, report


def test_shared_capability_has_one_identity_and_both_task_directions(payload):
    payload["capabilities"] = [{
        "id": "shared", "concept": "ReasoningCapability",
        "agents": [a["id"] for a in payload["agents"]],
        "tasks": [t["id"] for t in payload["tasks"][:2]],
    }]
    graph = to_rdf(Scenario.model_validate(payload))
    capability = URIRef(BASE + "capability:shared")
    assert set(graph.subjects(RDF.type, HI.Capability)) == {capability}
    assert set(graph.subjects(HI.hasCapability, capability)) == {
        URIRef(BASE + "agent:" + a["id"]) for a in payload["agents"]
    }
    tasks = {URIRef(BASE + "task:" + t["id"]) for t in payload["tasks"][:2]}
    assert set(graph.objects(capability, HI.allowsTask)) == tasks
    assert set(graph.subjects(HI.requiresCapability, capability)) == tasks
    assert not list(graph.objects(capability, RDFS.label))
    assert len(graph) == 51


def test_capability_identity_round_trip_and_deterministic_rdf(payload):
    payload["capabilities"].append({
        "id": "other-sensing", "concept": "SensingCapability",
        "agents": [a["id"] for a in payload["agents"]],
        "tasks": [t["id"] for t in payload["tasks"]],
    })
    scenario = Scenario.model_validate(payload)
    assert Scenario.model_validate_json(scenario.model_dump_json()) == scenario
    original = to_rdf(scenario)
    assert len(set(original.subjects(HI.hasCapabilityConcept, HINT.SensingCapability))) == 2
    payload["capabilities"].reverse()
    for capability in payload["capabilities"]:
        capability["agents"].reverse()
        capability["tasks"].reverse()
    assert to_ntriples(to_rdf(Scenario.model_validate(payload))) == to_ntriples(original)
    assert set(Graph().parse(data=to_ntriples(original), format="nt")) == set(original)
    payload["capabilities"][0]["concept"] = "ReasoningCapability"
    changed = to_rdf(Scenario.model_validate(payload))
    assert set(changed.subjects(RDF.type, HI.Capability)) == set(original.subjects(RDF.type, HI.Capability))
    payload["id"] = "another"
    assert set(to_rdf(Scenario.model_validate(payload)).subjects()).isdisjoint(original.subjects())


def test_capabilities_are_optional_and_can_be_unassigned(payload):
    payload.pop("capabilities")
    legacy = Scenario.model_validate(payload)
    assert legacy.capabilities == () and len(to_rdf(legacy)) == 43
    payload["capabilities"] = []
    assert to_ntriples(to_rdf(Scenario.model_validate(payload))) == to_ntriples(to_rdf(legacy))
    payload["capabilities"] = [{"id": "unassigned", "concept": "SensingCapability"}]
    graph = to_rdf(Scenario.model_validate(payload))
    assert len(graph) == 45
    assert not list(graph.triples((None, HI.hasCapability, None)))
    assert not list(graph.triples((None, HI.allowsTask, None)))


@pytest.mark.parametrize(("field", "value", "message"), [
    ("agents", ["missing"], "unknown agent IDs"),
    ("agents", ["data-collection"], "unknown agent IDs"),
    ("tasks", ["missing"], "unknown task IDs"),
    ("tasks", ["ai-assistant"], "unknown task IDs"),
    ("id", "self-reporting", "Duplicate capability IDs"),
])
@pytest.mark.parametrize("endpoint", ["/scenarios/preview", "/scenarios"])
def test_invalid_capability_references_and_ids_return_422(payload, field, value, message, endpoint):
    payload["capabilities"][0][field] = value
    with TestClient(app) as client:
        response = client.post(endpoint, json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert message in response.json()["issues"][0]["message"]


@pytest.mark.parametrize("concept", ["MadeUpCapability", "DataCollectionTask"])
@pytest.mark.parametrize("endpoint", ["/scenarios/preview", "/scenarios"])
def test_invalid_capability_vocabulary_is_rejected_before_storage(payload, concept, endpoint):
    payload["capabilities"][0]["concept"] = concept
    with TestClient(app) as client:
        response = client.post(endpoint, json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_vocabulary"


@pytest.mark.parametrize("capabilities", [
    None, {}, [{}], [{"id": "invalid:id", "concept": "SensingCapability"}],
    [{"id": "x", "concept": "SensingCapability", "agents": None}],
    [{"id": "x", "concept": "SensingCapability", "tasks": "data-collection"}],
    [{"id": "x", "concept": "SensingCapability", "tasks": [123]}],
    [{"id": "x", "concept": "SensingCapability", "name": "redundant"}],
])
def test_invalid_capability_structure_is_rejected(payload, capabilities):
    payload["capabilities"] = capabilities
    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)
