import json
from collections import Counter
from pathlib import Path

import pytest
from rdflib import Dataset, Literal, URIRef
from rdflib.namespace import RDFS, SKOS

from hi_scenario.explorer_queries import ROW_LIMIT, build_explorer_query, parse_explorer_rows
from hi_scenario.graphdb import HINT_GRAPH, ONTOLOGY_GRAPH, scenario_graph_iri
from hi_scenario.model import Scenario
from hi_scenario.rdf import HI, HINT, ONTOLOGY_DIR, to_rdf


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def data():
    dataset = Dataset(default_union=True)
    dataset.graph(HINT_GRAPH).parse(ONTOLOGY_DIR / "hi-thesaurus.ttl", format="turtle")
    dataset.graph(ONTOLOGY_GRAPH).parse(ONTOLOGY_DIR / "hi-ontology.ttl", format="turtle")
    for i in range(1, 8):
        scenario = Scenario.model_validate_json((ROOT / "examples" / f"s{i}.json").read_bytes())
        graph = dataset.graph(scenario_graph_iri(scenario.id))
        graph += to_rdf(scenario)
    return dataset


def answers(data, question, *scenarios, **parameters):
    scopes = [scenario_graph_iri(scenario) for scenario in scenarios]
    query = build_explorer_query(question, scopes, parameters)
    result = json.loads(data.query(query).serialize(format="json"))
    rows, truncated = parse_explorer_rows(question, result, scopes)
    assert not truncated
    return rows


def evidence(row, label):
    return next(item["iri"] for item in row["evidence"] if item["label"] == label)


@pytest.mark.parametrize(("question", "expected"), [
    ("cq1", (2, 2, 3, 2, 2, 2, 2)),
    ("cq2", (2, 11, 6, 6, 6, 6, 6)),
    ("cq5", (2, 0, 0, 2, 4, 4, 4)),
    ("cq8", (3, 2, 3, 3, 2, 4, 4)),
    ("cq11", (3, 2, 2, 2, 2, 2, 2)),
])
def test_queries_keep_results_in_their_named_graph_on_the_canonical_corpus(data, question, expected):
    ids = [f"s{i}" for i in range(1, 8)]
    counts = Counter(row["graph_iri"] for row in answers(data, question, *ids))
    assert tuple(counts[scenario_graph_iri(scenario)] for scenario in ids) == expected


def test_cq1_keeps_same_named_members_separate_and_uses_named_reference_labels(data):
    scope = data.graph(scenario_graph_iri("s3"))
    suspect = URIRef("urn:test:unrelated-member")
    team = next(scope.objects(None, HI.hasHITeam))
    members = set(scope.objects(team, HI.hasMember))
    for member in members:
        scope.set((member, RDFS.label, Literal("Same name")))
    # Even with a union default, only asserted members in this graph appear.
    data.default_graph.add((team, HI.hasMember, suspect))
    role = next(scope.objects(None, HI.hasRoleConcept))
    scope.add((role, SKOS.prefLabel, Literal("Wrong graph label")))

    rows = answers(data, "cq1", "s3")
    assert len(rows) == 3
    assert {row["values"]["member"] for row in rows} == {"Same name"}
    assert {evidence(row, "Team member") for row in rows} == set(map(str, members))
    assert all(row["values"]["role_definition"] for row in rows)
    assert "Wrong graph label" not in {row["values"]["role"] for row in rows}


def test_cq2_requires_every_capability_on_the_same_member_in_the_same_graph(data):
    scope = data.graph(scenario_graph_iri("s1"))
    ai = URIRef("urn:hi-app:scenario:s1:agent:ai-assistant")
    task = "urn:hi-app:scenario:s1:task:data-collection"
    self_reporting = next(scope.subjects(HI.hasCapabilityConcept, HINT.SelfReportingCapability))

    # One member can sense and the other can self-report. Scope cannot join them
    # or borrow a capability assertion for the same IRI from another graph.
    data.graph(scenario_graph_iri("s2")).add((ai, HI.hasCapability, self_reporting))
    assert task not in {evidence(row, "Task") for row in answers(data, "cq2", "s1", "s2")}

    scope.add((ai, HI.hasCapability, self_reporting))
    (row,) = answers(data, "cq2", "s1", capability="SensingCapability")
    assert evidence(row, "Task") == task
    assert evidence(row, "Team member") == str(ai)
    assert evidence(row, "Capability concept") == str(HINT.SensingCapability)


