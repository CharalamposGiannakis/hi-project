import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from rdflib import Graph, Namespace, URIRef
from rdflib.namespace import RDF, RDFS

from hi_scenario.api import app
from hi_scenario.model import Scenario
from hi_scenario.rdf import HI, ONTOLOGY_DIR, to_ntriples, to_rdf
from hi_scenario.validation import validate_rdf


ROOT = Path(__file__).resolve().parent.parent
CONTEXT = URIRef("urn:hi-app:scenario:s1:context")
TEAM = URIRef("urn:hi-app:scenario:s1:team")


@pytest.fixture
def payload():
    data = json.loads((ROOT / "examples" / "s1.json").read_text(encoding="utf-8"))
    data.pop("capabilities", None)  # Isolate the Context projection and legacy contract.
    data.pop("executions", None)
    data.pop("experiments", None)
    data.pop("evaluations", None)
    return data


def test_complete_s1_context_is_exactly_the_original_eleven_triples(payload):
    graph = to_rdf(Scenario.model_validate(payload))
    source = Graph().parse(ONTOLOGY_DIR / "scenarios_kgs.ttl", format="turtle")
    s1 = Namespace("https://w3id.org/hi-ontology/scenarios/1/")
    identities = {s1.ContextHealthMonitoring: CONTEXT, s1.HITeamPersonalAssistant: TEAM}
    expected = {
        (identities.get(s, s), p, identities.get(o, o))
        for s, p, o in source
        if s == s1.ContextHealthMonitoring or o == s1.ContextHealthMonitoring
    }
    del payload["context"]
    legacy = to_rdf(Scenario.model_validate(payload))
    assert len(expected) == 11
    assert set(graph) - set(legacy) == expected
    assert set(legacy) <= set(graph)
    assert len(graph) == 43 and len(legacy) == 32
    assert next(graph.objects(CONTEXT, RDFS.comment)).language == "en"
    assert (TEAM, RDF.type, HI.Agent) not in graph
    conforms, _, report = validate_rdf(graph)
    assert conforms, report
    assert set(Graph().parse(data=to_ntriples(graph), format="nt")) == set(graph)


def test_optional_context_and_fields_preserve_legacy_rdf(payload):
    payload.pop("context")
    legacy = to_rdf(Scenario.model_validate(payload))
    payload["context"] = None
    assert set(to_rdf(Scenario.model_validate(payload))) == set(legacy)
    payload["context"] = {"concept": "HealthMonitoringContext"}
    scenario = Scenario.model_validate(payload)
    assert scenario.context.phenomena == scenario.context.constraints == ()
    graph = to_rdf(scenario)
    assert len(graph) == len(legacy) + 4
    assert not list(graph.objects(CONTEXT, RDFS.comment))
    assert Scenario.model_validate_json(scenario.model_dump_json()) == scenario


def test_context_identity_and_output_do_not_depend_on_concept_order(payload):
    original = to_ntriples(to_rdf(Scenario.model_validate(payload)))
    payload["context"]["phenomena"].reverse()
    payload["context"]["constraints"].reverse()
    assert to_ntriples(to_rdf(Scenario.model_validate(payload))) == original
    payload["context"]["concept"] = "OnlineLearningContext"
    assert set(to_rdf(Scenario.model_validate(payload)).subjects(RDF.type, HI.Context)) == {CONTEXT}
    payload["id"] = "other"
    assert set(to_rdf(Scenario.model_validate(payload)).subjects(RDF.type, HI.Context)) == {
        URIRef("urn:hi-app:scenario:other:context"),
    }


@pytest.mark.parametrize(("field", "value"), [
    ("concept", "MadeUpContext"), ("concept", "HumanUserRole"),
    ("phenomena", ["MadeUpPhenomenon"]), ("phenomena", ["PrivacyConstraint"]),
    ("constraints", ["MadeUpConstraint"]), ("constraints", ["SensorNoisePhenomenon"]),
])
@pytest.mark.parametrize("endpoint", ["/scenarios/preview", "/scenarios"])
def test_invalid_context_vocabulary_is_rejected_before_storage(payload, field, value, endpoint):
    payload["context"][field] = value
    with TestClient(app) as client:
        response = client.post(endpoint, json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_vocabulary"


@pytest.mark.parametrize("context", [
    {}, {"concept": "HealthMonitoringContext", "phenomena": None},
    {"concept": "HealthMonitoringContext", "constraints": "PrivacyConstraint"},
    {"concept": "HealthMonitoringContext", "description": 123},
    {"concept": "HealthMonitoringContext", "description": "  "},
    {"concept": "HealthMonitoringContext", "extra": "not supported"},
])
def test_invalid_context_structure_is_rejected(payload, context):
    payload["context"] = context
    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)


def test_context_preview_returns_original_comment(payload):
    with TestClient(app) as client:
        response = client.post("/scenarios/preview", json=payload)
    assert response.status_code == 200
    assert response.json()["triple_count"] == 43
    graph = Graph().parse(data=response.json()["rdf"], format="nt")
    comment = next(graph.objects(CONTEXT, RDFS.comment))
    assert str(comment) == payload["context"]["description"] and comment.language == "en"
