"""Exercise the Explorer API and its SPARQL over an isolated repository fixture."""

import json
import os
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi.testclient import TestClient
from rdflib import Dataset, URIRef

from hi_scenario import api, graphdb
from hi_scenario.model import Scenario
from hi_scenario.rdf import to_rdf


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "/repositories/hi"
TRANSACTIONS = f"{REPOSITORY}/transactions"
APPROVED_ID = "explorer-approved-fixture"
UNLISTED_ID = "explorer-unlisted-fixture"


def _example(scenario_id, member_name):
    data = json.loads((ROOT / "examples" / "s1.json").read_bytes())
    data["id"] = scenario_id
    data["agents"][0]["name"] = member_name
    return data


class _Repository:
    """Run the actual SELECT/ASK and keep each RDF4J transaction isolated."""

    def __init__(self):
        self.committed = Dataset()
        for iri, file in ((graphdb.ONTOLOGY_GRAPH, "hi-ontology.ttl"), (graphdb.HINT_GRAPH, "hi-thesaurus.ttl")):
            self.committed.graph(URIRef(iri)).parse(ROOT / "ontology" / file, format="turtle")
        for scenario_id, name in ((APPROVED_ID, "Approved member"), (UNLISTED_ID, "Unlisted member")):
            context = self.committed.graph(URIRef(graphdb.scenario_graph_iri(scenario_id)))
            context += to_rdf(Scenario.model_validate(_example(scenario_id, name)))
        self.transactions = {}
        self.started = 0
        self.rolled_back = 0
        self.staged_contexts = []
        self.fail_queries = False
        self.location_origin = "http://explorer-db.test"

    def handle(self, request):
        assert request.url.host == "explorer-db.test"
        path = request.url.path
        if path == TRANSACTIONS:
            assert request.method == "POST"
            self.started += 1
            path = f"{TRANSACTIONS}/{self.started}"
            transaction = Dataset()
            for quad in self.committed.quads():
                transaction.add(quad)
            self.transactions[path] = transaction
            return httpx.Response(201, headers={"Location": f"{self.location_origin}{path}"})

        if path == REPOSITORY:
            assert request.method == "POST"
            params = parse_qs(request.content.decode(), strict_parsing=True)
            assert params.keys() == {"query", "infer"}
            assert params["infer"] == ["false"]
            return self.read(self.committed, params["query"][0])

        assert path in self.transactions, f"Unexpected repository operation {request.method} {path}"
        if request.method == "DELETE":
            del self.transactions[path]
            self.rolled_back += 1
            return httpx.Response(204)

        assert request.method == "PUT"
        action = request.url.params["action"]
        if action == "ADD":
            assert request.headers["Content-Type"].split(";")[0] == "application/n-triples"
            context = request.url.params["context"]
            assert context.startswith("<") and context.endswith(">")
            iri = URIRef(context[1:-1])
            self.staged_contexts.append(iri)
            self.transactions[path].graph(iri).parse(data=request.content, format="nt")
            return httpx.Response(200)

        assert action == "QUERY", "Explorer transactions must remain uncommitted"
        assert request.url.params["infer"] == "false"
        assert request.headers["Content-Type"].split(";")[0] == "application/sparql-query"
        if self.fail_queries:
            return httpx.Response(503)
        return self.read(self.transactions[path], request.content.decode())

    @staticmethod
    def read(dataset, query):
        result = dataset.query(query)
        assert result.type in {"SELECT", "ASK"}
        return httpx.Response(200, content=result.serialize(format="json"), headers={
            "Content-Type": "application/sparql-results+json",
        })


@pytest.fixture
def explorer(monkeypatch):
    store = _Repository()
    real_client = httpx.Client

    def repository_client(*args, **kwargs):
        return real_client(*args, transport=httpx.MockTransport(store.handle), **kwargs)

    monkeypatch.setenv("GRAPHDB_URL", "http://explorer-db.test")
    monkeypatch.setenv("GRAPHDB_REPOSITORY", "hi")
    monkeypatch.delenv("GRAPHDB_APPROVED_SCENARIO_IDS", raising=False)
    monkeypatch.setattr(graphdb.httpx, "Client", repository_client)
    with TestClient(api.app) as client:
        yield client, store
    assert store.transactions == {}
    assert store.rolled_back == store.started


