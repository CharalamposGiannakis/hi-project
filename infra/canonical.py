"""Plan, import, or verify the curated S1-S7 corpus in local GraphDB only."""

import argparse
from dataclasses import dataclass
from pathlib import Path

import httpx
from pydantic import ValidationError
from rdflib import Graph
from rdflib.compare import isomorphic
from rdflib.namespace import RDF, RDFS, SKOS

from hi_scenario.graphdb import (
    GraphDBError, GraphDBSettings, GraphDBStore, HINT_GRAPH, ONTOLOGY_GRAPH, scenario_graph_iri,
)
from hi_scenario.model import Scenario
from hi_scenario.rdf import HI, to_rdf
from hi_scenario.validation import validate_rdf
from infra.graphdb import REFERENCES, ROOT, check_repository, read_graph


INVENTORY = (("s1", 127), ("s2", 195), ("s3", 135), ("s4", 154),
             ("s5", 139), ("s6", 150), ("s7", 173))
MISSING = "missing"
IDENTICAL = "present and identical"
CONFLICT = "present but conflicting"
INVALID = "invalid canonical input"
UNAVAILABLE = "repository unavailable or incorrectly configured"


@dataclass
class Entry:
    id: str
    count: int
    scenario: Scenario | None = None
    graph: Graph | None = None
    state: str = INVALID
    detail: str = ""

    @property
    def iri(self) -> str:
        return scenario_graph_iri(self.id)


def load_corpus(root: Path = ROOT) -> list[Entry]:
    """Validate every fixed input before connecting or attempting a write."""
    entries = []
    for scenario_id, count in INVENTORY:
        entry = Entry(scenario_id, count)
        entries.append(entry)
        try:
            scenario = Scenario.model_validate_json(
                (root / "examples" / f"{scenario_id}.json").read_text(encoding="utf-8"),
            )
            if scenario.id != scenario_id:
                raise ValueError(f"Scenario ID must match filename: {scenario_id}")
            graph = to_rdf(scenario)  # Includes strict HINT category checks.
            conforms, _, report = validate_rdf(graph)
            if not conforms:
                raise ValueError(f"SHACL validation failed: {report}")
            if len(graph) != count:
                raise ValueError(f"Expected {count} triples, generated {len(graph)}")
            entry.scenario, entry.graph = scenario, graph
            entry.state = "validated"
        except (OSError, ValueError) as exc:
            entry.detail = str(exc)
    return entries


def local_settings() -> GraphDBSettings:
    try:
        settings = GraphDBSettings.from_env()
    except ValidationError as exc:
        # Do not echo invalid environment values (which could include credentials).
        raise ValueError("Invalid GraphDB connection settings; use the local development repository.") from exc
    # No remote override, URL prefixes, credentials, proxy, or redirect following.
    # The operator must use the development Compose service, not an SSH tunnel.
    if str(settings.url) not in ("http://127.0.0.1:7200/", "http://localhost:7200/") or settings.repository != "hi":
        raise ValueError("Canonical import requires local http://127.0.0.1:7200 and repository hi; remote targets are refused.")
    return settings


def check_environment(client: httpx.Client) -> dict[str, Graph]:
    check_repository(client)  # Require empty ruleset and disabled sameAs optimization.
    references = {}
    failed = False
    for path, iri in REFERENCES:
        try:
            expected = Graph().parse(path, format="turtle")
            stored = read_graph(client, iri)
            if not isomorphic(expected, stored):
                raise ValueError("missing or different from the checked-in reference")
            references[iri] = expected
            print(f"Reference <{iri}>: identical ({len(stored)} triples)")
        except (httpx.HTTPError, OSError, ValueError, SyntaxError) as exc:
            failed = True
            print(f"Reference <{iri}>: FAILED ({exc})")
    if failed:
        raise ValueError("Reference verification failed; no reference graphs were changed. Check local setup.")
    return references


def _label(graph: Graph, node, predicate) -> str | None:
    return min((str(value) for value in graph.objects(node, predicate)
                if not value.language or value.language.lower().split("-")[0] == "en"), default=None)


def verify_team(entry: Entry, store: GraphDBStore, references: dict[str, Graph]) -> None:
    """Compare real CQ1 with canonical identities and reference labels, not row counts."""
    graph = entry.graph
    use_case = next(graph.subjects(RDF.type, HI.UseCase))
    team = graph.value(use_case, HI.hasHITeam)
    expected = []
    for agent in sorted(graph.objects(team, HI.hasMember)):
        expected.append({
            "iri": str(agent), "name": str(graph.value(agent, RDFS.label)),
            "types": [{"iri": str(kind), "label": _label(references[ONTOLOGY_GRAPH], kind, RDFS.label)}
                      for kind in sorted(graph.objects(agent, RDF.type))],
            "roles": [{"iri": str(role), "label": _label(references[HINT_GRAPH], role, SKOS.prefLabel),
                       "definition": _label(references[HINT_GRAPH], role, SKOS.definition)}
                      for role in sorted(graph.objects(agent, HI.hasRoleConcept))],
        })
    actual = store.team(entry.id)  # Existing CQ1 SPARQL, explicit graphs, infer=false.
    if (actual["scenario_id"] != entry.id or actual["use_case_iri"] != str(use_case)
            or actual["team_iri"] != str(team) or actual["use_case_name"] != str(graph.value(use_case, RDFS.label))
            or actual["members"] != expected):
        raise ValueError("CQ1 team identities, names, types, roles, or reference labels differ")


