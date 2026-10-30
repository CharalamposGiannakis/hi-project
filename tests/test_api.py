import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDFS

from hi_scenario import api
from hi_scenario.model import Scenario
from hi_scenario.rdf import HI, HINT, to_ntriples, to_rdf
from hi_scenario.validation import validate_rdf


ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def payload():
    return json.loads((ROOT / "examples" / "s1.json").read_text(encoding="utf-8"))


@pytest.fixture
def client():
    with TestClient(api.app) as client:
        yield client


def test_s1_preview_matches_existing_pipeline(client, payload):
    response = client.post("/scenarios/preview", json=payload)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    graph = to_rdf(Scenario.model_validate(payload))
    conforms, _, report = validate_rdf(graph)
    assert response.json() == {
        "scenario_id": "s1",
        "rdf_format": "nt",
        "rdf": to_ntriples(graph),
        "triple_count": 43,
        "validation": {"conforms": conforms, "report": report},
    }
    assert set(Graph().parse(data=response.json()["rdf"], format="nt")) == set(graph)


def test_three_agents_keep_names_identities_and_roles(client, payload):
    payload["agents"][0]["name"] = 'Zoë "User"\n☃'
    payload["agents"].append({
        "id": "second-human",
        "name": payload["agents"][0]["name"],
        "kind": "human",
        "roles": ["HumanUserRole", "ClinicianRole"],
    })
    response = client.post("/scenarios/preview", json=payload)
    assert response.status_code == 200
    graph = Graph().parse(data=response.json()["rdf"], format="nt")
    base = "urn:hi-app:scenario:s1:"
    assert len(set(graph.objects(URIRef(base + "team"), HI.hasMember))) == 3
    for agent in payload["agents"]:
        node = URIRef(base + "agent:" + agent["id"])
        assert set(graph.objects(node, RDFS.label)) == {Literal(agent["name"])}
        assert set(graph.objects(node, HI.hasRoleConcept)) == {HINT[r] for r in agent["roles"]}


@pytest.mark.parametrize(("mutation", "location", "error_type"), [
    ("missing_goal", ["body", "goal"], "missing"),
    ("blank_name", ["body", "agents", 0, "name"], "string_pattern_mismatch"),
    ("duplicate_agent", ["body"], "value_error"),
    ("extra_field", ["body", "unhandled"], "extra_forbidden"),
])
def test_structural_errors_have_locations_and_do_not_run_rdf(
    client, payload, monkeypatch, mutation, location, error_type,
):
    if mutation == "missing_goal":
        del payload["goal"]
    elif mutation == "blank_name":
        payload["agents"][0]["name"] = "   "
    elif mutation == "duplicate_agent":
        payload["agents"][1]["id"] = payload["agents"][0]["id"]
    else:
        payload["unhandled"] = "private test payload"

    def unexpected_conversion(_scenario):
        pytest.fail("Structurally invalid input must not reach RDF generation")

    monkeypatch.setattr(api, "to_rdf", unexpected_conversion)
    response = client.post("/scenarios/preview", json=payload)
    assert response.status_code == 422
    error = response.json()
    assert error["code"] == "invalid_request"
    assert "rdf" not in error
    assert any(i["location"] == location and i["type"] == error_type for i in error["issues"])
    assert all(set(i) == {"location", "message", "type"} for i in error["issues"])
    assert "private test payload" not in response.text


@pytest.mark.parametrize("body", ['{"id":', "[]", "null", ""])
def test_invalid_json_or_body_returns_clear_json_error(client, body):
    response = client.post("/scenarios/preview", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert response.json()["issues"]


@pytest.mark.parametrize(("concept", "message"), [
    ("MadeUpGoal", "Unknown HINT concept: MadeUpGoal"),
    ("HumanUserRole", "HINT concept HumanUserRole is not a Goal concept"),
])
def test_vocabulary_errors_reuse_converter_messages(client, payload, concept, message):
    payload["goal"]["concept"] = concept
    response = client.post("/scenarios/preview", json=payload)
    assert response.status_code == 422
    assert response.json() == {
        "code": "invalid_vocabulary", "message": message, "issues": [], "shacl_report": None,
    }


def test_shacl_failure_returns_real_report_and_no_rdf(client, payload, monkeypatch):
    # Exercise the HTTP failure path with an actual violation of the existing shapes.
    graph = to_rdf(Scenario.model_validate(payload))
    graph.remove((None, HI.hasRoleConcept, None))
    monkeypatch.setattr(api, "to_rdf", lambda _scenario: graph)
    response = client.post("/scenarios/preview", json=payload)
    assert response.status_code == 422
    error = response.json()
    assert error["code"] == "shacl_failed"
    assert "Conforms: False" in error["shacl_report"]
    assert "MUST have at least one RoleConcept" in error["shacl_report"]
    assert "rdf" not in error


@pytest.mark.parametrize(("step", "exception"), [
    ("to_rdf", OSError("private server path")),
    ("validate_rdf", ValueError("private validation internals")),
    ("to_ntriples", RuntimeError("private serialization internals")),
])
def test_server_failures_are_distinct_from_bad_input_and_keep_cors(
    client, payload, monkeypatch, step, exception,
):
    def fail(_value):
        raise exception

    monkeypatch.setattr(api, step, fail)
    response = client.post("/scenarios/preview", json=payload, headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 500
    assert response.json() == {
        "code": "internal_error",
        "message": "Scenario processing failed on the server.",
        "issues": [],
        "shacl_report": None,
    }
    assert "private" not in response.text
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_repeated_submissions_are_deterministic_and_isolated(client, payload):
    first = client.post("/scenarios/preview", json=payload)
    invalid = {**payload, "goal": {**payload["goal"], "concept": "MadeUpGoal"}}
    assert client.post("/scenarios/preview", json=invalid).status_code == 422
    payload["tasks"].reverse()
    payload["agents"].reverse()
    second = client.post("/scenarios/preview", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:5173"])
def test_local_frontend_json_preflight(client, origin):
    response = client.options("/scenarios/preview", headers={
        "Origin": origin,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert set(response.headers["access-control-allow-methods"].split(", ")) == {"GET", "POST"}
    assert "access-control-allow-credentials" not in response.headers


def test_other_origins_are_not_allowed_by_cors(client):
    response = client.options("/scenarios/preview", headers={
        "Origin": "https://other.example",
        "Access-Control-Request-Method": "POST",
    })
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_openapi_uses_existing_scenario_and_documents_responses(client):
    document = client.get("/openapi.json").json()
    operation = document["paths"]["/scenarios/preview"]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/Scenario"
    for status_code, model in (("200", "ScenarioPreview"), ("422", "SubmissionError"), ("500", "SubmissionError")):
        assert operation["responses"][status_code]["content"]["application/json"]["schema"]["$ref"] == f"#/components/schemas/{model}"