def _query(client, **data):
    response = client.post("/explorer/query", json=data)
    assert response.status_code == 200, response.text
    return response.json()


def _rows_with(result, label):
    return [row for row in result["rows"] if label in row["values"].values()]


def test_reference_catalog_and_cq1_read_public_examples_without_publishing(explorer):
    client, store = explorer
    response = client.get("/explorer/catalog")
    assert response.status_code == 200, response.text
    catalog = response.json()
    assert catalog["shared_source"] == "reference"
    assert catalog["warnings"] == []
    assert {item["scenario_id"] for item in catalog["scenarios"]} == {f"s{number}" for number in range(1, 8)}
    assert {item["id"] for item in catalog["questions"]} == {"cq1", "cq2", "cq5", "cq8", "cq11"}

    result = _query(client, question_id="cq1", scope="shared", shared_scenario_id="s1")
    assert _rows_with(result, "Human user")
    assert _rows_with(result, "AI assistant")
    assert all(row["evidence"] for row in result["rows"])
    assert result["truncated"] is False
    assert store.staged_contexts
    assert all(not any(store.committed.quads((None, None, None, iri))) for iri in store.staged_contexts)


def test_combined_scope_keeps_a_private_draft_separate_even_with_a_matching_id(explorer, monkeypatch):
    client, store = explorer
    store.location_origin = "http://proxy-forwarded.invalid"
    monkeypatch.setenv("GRAPHDB_APPROVED_SCENARIO_IDS", APPROVED_ID)
    response = client.get("/explorer/catalog")
    assert response.status_code == 200, response.text
    catalog = response.json()
    assert catalog["shared_source"] == "approved"
    assert catalog["warnings"] == []
    assert [item["scenario_id"] for item in catalog["scenarios"]] == [APPROVED_ID]

    private_member = 'Zoë "Draft member"\nNo publication'
    scenario = _example(APPROVED_ID, private_member)
    result = _query(client, question_id="cq1", scope="combined", scenario=scenario, shared_scenario_id=APPROVED_ID)
    (draft_row,) = _rows_with(result, private_member)
    (approved_row,) = _rows_with(result, "Approved member")
    assert draft_row["source_id"] == f"provisional:{APPROVED_ID}"
    assert approved_row["source_id"] == f"approved:{APPROVED_ID}"
    assert not _rows_with(result, "Unlisted member")

    assert URIRef(graphdb.scenario_graph_iri(APPROVED_ID)) not in store.staged_contexts
    assert all(not any(store.committed.quads((None, None, None, iri))) for iri in store.staged_contexts)
    shared = _query(client, question_id="cq1", scope="shared", shared_scenario_id=APPROVED_ID)
    assert not _rows_with(shared, private_member)
    assert _rows_with(shared, "Approved member")

    denied = client.post("/explorer/query", json={
        "question_id": "cq1", "scope": "shared", "shared_scenario_id": UNLISTED_ID,
    })
    assert denied.status_code == 404


def test_query_failure_rolls_back_the_private_draft(explorer):
    client, store = explorer
    store.fail_queries = True
    response = client.post("/explorer/query", json={
        "question_id": "cq1", "scope": "draft", "scenario": _example("draft-only", "Unsaved member"),
    })
    assert response.status_code == 503
    assert response.json()["code"] == "graphdb_unavailable"
    assert store.staged_contexts
    assert store.started == store.rolled_back == 1


def test_save_cannot_fill_an_empty_approved_graph(explorer, monkeypatch):
    client, store = explorer
    reserved = "missing-approved-scenario"
    monkeypatch.setenv("GRAPHDB_APPROVED_SCENARIO_IDS", reserved)
    response = client.post("/scenarios", json=_example(reserved, "Unapproved member"))
    assert response.status_code == 409
    assert response.json()["code"] == "scenario_id_reserved"
    assert not list(store.committed.graph(URIRef(graphdb.scenario_graph_iri(reserved))))
    catalog = client.get("/explorer/catalog").json()
    assert catalog["shared_source"] == "reference"
    assert len(catalog["warnings"]) == 1
    assert "resolve to no available scenario graphs" in catalog["warnings"][0]
    result = _query(client, question_id="cq1", scope="shared", shared_scenario_id="s1")
    assert result["notices"] == [{
        "code": "approved_graphs_unavailable", "source_id": None, "message": catalog["warnings"][0],
    }]


