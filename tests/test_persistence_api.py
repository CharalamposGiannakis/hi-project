import json
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from rdflib import Dataset, Graph, Literal, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import RDFS

from hi_scenario import api
from hi_scenario.graphdb import GraphDBSettings, GraphDBStore, HINT_GRAPH, ONTOLOGY_GRAPH, scenario_graph_iri
from hi_scenario.model import Scenario
from hi_scenario.rdf import HI, HINT, to_rdf


ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def payload():
    return json.loads((ROOT / "examples" / "s1.json").read_text(encoding="utf-8"))


@pytest.fixture
def database(monkeypatch):
    # HTTP is mocked, but query/update results are computed by a real RDF/SPARQL
    # engine using the checked-in references, rather than hand-written answers.
    data = Dataset()
    data.graph(URIRef(ONTOLOGY_GRAPH)).parse(ROOT / "ontology" / "hi-ontology.ttl", format="turtle")
    data.graph(URIRef(HINT_GRAPH)).parse(ROOT / "ontology" / "hi-thesaurus.ttl", format="turtle")
    state = {"data": data, "requests": [], "failure": None, "failure_at": None}
    settings = GraphDBSettings()

    def handle(request):
        state["requests"].append(request)
        if state["failure"] is not None and state["failure_at"] in (None, len(state["requests"])):
            if isinstance(state["failure"], int):
                return httpx.Response(state["failure"])
            raise state["failure"]
        fields = parse_qs(request.content.decode("utf-8"))
        if request.url.path == "/repositories/hi/statements":
            assert request.method == "POST"
            update = fields["update"][0]
            assert "FILTER NOT EXISTS" in update
            assert "DELETE" not in update and "CLEAR" not in update
            data.update(update)
            return httpx.Response(204)
        assert request.url.path == "/repositories/hi"
        assert fields["infer"] == ["false"]
        result = data.query(fields["query"][0])
        if request.headers["accept"] == "text/turtle":
            return httpx.Response(200, content=result.serialize(format="turtle"), headers={"Content-Type": "text/turtle"})
        return httpx.Response(200, content=result.serialize(format="json"), headers={"Content-Type": "application/sparql-results+json"})

    @contextmanager
    def connect():
        with httpx.Client(base_url=str(settings.url), transport=httpx.MockTransport(handle)) as client:
            yield GraphDBStore(client, settings)

    monkeypatch.setattr(api, "connect_graphdb", connect)
    return state


@pytest.fixture
def client():
    with TestClient(api.app) as client:
        yield client


def test_save_s1_and_cq1_use_stored_rdf_and_reference_labels(client, database, payload):
    response = client.post("/scenarios", json=payload)
    assert response.status_code == 201
    saved = response.json()
    assert saved["scenario_id"] == "s1"
    assert saved["repository_id"] == "hi"
    assert saved["graph_iri"] == "urn:hi-app:graph:scenario:s1"
    assert saved["workbench_url"] == "http://127.0.0.1:7200/"
    assert saved["workbench_graph_url"] == (
        "http://127.0.0.1:7200/resource?uri=urn%3Ahi-app%3Agraph%3Ascenario%3As1&role=context"
    )
    assert saved["triple_count"] == 117
    assert saved["validation"]["conforms"] is True
    stored = database["data"].graph(URIRef(saved["graph_iri"]))
    assert isomorphic(stored, to_rdf(Scenario.model_validate(payload)))
    result = client.get("/scenarios/s1/team")
    assert result.status_code == 200
    composition = result.json()
    assert composition["team_iri"] == saved["team_iri"]
    assert composition["use_case_iri"] == saved["use_case_iri"]
    assert composition["use_case_name"] == payload["use_case"]["name"]
    members = {member["iri"]: member for member in composition["members"]}
    for agent in payload["agents"]:
        member = members[f"urn:hi-app:scenario:s1:agent:{agent['id']}"]
        assert member["name"] == agent["name"]
        assert member["types"] == [{
            "iri": str(HI.HumanAgent if agent["kind"] == "human" else HI.ArtificialAgent),
            "label": "Human Agent" if agent["kind"] == "human" else "Artificial Agent",
        }]
        assert {role["iri"] for role in member["roles"]} == {str(HINT[r]) for r in agent["roles"]}
        for role in member["roles"]:
            assert role["label"] and role["definition"]
    human = members["urn:hi-app:scenario:s1:agent:human-user"]
    assert human["roles"][0]["label"] == "User Role"


