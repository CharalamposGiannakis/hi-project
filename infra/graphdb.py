"""Set up and verify the local Compose GraphDB; no application persistence API."""

import argparse
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
from rdflib import Graph
from rdflib.compare import isomorphic

from hi_scenario.model import Scenario
from hi_scenario.graphdb import HINT_GRAPH, ONTOLOGY_GRAPH, scenario_graph_iri
from hi_scenario.rdf import to_ntriples, to_rdf
from hi_scenario.validation import validate_rdf


ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "http://127.0.0.1:7200"
REPOSITORY = "hi"
ENDPOINT = f"/repositories/{REPOSITORY}"
REFERENCES = (
    (ROOT / "ontology" / "hi-ontology.ttl", ONTOLOGY_GRAPH),
    (ROOT / "ontology" / "hi-thesaurus.ttl", HINT_GRAPH),
)


def wait_for_server(client: httpx.Client, timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = client.get("/rest/repositories", timeout=5)
            if response.status_code not in (502, 503):
                response.raise_for_status()
                return
        except httpx.TransportError:
            pass
        time.sleep(1)
    raise RuntimeError("GraphDB is not ready; check 'docker compose logs graphdb'.")


def check_repository(client: httpx.Client) -> None:
    response = client.get(f"/rest/repositories/{REPOSITORY}")
    response.raise_for_status()
    params = response.json().get("params", {})
    for name, expected in (("ruleset", "empty"), ("disableSameAs", "true")):
        actual = params.get(name, {}).get("value")
        if str(actual).lower() != expected:
            raise RuntimeError(
                f"Repository '{REPOSITORY}' must have {name}={expected}, got {actual!r}. "
                "Setup will not change an existing repository's inference configuration."
            )


def put_graph(client: httpx.Client, graph_iri: str, data: bytes, content_type: str) -> None:
    # RDF4J PUT replaces only this context; POST would duplicate parsed blank nodes.
    response = client.put(
        ENDPOINT + "/statements",
        params={"context": f"<{graph_iri}>"},
        content=data,
        headers={"Content-Type": content_type},
    )
    response.raise_for_status()


def setup_repository(client: httpx.Client) -> None:
    # Parse both inputs before modifying the database; upload the original bytes.
    references = [(path, iri, path.read_bytes()) for path, iri in REFERENCES]
    for _, _, data in references:
        Graph().parse(data=data, format="turtle")
    response = client.get(f"/rest/repositories/{REPOSITORY}")
    if response.status_code == 404:
        config = (ROOT / "infra" / "hi-repository.ttl").read_bytes()
        Graph().parse(data=config, format="turtle")
        client.post(
            "/rest/repositories", files={"config": ("hi-repository.ttl", config, "text/turtle")},
        ).raise_for_status()
    else:
        response.raise_for_status()
    check_repository(client)
    for path, iri, data in references:
        put_graph(client, iri, data, "text/turtle")
        print(f"Loaded {path.name} into <{iri}>")


def read_graph(client: httpx.Client, graph_iri: str) -> Graph:
    query = f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH <{graph_iri}> {{ ?s ?p ?o }} }}"
    response = client.post(
        ENDPOINT, data={"query": query, "infer": "false"}, headers={"Accept": "text/turtle"},
    )
    response.raise_for_status()
    return Graph().parse(data=response.content, format="turtle")


def check_references(client: httpx.Client) -> None:
    for path, iri in REFERENCES:
        expected = Graph().parse(path, format="turtle")
        stored = read_graph(client, iri)
        if not isomorphic(expected, stored):
            raise RuntimeError(f"Stored reference graph differs from {path.name}: <{iri}>")
        print(f"Verified {path.name}: {len(stored)} triples")


def verify(client: httpx.Client) -> None:
    """Store a temporary three-agent scenario, restart, query it, then clean up."""
    check_repository(client)
    check_references(client)
    payload = Scenario.model_validate_json((ROOT / "examples" / "s1.json").read_text(encoding="utf-8"))
    data = payload.model_dump(mode="json")
    data["id"] = "verification-" + uuid4().hex
    data["agents"].append({
        "id": "second-human", "name": data["agents"][0]["name"],
        "kind": "human", "roles": ["HumanUserRole", "ClinicianRole"],
    })
    scenario = Scenario.model_validate(data)
    graph = to_rdf(scenario)
    conforms, _, report = validate_rdf(graph)
    if not conforms:
        raise RuntimeError(report)
    iri = scenario_graph_iri(scenario.id)
    try:
        put_graph(client, iri, to_ntriples(graph).encode("utf-8"), "application/n-triples")
        # Re-running setup must not alter scenarios or grow reference blank nodes.
        setup_repository(client)
        if not isomorphic(graph, read_graph(client, iri)):
            raise RuntimeError("Stored scenario differs from the generated RDF.")
        subprocess.run(
            ["docker", "compose", "-f", str(ROOT / "compose.yaml"), "restart", "graphdb"],
            cwd=ROOT, check=True, timeout=90,
        )
        wait_for_server(client)
        check_repository(client)
        check_references(client)  # No setup/re-import after restart.
        if not isomorphic(graph, read_graph(client, iri)):
            raise RuntimeError("Scenario RDF did not survive the container restart.")
        query = f"""
            PREFIX hi: <https://w3id.org/hi-ontology#>
            PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
            PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
            SELECT ?agent ?name ?roleLabel WHERE {{
                GRAPH <{iri}> {{
                    ?team a hi:HITeam ; hi:hasMember ?agent .
                    ?agent rdfs:label ?name ; hi:hasRoleConcept ?role .
                }}
                GRAPH <{HINT_GRAPH}> {{ ?role skos:prefLabel ?roleLabel }}
            }}
        """
        response = client.post(
            ENDPOINT, data={"query": query, "infer": "false"},
            headers={"Accept": "application/sparql-results+json"},
        )
        response.raise_for_status()
        bindings = response.json()["results"]["bindings"]
        if len({row["agent"]["value"] for row in bindings}) != 3 or len(bindings) != 4:
            raise RuntimeError("SPARQL scenario/HINT join did not preserve all three agents and roles.")
        print(f"Verified SPARQL join and restart persistence: {len(graph)} triples, 3 distinct agents")
    finally:
        # Never clear the repository or any reference/user scenario graph.
        try:
            client.delete(ENDPOINT + "/statements", params={"context": f"<{iri}>"}).raise_for_status()
        except httpx.HTTPError as exc:
            print(f"Could not remove temporary verification graph <{iri}>: {exc}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("setup", "verify"))
    args = parser.parse_args()
    try:
        with httpx.Client(base_url=BASE_URL, timeout=40, trust_env=False) as client:
            wait_for_server(client)
            if args.command == "setup":
                setup_repository(client)
                check_references(client)
            else:
                verify(client)
    except (httpx.HTTPError, OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        parser.exit(1, f"GraphDB {args.command} failed: {exc}\n")


if __name__ == "__main__":
    main()
