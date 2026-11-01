"""Importer tests use real RDFLib SPARQL with a mocked GraphDB HTTP boundary."""

import json
from dataclasses import replace
from urllib.parse import parse_qs

import httpx
import pytest
from rdflib import Dataset, Graph, Literal, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import RDF, RDFS

from hi_scenario.graphdb import GraphDBSettings, GraphDBStore, HINT_GRAPH, ONTOLOGY_GRAPH
from hi_scenario.rdf import HI
from infra import canonical


@pytest.fixture(scope="module")
def corpus():
    return canonical.load_corpus()


@pytest.fixture
def entries(corpus):
    return [replace(entry) for entry in corpus]


@pytest.fixture
def database():
    data = Dataset()
    for path, iri in canonical.REFERENCES:
        data.graph(URIRef(iri)).parse(path, format="turtle")
    unrelated = data.graph(URIRef("urn:hi-app:graph:scenario:unrelated"))
    unrelated.add((URIRef("urn:unrelated"), RDFS.label, Literal("Keep this research data")))
    state = {"data": data, "requests": [], "writes": [], "fail_at": None,
             "lose_response": False, "unavailable": False,
             "params": {"ruleset": {"value": "empty"}, "disableSameAs": {"value": "true"}}}

    def handle(request):
        state["requests"].append(request)
        if state["unavailable"]:
            raise httpx.ConnectError("Offline", request=request)
        if request.method == "GET" and request.url.path == "/rest/repositories/hi":
            return httpx.Response(200, json={"params": state["params"]})
        assert request.method == "POST"  # No PUT, DELETE, or setup calls are allowed.
        fields = parse_qs(request.content.decode())
        if request.url.path == "/repositories/hi/statements":
            update = fields["update"][0]
            assert "FILTER NOT EXISTS" in update and "INSERT" in update
            assert not any(token in update for token in ("DELETE", "CLEAR", "DROP"))
            state["writes"].append(update)
            failing = len(state["writes"]) == state["fail_at"]
            if not failing or state["lose_response"]:
                data.update(update)
            if failing:
                raise httpx.ReadTimeout("Lost save response", request=request)
            return httpx.Response(204)
        assert request.url.path == "/repositories/hi"
        assert fields["infer"] == ["false"]
        query = fields["query"][0]
        assert "INSERT" not in query and "DELETE" not in query
        result = data.query(query)
        if request.headers["accept"] == "text/turtle":
            return httpx.Response(200, content=result.serialize(format="turtle"))
        return httpx.Response(200, content=result.serialize(format="json"))

    with httpx.Client(base_url="http://127.0.0.1:7200", transport=httpx.MockTransport(handle)) as client:
        yield GraphDBStore(client, GraphDBSettings()), state


def snapshot(data):
    return {str(graph.identifier): set(graph) for graph in data.graphs() if len(graph)}


def seed(state, entry):
    graph = state["data"].graph(URIRef(entry.iri))
    graph += entry.graph


def assert_protected(state, before):
    after = snapshot(state["data"])
    for iri, graph in before.items():
        assert after[iri] == graph


def test_inventory_complete_semantic_validation_and_counts(entries):
    assert [(e.id, e.count) for e in entries] == [
        ("s1", 127), ("s2", 195), ("s3", 135), ("s4", 154),
        ("s5", 139), ("s6", 150), ("s7", 173),
    ]
    for entry, entities in zip(entries, (23, 40, 24, 26, 24, 26, 29), strict=True):
        assert entry.state == "validated", entry.detail
        assert entry.scenario.id == entry.id
        assert entry.iri == f"urn:hi-app:graph:scenario:{entry.id}"
        assert len(entry.graph) == entry.count
        assert len(set(entry.graph.subjects(RDF.type, None))) == entities


def test_plan_is_read_only_and_distinguishes_full_graph_conflicts(database, entries, capsys):
    store, state = database
    seed(state, entries[0])
    seed(state, entries[1])
    graph = state["data"].graph(URIRef(entries[1].iri))
    node = next(graph.subjects(RDF.type, HI.UseCase))
    graph.set((node, RDFS.label, Literal("Different, but same triple count")))
    assert len(graph) == entries[1].count
    before = snapshot(state["data"])
    assert canonical.run("plan", store, entries) == 1
    assert [e.state for e in entries] == [canonical.IDENTICAL, canonical.CONFLICT] + [canonical.MISSING] * 5
    assert snapshot(state["data"]) == before
    assert not state["writes"]
    assert "No writes attempted" in capsys.readouterr().out


