"""Opt-in importer rehearsal: isolated UUID graphs, no GraphDB restart or user-data cleanup."""

import os
from uuid import uuid4

import httpx
import pytest
from rdflib import Graph, Literal
from rdflib.compare import isomorphic
from rdflib.namespace import RDF, RDFS

from hi_scenario.graphdb import GraphDBStore
from hi_scenario.rdf import HI, to_rdf
from infra import canonical
from infra.graphdb import read_graph


pytestmark = pytest.mark.skipif(os.getenv("HI_GRAPHDB_LIVE") != "1", reason="Set HI_GRAPHDB_LIVE=1 to verify local GraphDB")


def test_live_canonical_import_idempotency_conflict_partial_resume_and_protection():
    settings = canonical.local_settings()
    corpus = canonical.load_corpus()
    assert all(entry.graph is not None for entry in corpus)
    owned = []

    with httpx.Client(base_url=str(settings.url), timeout=40, trust_env=False, follow_redirects=False) as client:
        store = GraphDBStore(client, settings)
        canonical.check_environment(client)

        # Snapshot every existing named graph; none is owned or modified by this test.
        query = "SELECT DISTINCT ?graph WHERE { GRAPH ?graph { ?s ?p ?o } }"
        response = client.post("/repositories/hi", data={"query": query, "infer": "false"},
                               headers={"Accept": "application/sparql-results+json"})
        response.raise_for_status()
        before = {row["graph"]["value"]: read_graph(client, row["graph"]["value"])
                  for row in response.json()["results"]["bindings"]}

        def isolated():
            prefix = "test-canonical-" + uuid4().hex
            entries = []
            for original in corpus:
                scenario = original.scenario.model_copy(update={"id": f"{prefix}-{original.id}"})
                entry = canonical.Entry(scenario.id, original.count, scenario, to_rdf(scenario), "validated")
                assert not store.exists(entry.iri)
                owned.append(entry.iri)  # Only graphs confirmed absent before this test.
                entries.append(entry)
            return entries

        try:
            entries = isolated()
            assert canonical.run("plan", store, entries) == 0
            assert all(entry.state == canonical.MISSING for entry in entries)
            assert canonical.run("apply", store, entries) == 0
            first = {entry.iri: read_graph(client, entry.iri) for entry in entries}
            assert canonical.run("apply", store, entries) == 0
            assert canonical.run("verify", store, entries) == 0
            for entry in entries:
                assert set(read_graph(client, entry.iri)) == set(first[entry.iri]) == set(entry.graph)

            conflicting = isolated()
            last = conflicting[-1]
            graph = Graph() + last.graph
            use_case = next(graph.subjects(RDF.type, HI.UseCase))
            graph.set((use_case, RDFS.label, Literal("Deliberate test conflict; retain unchanged")))
            assert len(graph) == last.count
            store.save(last.id, graph)
            assert canonical.run("apply", store, conflicting) == 1
            assert isomorphic(graph, read_graph(client, last.iri))
            assert all(not store.exists(entry.iri) for entry in conflicting[:-1])

            partial = isolated()
            for entry in partial[:2]:
                store.save(entry.id, entry.graph)
            assert canonical.run("apply", store, partial) == 0
            assert canonical.run("verify", store, partial) == 0
            for iri, graph in before.items():
                assert isomorphic(graph, read_graph(client, iri)), f"Existing graph changed: {iri}"
        finally:
            for iri in owned:
                client.delete("/repositories/hi/statements", params={"context": f"<{iri}>"}).raise_for_status()
                assert not store.exists(iri)
        for iri, graph in before.items():
            assert isomorphic(graph, read_graph(client, iri)), f"Existing graph changed: {iri}"
