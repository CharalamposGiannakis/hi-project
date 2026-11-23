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
    ("cq2", (4, 11, 6, 6, 6, 6, 8)),
    ("cq5", (2, 0, 0, 2, 4, 4, 4)),
    ("cq8", (6, 10, 6, 6, 4, 8, 8)),
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


@pytest.mark.parametrize(("scenario", "task_id", "members"), [
    ("s1", "data-collection", {"AI assistant", "Human user"}),
    ("s7", "interpret-multimodal-input", {"AI virtual guide", "Human visitor"}),
])
def test_cq2_covers_collaborative_requirements_without_execution_claims(data, scenario, task_id, members):
    scope = data.graph(scenario_graph_iri(scenario))
    # Derived coverage remains available when the scenario has no execution evidence.
    scope.remove((None, HI.realizesTask, None))
    task = f"urn:hi-app:scenario:{scenario}:task:{task_id}"
    rows = [row for row in answers(data, "cq2", scenario) if evidence(row, "Task") == task]
    assert len(rows) == 2
    assert {row["values"]["member"] for row in rows} == members
    assert {evidence(row, "Task requirement") for row in rows} == set(map(str, scope.objects(URIRef(task), HI.requiresCapability)))
    assert all(evidence(row, "HI team") == f"urn:hi-app:scenario:{scenario}:team" for row in rows)
    assert all("execution" not in row["values"] for row in rows)


def test_cq2_requires_every_capability_within_the_same_team_and_graph(data):
    scope = data.graph(scenario_graph_iri("s1"))
    ai = URIRef("urn:hi-app:scenario:s1:agent:ai-assistant")
    task = "urn:hi-app:scenario:s1:task:data-collection"
    sensing = next(scope.subjects(HI.hasCapabilityConcept, HINT.SensingCapability))

    # A missing team's capability cannot be borrowed from another graph or
    # from someone who is outside that team even within the selected graph.
    scope.remove((ai, HI.hasCapability, sensing))
    data.graph(scenario_graph_iri("s2")).add((ai, HI.hasCapability, sensing))
    scope.add((URIRef("urn:test:outside-team-agent"), HI.hasCapability, sensing))
    assert task not in {evidence(row, "Task") for row in answers(data, "cq2", "s1", "s2")}

    scope.add((ai, HI.hasCapability, sensing))
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

    rows = answers(data, "cq2", "s1", capability="SelfReportingCapability")
    (row,) = [row for row in rows if evidence(row, "Member capability") == str(owned)]
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


def test_cq8_keeps_experiment_metrics_distinct_and_hypotheses_when_one_is_absent(data):
    scope = data.graph(scenario_graph_iri("s7"))
    experiment = next(scope.subjects(HI.hasExperimentConcept, HINT.VirtualRealityEffectivenessExperiment))
    scope.add((experiment, HI.hasMetricTested, HINT.CO2ReductionMetric))
    scope.remove((experiment, HI.hasNullHypothesis, None))

    rows = answers(data, "cq8", "s1", "s7", goal="EnhancedVisitorGoal")
    assert {row["graph_iri"] for row in rows} == {scenario_graph_iri("s7")}
    assert len(rows) == 9
    (extra,) = [row for row in rows if evidence(row, "Metric concept") == str(HINT.CO2ReductionMetric)]
    assert extra["values"]["metric_source"] == "Experiment"
    assert evidence(extra, "Metric owner") == str(experiment)
    assert evidence(extra, "Metric relationship") == str(HI.hasMetricTested)
    assert all(row["values"]["null_hypothesis"] is None and row["values"]["alternative_hypothesis"] for row in rows)


@pytest.mark.parametrize("scenario", ["s2", "s5"])
def test_cq8_retrieves_every_recorded_experiment_and_each_metric_relationship(data, scenario):
    scope = data.graph(scenario_graph_iri(scenario))
    rows = answers(data, "cq8", scenario)
    recorded = {
        (str(experiment), str(owner), str(predicate), str(metric))
        for evaluation, experiment in scope.subject_objects(HI.hasExperiment)
        for owner, predicate in ((evaluation, HI.hasMetricConcept), (experiment, HI.hasMetricTested))
        for metric in scope.objects(owner, predicate)
    }
    assert {
        (evidence(row, "Experiment"), evidence(row, "Metric owner"),
         evidence(row, "Metric relationship"), evidence(row, "Metric concept"))
        for row in rows
    } == recorded
    assert {row["values"]["metric_source"] for row in rows} == {"Evaluation", "Experiment"}
    assert len(rows) == len(recorded)


def test_cq8_accepts_either_goal_path_and_excludes_unlinked_evaluations(data):
    scope = data.graph(scenario_graph_iri("s2"))
    goal = next(scope.objects(None, HI.hasGoal))
    expected = {evidence(row, "Experiment") for row in answers(data, "cq8", "s2")}
    scope.remove((goal, HI.requiresTask, None))
    assert {evidence(row, "Experiment") for row in answers(data, "cq8", "s2")} == expected
    scope.remove((None, HI.towardsGoal, goal))
    assert not answers(data, "cq8", "s2")
    # The required-task path is independently sufficient without towardsGoal.
    execution = URIRef("urn:hi-app:scenario:s2:execution:unlock-cabinet")
    scope.add((goal, HI.requiresTask, next(scope.objects(execution, HI.realizesTask))))
    assert {evidence(row, "Experiment") for row in answers(data, "cq8", "s2")} == {
        "urn:hi-app:scenario:s2:experiment:fine-manipulation",
    }


def test_cq8_retains_experiments_when_metric_information_is_missing(data):
    scope = data.graph(scenario_graph_iri("s5"))
    scope.remove((None, HI.hasMetricConcept, None))
    scope.remove((None, HI.hasMetricTested, None))
    rows = answers(data, "cq8", "s5")
    assert len(rows) == 2
    assert all(row["values"]["metric"] is None and row["values"]["metric_source"] is None for row in rows)
    assert all(row["values"]["null_hypothesis"] and row["values"]["alternative_hypothesis"] for row in rows)


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