def test_first_apply_second_apply_and_read_only_verify(database, entries, capsys):
    store, state = database
    before = snapshot(state["data"])
    assert canonical.run("plan", store, entries) == 0  # Missing is actionable, not a plan error.
    assert not state["writes"]
    assert canonical.run("apply", store, entries) == 0
    assert len(state["writes"]) == 7
    for entry in entries:
        stored = state["data"].graph(URIRef(entry.iri))
        assert set(stored) == set(entry.graph)
        assert isomorphic(stored, entry.graph)
        assert entry.state == canonical.IDENTICAL
    assert_protected(state, before)
    imported = snapshot(state["data"])
    assert canonical.run("apply", store, entries) == 0
    assert "Created this run (confirmed save responses): none" in capsys.readouterr().out
    assert len(state["writes"]) == 7
    assert canonical.run("verify", store, entries) == 0
    assert snapshot(state["data"]) == imported
    assert len(state["writes"]) == 7
    cq1_requests = [request for request in state["requests"] if b"SELECT+DISTINCT" in request.content]
    assert len(cq1_requests) == 21  # Apply twice and verify: CQ1 for every scenario.


def test_apply_preflights_last_conflict_before_any_write(database, entries):
    store, state = database
    conflict = state["data"].graph(URIRef(entries[-1].iri))
    conflict.add((URIRef("urn:existing"), RDFS.label, Literal("Unrelated content using s7 ID")))
    before = snapshot(state["data"])
    assert canonical.run("apply", store, entries) == 1
    assert entries[-1].state == canonical.CONFLICT
    assert not state["writes"]
    assert snapshot(state["data"]) == before


@pytest.mark.parametrize("bad_input", ["id", "hint", "json", "missing", "count", "shacl"])
def test_all_canonical_inputs_checked_before_apply(database, tmp_path, monkeypatch, bad_input):
    examples = tmp_path / "examples"
    examples.mkdir()
    for scenario_id, _ in canonical.INVENTORY:
        (examples / f"{scenario_id}.json").write_bytes((canonical.ROOT / "examples" / f"{scenario_id}.json").read_bytes())
    target = examples / "s7.json"
    payload = json.loads(target.read_text(encoding="utf-8"))
    if bad_input == "id":
        payload["id"] = "another-id"
    elif bad_input == "hint":
        payload["agents"][0]["roles"] = ["PrivacyConstraint"]
    elif bad_input == "count":
        payload["tasks"][0]["description"] = "An unexpected assertion"
    target.write_text(json.dumps(payload), encoding="utf-8")
    if bad_input == "json":
        target.write_text("{", encoding="utf-8")
    elif bad_input == "missing":
        target.unlink()
    elif bad_input == "shacl":
        real_validate = canonical.validate_rdf
        monkeypatch.setattr(canonical, "validate_rdf", lambda graph:
                            (False, Graph(), "Test nonconformance") if len(graph) == 173 else real_validate(graph))
    entries = canonical.load_corpus(tmp_path)
    assert entries[-1].state == canonical.INVALID
    assert all(e.graph is not None for e in entries[:-1])
    store, state = database
    before = snapshot(state["data"])
    assert canonical.run("apply", store, entries) == 1
    assert not state["writes"]
    assert snapshot(state["data"]) == before


@pytest.mark.parametrize("lose_response", [False, True])
def test_interrupted_apply_reports_confirmed_and_uncertain_graphs_and_resumes(database, entries, capsys, lose_response):
    store, state = database
    before = snapshot(state["data"])
    state.update(fail_at=3, lose_response=lose_response)
    assert canonical.run("apply", store, entries) == 1
    output = capsys.readouterr().out
    assert f"Created this run (confirmed save responses): {entries[0].iri}, {entries[1].iri}" in output
    assert f"Save outcome for <{entries[2].iri}> may be uncertain" in output
    present = entries[:3 if lose_response else 2]
    for entry in present:
        assert set(state["data"].graph(URIRef(entry.iri))) == set(entry.graph)
    assert_protected(state, before)
    state["fail_at"] = None
    state["writes"].clear()
    assert canonical.run("apply", store, entries) == 0
    assert len(state["writes"]) == 7 - len(present)
    for entry in entries:
        assert set(state["data"].graph(URIRef(entry.iri))) == set(entry.graph)
    assert_protected(state, before)


