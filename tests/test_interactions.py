import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS

from hi_scenario.api import app
from hi_scenario.model import Scenario
from hi_scenario.rdf import HI, HINT, ONTOLOGY_DIR, _concept, to_ntriples, to_rdf
from hi_scenario.validation import validate_rdf


ROOT = Path(__file__).resolve().parent.parent
BASE = "urn:hi-app:scenario:s1:"
SUPPORTED = {RDF.type, RDFS.comment, HI.hasAgentInvolved, HI.hasInteractionIntentConcept, HI.hasInteractionModalityConcept, HI.hasInteractionEpisode}


@pytest.fixture
def payload():
    return json.loads((ROOT / "examples" / "s1.json").read_text(encoding="utf-8"))


def test_s1_adds_exactly_six_original_interaction_triples(payload):
    source = Graph().parse(ONTOLOGY_DIR / "scenarios_kgs.ttl", format="turtle")
    namespace = "https://w3id.org/hi-ontology/scenarios/1/"
    original = URIRef(namespace + "InteractionExplainDecision")
    identities = {
        original: URIRef(BASE + "interaction:explain-decision"),
        URIRef(namespace + "AIAssistant"): URIRef(BASE + "agent:ai-assistant"),
        URIRef(namespace + "HumanUser"): URIRef(BASE + "agent:human-user"),
        URIRef(namespace + "ExecutionExplanation"): URIRef(BASE + "execution:explanation"),
    }
    expected = {(identities.get(s, s), p, identities.get(o, o)) for s, p, o in source if s == original or o == original}
    graph = to_rdf(Scenario.model_validate(payload))
    payload.pop("interactions")
    legacy = to_rdf(Scenario.model_validate(payload))
    assert len(expected) == 6 and len(graph) == 123
    assert set(graph) - set(legacy) == expected and set(legacy) <= set(graph)
    conforms, _, report = validate_rdf(graph)
    assert conforms, report


def source_projection(payload, number):
    """Compare original interaction RDF only; other entities provide valid references."""
    source = Graph().parse(ONTOLOGY_DIR / "scenarios_kgs.ttl", format="turtle")
    namespace = f"https://w3id.org/hi-ontology/scenarios/{number}/"
    nodes = sorted(s for s in source.subjects(RDF.type, HI.Interaction) if str(s).startswith(namespace))
    agents = sorted({agent for node in nodes for agent in source.objects(node, HI.hasAgentInvolved)})
    executions = sorted({execution for node in nodes for execution in source.subjects(HI.hasInteractionEpisode, node)})
    local = lambda node: str(node).removeprefix(namespace).lower()
    payload["id"] = f"source-s{number}"
    identities = {
        node: URIRef(f"urn:hi-app:scenario:{payload['id']}:{kind}:{local(node)}")
        for kind, items in (("interaction", nodes), ("agent", agents), ("execution", executions)) for node in items
    }
    payload["agents"] = [{
        "id": local(agent), "name": local(agent),
        "kind": "human" if (agent, RDF.type, HI.HumanAgent) in source else "artificial",
        "roles": ["HumanUserRole" if (agent, RDF.type, HI.HumanAgent) in source else "AIAssistantRole"],
    } for agent in agents]
    scaffold = payload["executions"][0]
    payload["executions"] = [{**scaffold, "id": local(node), "agent": payload["agents"][0]["id"]} for node in executions]
    payload["capabilities"] = []
    payload["experiments"] = []
    payload["evaluations"] = []
    payload["interactions"] = []
    for node in nodes:
        record = {
            "id": local(node),
            "intent": str(source.value(node, HI.hasInteractionIntentConcept)).removeprefix(str(HINT)),
            "modality": str(source.value(node, HI.hasInteractionModalityConcept)).removeprefix(str(HINT)),
            "agents": sorted(local(agent) for agent in source.objects(node, HI.hasAgentInvolved)),
            "executions": sorted(local(execution) for execution in source.subjects(HI.hasInteractionEpisode, node)),
        }
        description = source.value(node, RDFS.comment)
        if description is not None:
            assert description.language == "en"
            record["description"] = str(description)
        payload["interactions"].append(record)
    related = {(s, p, o) for s, p, o in source if s in nodes or (p == HI.hasInteractionEpisode and o in nodes)}
    expected = {(identities.get(s, s), p, identities.get(o, o)) for s, p, o in related if p in SUPPORTED}
    omitted = {(s, p, o) for s, p, o in related if p not in SUPPORTED}
    return payload, expected, omitted


@pytest.mark.parametrize("number", [2, 3, 4, 5, 6])
def test_source_patterns_reproduce_supported_interaction_projection(payload, number):
    data, expected, omitted = source_projection(payload, number)
    scenario = Scenario.model_validate(data)
    graph = to_rdf(scenario)
    legacy = scenario.model_copy(update={"interactions": ()})
    assert set(graph) - set(to_rdf(legacy)) == expected
    assert {p for _, p, _ in omitted} == ({HI.towardsGoal} if number == 2 else {HI.hasInteractionConcept} if number == 5 else set())
    if number in (2, 3):
        assert not list(graph.triples((None, HI.hasInteractionEpisode, None)))
    if number == 3:
        assert len(scenario.interactions) == 2 and all(len(i.agents) == 3 for i in scenario.interactions)
    if number == 5:
        assert len(scenario.interactions[0].executions) == 2
        assert Literal(scenario.interactions[0].description, lang="en") in set(graph.objects(None, RDFS.comment))
    ontology = Graph().parse(ONTOLOGY_DIR / "hi-ontology.ttl", format="turtle")
    assert (HI.towardsGoal, RDFS.domain, HI.TaskExecution) in ontology
    assert not list(ontology.triples((HI.hasInteractionConcept, None, None)))
    assert not list(graph.triples((None, HI.hasInteractionConcept, None)))
    assert all(not list(graph.objects(s, HI.towardsGoal)) for s in graph.subjects(RDF.type, HI.Interaction))