def inspect_entry(entry: Entry, store: GraphDBStore, references: dict[str, Graph], *, verify: bool) -> None:
    if entry.graph is None:
        return
    try:
        stored = read_graph(store.client, entry.iri)
        if not stored:
            entry.state, entry.detail = MISSING, ""
        elif len(stored) != entry.count or not isomorphic(entry.graph, stored):
            entry.state, entry.detail = CONFLICT, f"stored {len(stored)}, expected {entry.count} triples; full RDF differs"
        else:
            entry.state, entry.detail = IDENTICAL, f"{len(stored)} triples"
            if verify:
                if set(stored.triples((None, RDF.type, None))) != set(entry.graph.triples((None, RDF.type, None))):
                    raise ValueError("Scenario entity identities or RDF types differ")
                conforms, _, report = validate_rdf(stored)
                if not conforms:
                    raise ValueError(f"Stored RDF failed SHACL: {report}")
                verify_team(entry, store, references)
                entry.detail += "; identities, SHACL, CQ1 verified"
    except (httpx.HTTPError, GraphDBError) as exc:
        entry.state, entry.detail = UNAVAILABLE, str(exc)
    except (ValueError, SyntaxError) as exc:
        entry.state, entry.detail = CONFLICT, str(exc)


def summary(entries: list[Entry]) -> None:
    for entry in entries:
        print(f"{entry.id.upper()} <{entry.iri}>: {entry.state}" + (f"; {entry.detail}" if entry.detail else ""))


def run(command: str, store: GraphDBStore, entries: list[Entry]) -> int:
    print(f"Local target: {store.settings.url} repository hi; operation: {command}")
    created = []
    try:
        references = check_environment(store.client)
    except (httpx.HTTPError, OSError, RuntimeError, ValueError, SyntaxError) as exc:
        for entry in entries:
            if entry.graph is not None:
                entry.state, entry.detail = UNAVAILABLE, str(exc)
        summary(entries)
        print("No writes attempted.")
        return 1

    for entry in entries:
        inspect_entry(entry, store, references, verify=command == "verify")
    summary(entries)
    if any(entry.state not in (MISSING, IDENTICAL) for entry in entries):
        print("Preflight failed. No writes attempted.")
        return 1
    if command != "apply":
        return int(command == "verify" and any(entry.state == MISSING for entry in entries))

    # All seven inputs, references, settings, and target graphs were checked above.
    # Sole-writer operation: the adapter lock does not span CLI/API processes.
    for entry in entries:
        if entry.state != MISSING:
            continue
        try:
            store.save(entry.id, entry.graph)  # Guarded INSERT only; never PUT/DELETE.
            created.append(entry.iri)
        except (httpx.HTTPError, GraphDBError, KeyboardInterrupt) as exc:
            print(f"Apply stopped at <{entry.iri}>: {exc}")
            print(f"Save outcome for <{entry.iri}> may be uncertain; inspect it with plan/verify before resuming.")
            print("Created this run (confirmed save responses): " + (", ".join(created) or "none"))
            print("No rollback or deletion was attempted. Re-run plan, then apply to resume safely.")
            return 1
    print("Created this run (confirmed save responses): " + (", ".join(created) or "none"))
    # Verify even graphs that were already present; never repair a mismatch by replacing RDF.
    for entry in entries:
        inspect_entry(entry, store, references, verify=True)
    summary(entries)
    try:
        check_environment(store.client)
    except (httpx.HTTPError, OSError, RuntimeError, ValueError, SyntaxError) as exc:
        print(f"Post-import reference verification failed: {exc}")
        return 1
    return int(any(entry.state != IDENTICAL for entry in entries))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("plan", "apply", "verify"))
    args = parser.parse_args(argv)
    try:
        settings = local_settings()
        entries = load_corpus()
        with httpx.Client(base_url=str(settings.url), timeout=settings.timeout_seconds,
                          trust_env=False, follow_redirects=False) as client:
            return run(args.command, GraphDBStore(client, settings), entries)
    except (httpx.HTTPError, OSError, ValueError) as exc:
        print(f"Canonical {args.command} failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
