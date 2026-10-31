import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from rdflib import URIRef
from rdflib.namespace import RDF

from hi_scenario import api
from hi_scenario.model import Scenario
from hi_scenario.rdf import HI, HINT, to_rdf
from hi_scenario.validation import validate_rdf


ROOT = Path(__file__).resolve().parent.parent
TEAM = URIRef("urn:hi-app:scenario:s1:team")
CONTEXT = URIRef("urn:hi-app:scenario:s1:context")


@pytest.fixture
def payload():
    return json.loads((ROOT / "examples" / "s1.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("index, count", [(1, 127), (2, 195), (3, 135), (4, 154), (5, 139), (6, 150)])
def test_omitted_and_empty_team_constraints_preserve_legacy_graphs(index, count):
    data = json.loads((ROOT / "examples" / f"s{index}.json").read_text(encoding="utf-8"))
    scenario = Scenario.model_validate(data)
    assert scenario.team_constraints == ()
    original = to_rdf(scenario)
    assert len(original) == count
    assert not list(original.objects(URIRef(f"urn:hi-app:scenario:s{index}:team"), HI.hasConstraintConcept))
    data["team_constraints"] = []
    assert set(to_rdf(Scenario.model_validate(data))) == set(original)


@pytest.mark.parametrize("with_context", [False, True])
def test_selected_team_constraints_add_only_team_triples_and_round_trip(payload, with_context):
    if not with_context:
        del payload["context"]
    original = to_rdf(Scenario.model_validate(payload))
    payload["team_constraints"] = ["PrivacyConstraint", "AccessibilityConstraint"]
    scenario = Scenario.model_validate(payload)
    assert Scenario.model_validate_json(scenario.model_dump_json()) == scenario
    graph = to_rdf(scenario)
    assert set(graph) - set(original) == {
        (TEAM, HI.hasConstraintConcept, HINT.PrivacyConstraint),
        (TEAM, HI.hasConstraintConcept, HINT.AccessibilityConstraint),
    }
    assert set(original) <= set(graph)
    assert set(graph.objects(CONTEXT, HI.hasConstraintConcept)) == set(original.objects(CONTEXT, HI.hasConstraintConcept))
    assert set(graph.subjects(RDF.type, HI.HITeam)) == {TEAM}
    conforms, _, report = validate_rdf(graph)
    assert conforms, report


def test_changing_or_removing_context_does_not_change_team_constraints(payload):
    payload["team_constraints"] = ["PrivacyConstraint"]
    payload["context"]["constraints"] = ["TransparencyConstraint"]
    for context_constraints in (["TransparencyConstraint"], ["AccessibilityConstraint"]):
        payload["context"]["constraints"] = context_constraints
        graph = to_rdf(Scenario.model_validate(payload))
        assert set(graph.objects(TEAM, HI.hasConstraintConcept)) == {HINT.PrivacyConstraint}
        assert set(graph.objects(CONTEXT, HI.hasConstraintConcept)) == {HINT[name] for name in context_constraints}
    payload["team_constraints"] = ["FairnessConstraint"]
    graph = to_rdf(Scenario.model_validate(payload))
    assert set(graph.objects(CONTEXT, HI.hasConstraintConcept)) == {HINT.AccessibilityConstraint}
    del payload["context"]
    graph = to_rdf(Scenario.model_validate(payload))
    assert set(graph.objects(TEAM, HI.hasConstraintConcept)) == {HINT.FairnessConstraint}
    assert not list(graph.subjects(RDF.type, HI.Context))


@pytest.mark.parametrize("concept", ["MadeUpConstraint", "SensorNoisePhenomenon", "HumanUserRole"])
@pytest.mark.parametrize("endpoint", ["/scenarios/preview", "/scenarios"])
def test_invalid_team_vocabulary_is_rejected_before_storage(payload, concept, endpoint, monkeypatch):
    def unexpected_connection():
        pytest.fail("Invalid vocabulary must be rejected before connecting to GraphDB")

    monkeypatch.setattr(api, "connect_graphdb", unexpected_connection)
    payload["team_constraints"] = [concept]
    with TestClient(api.app) as client:
        response = client.post(endpoint, json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_vocabulary"


@pytest.mark.parametrize("value", [None, "PrivacyConstraint", 123, [123], [""], ["hint:PrivacyConstraint"]])
def test_invalid_team_constraint_structure_is_rejected(payload, value):
    payload["team_constraints"] = value
    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)