@pytest.mark.parametrize("index", [0, 1])
def test_s7_scenario_local_intents_are_rejected_without_substitution(payload, index):
    data, _, _ = source_projection(payload, 7)
    data["interactions"] = [data["interactions"][index]]
    intent = data["interactions"][0]["intent"]
    assert intent.startswith("https://w3id.org/hi-ontology/scenarios/7/Intent")
    with pytest.raises(ValidationError):
        Scenario.model_validate(data)
    with pytest.raises(ValueError, match="Unknown HINT concept"):
        _concept(intent.rsplit("/", 1)[-1], "InteractionIntent")


def test_many_to_many_links_identity_and_no_inferred_participants(payload):
    payload["agents"].append({**payload["agents"][0], "id": "second-human"})
    payload["interactions"][0]["agents"] = ["human-user", "second-human"]
    payload["interactions"][0]["executions"] = ["explanation", "conflict-resolution"]  # Both performed by AI.
    payload["interactions"].append({**payload["interactions"][0], "id": "another", "description": "Another interaction."})
    scenario = Scenario.model_validate(payload)
    assert Scenario.model_validate_json(scenario.model_dump_json()) == scenario
    graph = to_rdf(scenario)
    nodes = set(graph.subjects(RDF.type, HI.Interaction))
    assert nodes == {URIRef(BASE + "interaction:" + id) for id in ("explain-decision", "another")}
    for node in nodes:
        assert set(graph.objects(node, HI.hasAgentInvolved)) == {URIRef(BASE + "agent:" + id) for id in ("human-user", "second-human")}
        assert set(graph.subjects(HI.hasInteractionEpisode, node)) == {URIRef(BASE + "execution:" + id) for id in ("explanation", "conflict-resolution")}
    payload["interactions"].reverse()
    for interaction in payload["interactions"]:
        interaction["agents"].reverse()
        interaction["executions"].reverse()
    assert to_ntriples(to_rdf(Scenario.model_validate(payload))) == to_ntriples(graph)
    assert set(Graph().parse(data=to_ntriples(graph), format="nt")) == set(graph)
    payload["interactions"][0]["intent"] = "NegotiationIntent"
    assert set(to_rdf(Scenario.model_validate(payload)).subjects(RDF.type, HI.Interaction)) == nodes


def test_optional_collection_execution_links_and_descriptions(payload):
    payload.pop("interactions")
    legacy = to_rdf(Scenario.model_validate(payload))
    payload["interactions"] = []
    assert len(legacy) == 117 and set(to_rdf(Scenario.model_validate(payload))) == set(legacy)
    payload["interactions"] = [{"id": "unlinked", "intent": "ExplanationIntent", "modality": "TextChatModality", "agents": ["human-user", "ai-assistant"], "description": None}]
    graph = to_rdf(Scenario.model_validate(payload))
    assert len(graph) == 122 and not list(graph.triples((None, HI.hasInteractionEpisode, None)))
    payload["interactions"][0]["description"] = 'An English "description".\nSecond line.'
    assert (URIRef(BASE + "interaction:unlinked"), RDFS.comment, Literal(payload["interactions"][0]["description"], lang="en")) in to_rdf(Scenario.model_validate(payload))


@pytest.mark.parametrize(("field", "value", "code"), [
    ("intent", "MadeUpIntent", "invalid_vocabulary"), ("intent", "VerbalDialogueModality", "invalid_vocabulary"),
    ("modality", "MadeUpModality", "invalid_vocabulary"), ("modality", "ExplanationIntent", "invalid_vocabulary"),
    ("agents", [], "invalid_request"), ("agents", ["human-user"], "invalid_request"),
    ("agents", ["human-user", "human-user"], "invalid_request"),
    ("agents", ["human-user", "ai-assistant", "human-user"], "invalid_request"),
    ("agents", ["human-user", "missing"], "invalid_request"), ("agents", ["human-user", "data-collection"], "invalid_request"),
    ("executions", ["missing"], "invalid_request"), ("executions", ["ai-assistant"], "invalid_request"),
    ("executions", ["explanation", "explanation"], "invalid_request"),
    ("description", "  ", "invalid_request"), ("description", 123, "invalid_request"),
])
@pytest.mark.parametrize("endpoint", ["/scenarios/preview", "/scenarios"])
def test_invalid_interactions_return_422_before_storage(payload, field, value, code, endpoint):
    payload["interactions"][0][field] = value
    with TestClient(app) as client:
        response = client.post(endpoint, json=payload)
    assert response.status_code == 422 and response.json()["code"] == code


@pytest.mark.parametrize("interactions", [None, {}, [{}]])
def test_invalid_collection_structure(payload, interactions):
    payload["interactions"] = interactions
    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)


def test_duplicate_ids_and_deletion_preserve_data_until_repaired(payload):
    duplicate = deepcopy(payload)
    duplicate["interactions"].append(dict(duplicate["interactions"][0]))
    with pytest.raises(ValidationError, match="Duplicate interaction IDs"):
        Scenario.model_validate(duplicate)
    original = deepcopy(payload["interactions"])
    invalid = deepcopy(payload)
    invalid["executions"] = []
    invalid["evaluations"] = []
    with pytest.raises(ValidationError, match="unknown execution IDs"):
        Scenario.model_validate(invalid)
    assert invalid["interactions"] == original