@pytest.mark.parametrize(("scenario_id", "count"), [("s2", 1), ("s3", 2)])
def test_cq5_reports_interactions_without_inventing_execution_links(explorer, scenario_id, count):
    client, store = explorer
    result = _query(client, question_id="cq5", scope="shared", shared_scenario_id=scenario_id)
    assert result["rows"] == []
    (notice,) = result["notices"]
    assert notice["source_id"] == f"reference:{scenario_id}"
    assert notice["code"] == "interactions_without_execution_links"
    assert notice["message"].startswith(f"{count} recorded interaction")
    assert "no recorded link to a task execution" in notice["message"]
    assert not store.transactions


def test_cq5_missing_link_notice_is_scoped_alongside_existing_results(explorer, monkeypatch):
    client, store = explorer
    monkeypatch.setenv("GRAPHDB_APPROVED_SCENARIO_IDS", APPROVED_ID)
    scenario = json.loads((ROOT / "examples" / "s2.json").read_bytes())
    result = _query(client, question_id="cq5", scope="combined", scenario=scenario)
    assert result["rows"]
    assert {row["source_id"] for row in result["rows"]} == {f"approved:{APPROVED_ID}"}
    assert [notice["source_id"] for notice in result["notices"]] == ["provisional:s2"]
    assert not store.transactions


def test_incomplete_draft_is_rejected_before_opening_a_transaction(explorer):
    client, store = explorer
    scenario = _example("incomplete", "Human member")
    scenario["agents"] = scenario["agents"][:1]
    response = client.post("/explorer/query", json={"question_id": "cq1", "scope": "draft", "scenario": scenario})
    assert response.status_code == 422
    assert store.started == 0


@pytest.mark.skipif(os.getenv("HI_GRAPHDB_LIVE") != "1", reason="Set HI_GRAPHDB_LIVE=1 for the local GraphDB check")
@pytest.mark.parametrize(("scenario_id", "question_id", "rows_per_source"), [
    ("s1", "cq1", 2), ("s1", "cq2", 4), ("s1", "cq5", 2), ("s1", "cq8", 6), ("s1", "cq11", 3),
    ("s7", "cq2", 8), ("s2", "cq8", 10), ("s5", "cq8", 4), ("s2", "cq5", 0), ("s3", "cq5", 0),
])
def test_live_explorer_queries_both_named_graphs_and_rolls_back(monkeypatch, scenario_id, question_id, rows_per_source):
    settings = graphdb.GraphDBSettings.from_env()
    assert settings.url.host in {"127.0.0.1", "localhost", "[::1]"}, "Use an existing loopback GraphDB repository."
    monkeypatch.delenv("GRAPHDB_APPROVED_SCENARIO_IDS", raising=False)

    private_member = "Explorer live draft member"
    scenario = json.loads((ROOT / "examples" / f"{scenario_id}.json").read_bytes())
    scenario["agents"][0]["name"] = private_member
    with TestClient(api.app) as client:
        result = _query(
            client, question_id=question_id, scope="combined", scenario=scenario, shared_scenario_id=scenario_id,
        )

    assert {source["publication_status"] for source in result["sources"]} == {"provisional", "reference"}
    assert {source["id"] for source in result["sources"]} == {f"provisional:{scenario_id}", f"reference:{scenario_id}"}
    expected = {f"provisional:{scenario_id}": rows_per_source, f"reference:{scenario_id}": rows_per_source}
    assert Counter(row["source_id"] for row in result["rows"]) == (expected if rows_per_source else {})
    assert result["truncated"] is False
    if question_id == "cq5" and scenario_id in {"s2", "s3"}:
        assert {notice["source_id"] for notice in result["notices"]} == {f"provisional:{scenario_id}", f"reference:{scenario_id}"}
    if question_id == "cq1":
        assert {row["source_id"] for row in _rows_with(result, private_member)} == {"provisional:s1"}
        assert {row["source_id"] for row in _rows_with(result, "Human user")} == {"reference:s1"}
    with graphdb.connect_graphdb() as store:
        for source in result["sources"]:
            assert not store.exists(source["graph_iri"])