def test_partially_imported_corpus_is_completed_without_touching_existing_graphs(database, entries):
    store, state = database
    for entry in entries[:3]:
        seed(state, entry)
    before = snapshot(state["data"])
    assert canonical.run("apply", store, entries) == 0
    assert len(state["writes"]) == 4
    assert_protected(state, before)


@pytest.mark.parametrize("command", ["plan", "apply", "verify"])
def test_unavailability_is_reported_without_writing(database, entries, command):
    store, state = database
    state["unavailable"] = True
    assert canonical.run(command, store, entries) == 1
    assert all(e.state == canonical.UNAVAILABLE for e in entries)
    assert not state["writes"]


@pytest.mark.parametrize("params", [{}, {"ruleset": {"value": "owl2-rl"}},
                                   {"ruleset": {"value": "empty"}, "disableSameAs": {"value": "false"}}])
def test_wrong_repository_configuration_prevents_apply(database, entries, params):
    store, state = database
    state["params"] = params
    assert canonical.run("apply", store, entries) == 1
    assert not state["writes"]


@pytest.mark.parametrize("iri", [ONTOLOGY_GRAPH, HINT_GRAPH])
def test_each_reference_is_independently_verified_and_never_repaired(database, entries, iri, capsys):
    store, state = database
    state["data"].graph(URIRef(iri)).remove((None, None, None))
    before = snapshot(state["data"])
    assert canonical.run("apply", store, entries) == 1
    output = capsys.readouterr().out
    assert f"Reference <{iri}>: FAILED" in output
    assert all(f"Reference <{ref}>:" in output for _, ref in canonical.REFERENCES)
    assert not state["writes"]
    assert snapshot(state["data"]) == before


def test_verify_reports_missing_and_incomplete_graphs_without_writes(database, entries):
    store, state = database
    seed(state, entries[0])
    seed(state, entries[1])
    graph = state["data"].graph(URIRef(entries[1].iri))
    graph.remove(next(iter(graph)))
    before = snapshot(state["data"])
    assert canonical.run("verify", store, entries) == 1
    assert entries[0].state == canonical.IDENTICAL
    assert entries[1].state == canonical.CONFLICT
    assert entries[2].state == canonical.MISSING
    assert not state["writes"]
    assert snapshot(state["data"]) == before


def test_verify_checks_cq1_roles_and_distinct_identities_not_only_graph_equality(database, entries, monkeypatch):
    store, state = database
    for entry in entries:
        seed(state, entry)
    real_team = store.team

    def wrong_team(scenario_id):
        team = real_team(scenario_id)
        if scenario_id == "s3":
            assert len(team["members"]) == 3
            team["members"].pop()  # A merged/omitted member must fail despite correct stored RDF.
        return team

    monkeypatch.setattr(store, "team", wrong_team)
    assert canonical.run("verify", store, entries) == 1
    assert entries[2].state == canonical.CONFLICT
    assert "CQ1" in entries[2].detail
    assert not state["writes"]


@pytest.mark.parametrize("url,repository", [
    ("https://example.org", "hi"), ("http://graphdb:7200", "hi"),
    ("http://127.0.0.1:7201", "hi"), ("http://127.0.0.1:7200/production", "hi"),
    ("http://127.0.0.1:7200", "production"),
])
def test_remote_or_nonstandard_targets_rejected_before_loading_or_connecting(monkeypatch, url, repository):
    monkeypatch.setenv("GRAPHDB_URL", url)
    monkeypatch.setenv("GRAPHDB_REPOSITORY", repository)
    monkeypatch.setattr(canonical, "load_corpus", lambda: pytest.fail("Must reject target first"))
    assert canonical.main(["apply"]) == 1


@pytest.mark.parametrize("url", ["http://127.0.0.1:7200", "http://localhost:7200"])
def test_designated_local_target_allowed(monkeypatch, url):
    monkeypatch.setenv("GRAPHDB_URL", url)
    monkeypatch.setenv("GRAPHDB_REPOSITORY", "hi")
    assert str(canonical.local_settings().url) == url + "/"


def test_invalid_configuration_values_are_not_echoed(monkeypatch, capsys):
    monkeypatch.setenv("GRAPHDB_URL", "invalid-configuration-value")
    assert canonical.main(["plan"]) == 1
    assert "invalid-configuration-value" not in capsys.readouterr().out