def test_three_agents_shared_names_types_roles_and_multiple_roles_are_not_merged(client, database, payload):
    payload["agents"][0]["name"] = 'Zoë "User"\n☃'
    payload["agents"].append({
        "id": "second-human", "name": payload["agents"][0]["name"],
        "kind": "human", "roles": ["HumanUserRole", "ClinicianRole"],
    })
    assert client.post("/scenarios", json=payload).status_code == 201
    result = client.get("/scenarios/s1/team").json()
    members = {m["iri"]: m for m in result["members"]}
    assert len(members) == 3
    first = members["urn:hi-app:scenario:s1:agent:human-user"]
    second = members["urn:hi-app:scenario:s1:agent:second-human"]
    assert first["name"] == second["name"] == payload["agents"][0]["name"]
    assert first["types"] == second["types"]
    assert len(first["roles"]) == 1 and len(second["roles"]) == 2


def test_cq1_reads_database_edits_and_does_not_fabricate_missing_labels(client, database, payload):
    assert client.post("/scenarios", json=payload).status_code == 201
    scenario_graph = database["data"].graph(URIRef(scenario_graph_iri("s1")))
    member = URIRef("urn:hi-app:scenario:s1:agent:human-user")
    scenario_graph.set((member, RDFS.label, Literal("Name changed in GraphDB")))
    database["data"].graph(URIRef(HINT_GRAPH)).remove((None, None, None))
    database["data"].graph(URIRef(ONTOLOGY_GRAPH)).remove((None, None, None))
    result = client.get("/scenarios/s1/team")
    assert result.status_code == 200
    members = {m["iri"]: m for m in result.json()["members"]}
    assert members[str(member)]["name"] == "Name changed in GraphDB"
    assert len(members) == 2
    for agent in members.values():
        assert all(t["label"] is None for t in agent["types"])
        assert all(r["label"] is None and r["definition"] is None for r in agent["roles"])


def test_existing_id_is_rejected_without_writes_or_data_loss(client, database, payload):
    assert client.post("/scenarios", json=payload).status_code == 201
    before = set(database["data"].quads())
    database["requests"].clear()
    payload["agents"][0]["name"] = "Changed name"
    response = client.post("/scenarios", json=payload)
    assert response.status_code == 409
    assert response.json()["code"] == "scenario_exists"
    assert set(database["data"].quads()) == before
    assert len(database["requests"]) == 1
    assert database["requests"][0].url.path == "/repositories/hi"


def test_confirmation_timeout_does_not_retry_or_overwrite_a_committed_save(client, database, payload):
    database["failure"] = httpx.ReadTimeout("Response lost after commit")
    database["failure_at"] = 3  # ASK, insert, then failed read-back.
    response = client.post("/scenarios", json=payload)
    assert response.status_code == 503
    assert len(database["requests"]) == 3
    stored = database["data"].graph(URIRef(scenario_graph_iri("s1")))
    assert isomorphic(stored, to_rdf(Scenario.model_validate(payload)))
    database["failure"] = None
    assert client.get("/scenarios/s1/team").status_code == 200
    assert client.post("/scenarios", json=payload).status_code == 409


@pytest.mark.parametrize("invalid", ["structure", "vocabulary", "shacl"])
def test_invalid_scenarios_do_not_contact_graphdb(client, database, payload, monkeypatch, invalid):
    if invalid == "structure":
        payload["agents"][1]["id"] = payload["agents"][0]["id"]
    elif invalid == "vocabulary":
        payload["goal"]["concept"] = "MadeUpGoal"
    else:
        graph = to_rdf(Scenario.model_validate(payload))
        graph.remove((None, HI.hasRoleConcept, None))
        monkeypatch.setattr(api, "to_rdf", lambda _: graph)
    response = client.post("/scenarios", json=payload)
    assert response.status_code == 422
    assert database["requests"] == []


def test_missing_scenario_is_404_not_empty_success(client, database):
    response = client.get("/scenarios/missing/team")
    assert response.status_code == 404
    assert response.json()["code"] == "scenario_not_found"


@pytest.mark.parametrize("scenario_id", ["Bad-ID", "injected:graph", "unsafe%3E%20%7B"])
def test_invalid_path_identifiers_are_rejected_before_querying(client, database, scenario_id):
    response = client.get(f"/scenarios/{scenario_id}/team")
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert database["requests"] == []