def test_cq2_matches_an_equivalent_owned_capability_to_the_separate_required_record(data):
    scope = data.graph(scenario_graph_iri("s1"))
    ai = URIRef("urn:hi-app:scenario:s1:agent:ai-assistant")
    task = "urn:hi-app:scenario:s1:task:data-collection"
    required = next(scope.subjects(HI.hasCapabilityConcept, HINT.SelfReportingCapability))
    owned = URIRef("urn:test:another-self-reporting-capability")
    scope.add((ai, HI.hasCapability, owned))
    scope.add((owned, HI.hasCapabilityConcept, HINT.SelfReportingCapability))

    (row,) = answers(data, "cq2", "s1", capability="SelfReportingCapability")
    assert evidence(row, "Team member") == str(ai)
    assert evidence(row, "Task") == task
    assert evidence(row, "Member capability") == str(owned)
    assert evidence(row, "Task requirement") == str(required)
    assert not any(scope.triples((owned, HI.allowsTask, None)))


def test_cq5_uses_explicit_execution_participants_and_filters_on_asserted_methods(data):
    rows = answers(data, "cq5", "s1", "s2", task="ExplanationTask", method="PostHocExplanationMethod")
    assert {row["graph_iri"] for row in rows} == {scenario_graph_iri("s1")}
    assert {row["values"]["participant"] for row in rows} == {"AI assistant", "Human user"}
    assert all(row["values"]["interaction_description"] is None for row in rows)
    assert all(evidence(row, "Method concept") == str(HINT.PostHocExplanationMethod) for row in rows)
    assert not answers(data, "cq5", "s1", method="DataCollectionMethod")


def test_cq8_uses_evaluation_metrics_and_keeps_stated_hypotheses_when_one_is_absent(data):
    scope = data.graph(scenario_graph_iri("s7"))
    experiment = next(scope.subjects(HI.hasExperimentConcept, HINT.VirtualRealityEffectivenessExperiment))
    scope.add((experiment, HI.hasMetricTested, HINT.CO2ReductionMetric))
    scope.remove((experiment, HI.hasNullHypothesis, None))

    rows = answers(data, "cq8", "s1", "s7", goal="EnhancedVisitorGoal")
    assert {row["graph_iri"] for row in rows} == {scenario_graph_iri("s7")}
    assert len(rows) == 4
    assert str(HINT.CO2ReductionMetric) not in {evidence(row, "Metric concept") for row in rows}
    assert all(row["values"]["null_hypothesis"] is None and row["values"]["alternative_hypothesis"] for row in rows)


def test_cq11_does_not_treat_operates_in_context_as_asserted_influence(data):
    initial = answers(data, "cq11", "s6")
    assert len(initial) == 2
    assert {row["values"]["context"] for row in initial} == {"Smart Campus Context"}
    scope = data.graph(scenario_graph_iri("s6"))
    scope.remove((None, HI.hasInfluenceOn, None))
    assert any(scope.triples((None, HI.operatesInContext, None)))
    assert not answers(data, "cq11", "s6")


def test_query_requires_explicit_safe_scope_and_parameters():
    with pytest.raises(ValueError):
        build_explorer_query("cq1", [], {})
    with pytest.raises(ValueError):
        build_explorer_query("cq1", ["urn:test:bad scope"], {})
    with pytest.raises(ValueError):
        build_explorer_query("cq2", ["urn:test:scope"], {"capability": "Bad Capability"})


def test_parser_checks_scope_and_binding_types_and_reports_truncation():
    graph = "urn:test:scope"
    row = {"graph": {"type": "uri", "value": graph},
           "member_iri": {"type": "uri", "value": "urn:test:member"},
           "member": {"type": "literal", "value": "Recorded name"}}
    result = {"results": {"bindings": [row] * (ROW_LIMIT + 1)}}
    rows, truncated = parse_explorer_rows("cq1", result, [graph])
    assert len(rows) == ROW_LIMIT and truncated
    assert rows[0]["values"] == {"member": "Recorded name", "agent_type": None, "role": None, "role_definition": None}

    result["results"]["bindings"][-1] = {**row, "graph": {"type": "uri", "value": "urn:test:wrong-scope"}}
    with pytest.raises(ValueError, match="outside the selection"):
        parse_explorer_rows("cq1", result, [graph])
    result["results"]["bindings"] = [{**row, "member_iri": {"type": "literal", "value": "Not an IRI"}}]
    with pytest.raises(ValueError, match="binding type"):
        parse_explorer_rows("cq1", result, [graph])
