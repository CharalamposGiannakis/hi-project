"""Opt-in verification against the local Compose repository; owns only UUID test graphs."""

import json
import os
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from rdflib import URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import RDF

from hi_scenario import api
from hi_scenario.graphdb import scenario_graph_iri
from hi_scenario.model import Scenario
from hi_scenario.rdf import HI, to_rdf
from infra.graphdb import BASE_URL, ROOT, check_references, check_repository, read_graph, wait_for_server


pytestmark = pytest.mark.skipif(os.getenv("HI_GRAPHDB_LIVE") != "1", reason="Set HI_GRAPHDB_LIVE=1 to verify local GraphDB")


def test_live_persistence_cq1_conflicts_concurrency_restart_and_unavailability(monkeypatch):
    monkeypatch.setenv("GRAPHDB_URL", BASE_URL)
    monkeypatch.setenv("GRAPHDB_REPOSITORY", "hi")
    monkeypatch.setenv("GRAPHDB_TIMEOUT_SECONDS", "10")
    original = json.loads((ROOT / "examples" / "s1.json").read_text(encoding="utf-8"))
    s2 = json.loads((ROOT / "examples" / "s2.json").read_text(encoding="utf-8"))
    s3 = json.loads((ROOT / "examples" / "s3.json").read_text(encoding="utf-8"))
    s4 = json.loads((ROOT / "examples" / "s4.json").read_text(encoding="utf-8"))
    owned_ids = []
    saved = []

    def new_payload(label, template=original):
        data = json.loads(json.dumps(template))
        data["id"] = f"test-{label}-{uuid4().hex}"
        owned_ids.append(data["id"])
        return data

    try:
        with httpx.Client(base_url=BASE_URL, timeout=40, trust_env=False) as database:
            check_repository(database)
            check_references(database)
            with TestClient(api.app) as client:
                for label, count, template in (("s1", 2, original), ("three", 3, original), ("s2", 2, s2), ("s3", 3, s3), ("s4", 2, s4)):
                    payload = new_payload(label, template)
                    if label == "three":
                        payload["agents"][0]["name"] = 'Zoë "User"\n☃'
                        payload["agents"].append({
                            "id": "second-human", "name": payload["agents"][0]["name"],
                            "kind": "human", "roles": ["HumanUserRole", "ClinicianRole"],
                        })
                    response = client.post("/scenarios", json=payload)
                    assert response.status_code == 201, response.text
                    location = response.json()
                    graph = to_rdf(Scenario.model_validate(payload))
                    if label == "s2":
                        assert len(graph) == 195
                    if label == "s3":
                        assert len(graph) == 135
                    if label == "s4":
                        stored = read_graph(database, location["graph_iri"])
                        assert len(stored) == 154
                        assert set(stored) == set(graph)
                        assert len(set(stored.subjects(RDF.type, None))) == 26
                        base = f"urn:hi-app:scenario:{payload['id']}:"
                        assert set(stored.triples((None, HI.hasInteractionEpisode, None))) == {
                            (URIRef(base + "execution:explain-recommendations"), HI.hasInteractionEpisode, URIRef(base + "interaction:explain-recommendations")),
                        }
                        assert set(stored.subjects(HI.evaluatedBy, URIRef(base + "evaluation:tutor-impact"))) == {
                            URIRef(base + "execution:" + execution["id"]) for execution in payload["executions"]
                        }
                    assert isomorphic(graph, read_graph(database, location["graph_iri"]))
                    response = client.get(f"/scenarios/{payload['id']}/team")
                    assert response.status_code == 200, response.text
                    composition = response.json()
                    members = {m["iri"]: m for m in composition["members"]}
                    assert len(members) == count
                    for agent in payload["agents"]:
                        member = members[f"urn:hi-app:scenario:{payload['id']}:agent:{agent['id']}"]
                        assert member["name"] == agent["name"]
                        assert {r["iri"].rsplit("/", 1)[1] for r in member["roles"]} == set(agent["roles"])
                        assert all(r["label"] and r["definition"] for r in member["roles"])
                        assert all(t["label"] for t in member["types"])
                    changed = {**payload, "use_case": {**payload["use_case"], "name": "Rejected replacement"}}
                    duplicate = client.post("/scenarios", json=changed)
                    assert duplicate.status_code == 409
                    assert isomorphic(graph, read_graph(database, location["graph_iri"]))
                    saved.append((payload, graph, composition))
                    print(f"Saved and retrieved {label} {count}-agent scenario: {payload['id']}")

                race = new_payload("concurrent")
                variants = [
                    {**race, "use_case": {**race["use_case"], "name": f"Concurrent submission {index}"}}
                    for index in range(2)
                ]
                with ThreadPoolExecutor(max_workers=2) as pool:
                    responses = list(pool.map(lambda data: client.post("/scenarios", json=data), variants))
                assert sorted(r.status_code for r in responses) == [201, 409]
                winner = variants[next(i for i, r in enumerate(responses) if r.status_code == 201)]
                assert isomorphic(to_rdf(Scenario.model_validate(winner)), read_graph(database, scenario_graph_iri(race["id"])))
                print("Concurrent save: one created, one conflict; no merged or replaced RDF")

                missing = client.get(f"/scenarios/test-missing-{uuid4().hex}/team")
                assert missing.status_code == 404

            subprocess.run(
                ["docker", "compose", "-f", str(ROOT / "compose.yaml"), "restart", "graphdb"],
                cwd=ROOT, check=True, timeout=90,
            )
            wait_for_server(database)
            # Fresh backend clients after restart; no re-import or resave.
            with TestClient(api.app) as client:
                for payload, graph, composition in saved:
                    assert isomorphic(graph, read_graph(database, scenario_graph_iri(payload["id"])))
                    response = client.get(f"/scenarios/{payload['id']}/team")
                    assert response.status_code == 200
                    assert response.json() == composition
                check_references(database)
                print("API-saved RDF and CQ1 results survived GraphDB restart")

                # A bound but non-listening port deterministically refuses connections.
                with socket.socket() as unavailable:
                    unavailable.bind(("127.0.0.1", 0))
                    with monkeypatch.context() as settings:
                        settings.setenv("GRAPHDB_URL", f"http://127.0.0.1:{unavailable.getsockname()[1]}")
                        settings.setenv("GRAPHDB_TIMEOUT_SECONDS", "0.2")
                        assert client.get(f"/scenarios/{saved[0][0]['id']}/team").status_code == 503
                        assert client.post("/scenarios", json=new_payload("offline")).status_code == 503
                        assert client.post("/scenarios/preview", json=original).status_code == 200
                print("Real connection failure returns 503; preview remains available")
    finally:
        with httpx.Client(base_url=BASE_URL, timeout=40, trust_env=False) as database:
            for scenario_id in owned_ids:
                iri = scenario_graph_iri(scenario_id)
                database.delete("/repositories/hi/statements", params={"context": f"<{iri}>"}).raise_for_status()
                assert len(read_graph(database, iri)) == 0