@pytest.mark.parametrize("failure", [503, 404, 401, httpx.ConnectError("private connection details"), httpx.ReadTimeout("private timeout details")])
@pytest.mark.parametrize("operation", ["save", "team"])
def test_graphdb_failures_are_clear_and_do_not_expose_details(client, database, payload, failure, operation):
    database["failure"] = failure
    headers = {"Origin": "http://localhost:5173"}
    response = client.post("/scenarios", json=payload, headers=headers) if operation == "save" else client.get("/scenarios/s1/team", headers=headers)
    assert response.status_code == 503
    assert response.json()["code"] == "graphdb_unavailable"
    assert "private" not in response.text
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_preview_is_independent_of_graphdb(client, database, payload):
    database["failure"] = httpx.ConnectError("GraphDB offline")
    assert client.post("/scenarios/preview", json=payload).status_code == 200
    assert database["requests"] == []


@pytest.mark.parametrize("body", [b"not JSON", b"[]", b'{"results":{"bindings":[{}]}}'])
def test_bad_graphdb_query_responses_are_502(client, monkeypatch, body):
    @contextmanager
    def connect():
        with httpx.Client(base_url="http://127.0.0.1:7200", transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))) as http:
            yield GraphDBStore(http, GraphDBSettings())
    monkeypatch.setattr(api, "connect_graphdb", connect)
    response = client.get("/scenarios/s1/team")
    assert response.status_code == 502
    assert response.json()["code"] == "graphdb_invalid_response"


def test_connection_settings_are_configurable_and_reject_unsafe_values(monkeypatch):
    monkeypatch.setenv("GRAPHDB_URL", "https://db.example/graphdb/")
    monkeypatch.setenv("GRAPHDB_WORKBENCH_URL", "https://workbench.example/")
    monkeypatch.setenv("GRAPHDB_REPOSITORY", "hi-research")
    monkeypatch.setenv("GRAPHDB_TIMEOUT_SECONDS", "3.5")
    settings = GraphDBSettings.from_env()
    assert str(settings.url) == "https://db.example/graphdb/"
    assert str(settings.workbench_url) == "https://workbench.example/"
    assert settings.repository == "hi-research" and settings.timeout_seconds == 3.5
    for values in ({"url": "http://user:secret@localhost:7200"}, {"workbench_url": "http://user:secret@localhost:7200"}, {"repository": "hi/../../other"}, {"timeout_seconds": 0}):
        with pytest.raises(ValidationError):
            GraphDBSettings(**values)


def test_workbench_link_uses_public_address_not_internal_graphdb_address():
    settings = GraphDBSettings(url="http://graphdb:7200", workbench_url="https://workbench.example")
    with httpx.Client(base_url=str(settings.url)) as http:
        location = GraphDBStore(http, settings).location("s1", "urn:case", "urn:team")
    assert location["workbench_url"] == "https://workbench.example/"
    assert location["workbench_graph_url"].startswith("https://workbench.example/resource?")
    assert "graphdb:7200" not in str(location)


def test_configured_url_base_path_is_used_for_graphdb_requests():
    paths = []

    def handle(request):
        paths.append(request.url.path)
        return httpx.Response(200, json={"boolean": False})

    settings = GraphDBSettings(url="https://db.example/graphdb/", repository="hi-research")
    with httpx.Client(base_url=str(settings.url), transport=httpx.MockTransport(handle)) as http:
        assert GraphDBStore(http, settings).exists(scenario_graph_iri("s1")) is False
    assert paths == ["/graphdb/repositories/hi-research"]


def test_misconfiguration_has_clear_error_and_preview_still_works(client, payload, monkeypatch):
    monkeypatch.setenv("GRAPHDB_TIMEOUT_SECONDS", "invalid")
    response = client.post("/scenarios", json=payload)
    assert response.status_code == 503
    assert response.json()["code"] == "graphdb_configuration"
    assert client.post("/scenarios/preview", json=payload).status_code == 200


def test_new_endpoints_and_get_cors_are_documented(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert paths["/scenarios"]["post"]["responses"]["201"]["content"]["application/json"]["schema"]["$ref"].endswith("SavedScenario")
    assert "404" in paths["/scenarios/{scenario_id}/team"]["get"]["responses"]
    response = client.options("/scenarios/s1/team", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
