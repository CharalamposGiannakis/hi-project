"""Exercise recorded concept overlap and relationship evidence in actual SPARQL."""

import json
from pathlib import Path

import pytest
from rdflib import Dataset, Literal, URIRef
from rdflib.namespace import RDF, RDFS, SKOS

from hi_scenario.explorer_concepts import build_concept_query, parse_concept_rows
from hi_scenario.explorer_queries import ROW_LIMIT
from hi_scenario.graphdb import HINT_GRAPH, ONTOLOGY_GRAPH, scenario_graph_iri
from hi_scenario.model import Scenario
from hi_scenario.rdf import HI, HINT, ONTOLOGY_DIR, to_rdf


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def dataset():
    data = Dataset(default_union=True)
    data.graph(HINT_GRAPH).parse(ONTOLOGY_DIR / "hi-thesaurus.ttl", format="turtle")
    data.graph(ONTOLOGY_GRAPH).parse(ONTOLOGY_DIR / "hi-ontology.ttl", format="turtle")
    for number in range(1, 8):
        scenario = Scenario.model_validate_json((ROOT / "examples" / f"s{number}.json").read_bytes())
        graph = data.graph(scenario_graph_iri(scenario.id))
        graph += to_rdf(scenario)
    return data


def query(data, category, concept=None, scenarios=tuple(f"s{i}" for i in range(1, 8)), comparison=False):
    scopes = [scenario_graph_iri(scenario) for scenario in scenarios]
    text = build_concept_query(scopes, category, concept, tuple(scopes) if comparison else None)
    result = json.loads(data.query(text).serialize(format="json"))
    return parse_concept_rows(result, scopes)


def evidence(row):
    return {item["label"]: item["iri"] for item in row["evidence"]}


def test_kg_querying_search_retains_agents_and_tasks_in_five_scenarios(dataset):
    rows, truncated = query(dataset, "Capability", "KnowledgeGraphQueryingCapability")
    assert not truncated
    assert {row["graph_iri"] for row in rows} == {scenario_graph_iri(f"s{i}") for i in (2, 4, 5, 6, 7)}
    assert {row["values"]["connection"] for row in rows} == {
        "Agent has capability", "Task requires capability", "Capability allows task",
    }
    assert all(evidence(row)["HINT concept"] == str(HINT.KnowledgeGraphQueryingCapability) for row in rows)
    assert all(evidence(row)["Concept relationship"] == str(HI.hasCapabilityConcept) for row in rows)
    assert any(row["values"]["related"] == "AI diagnostic assistant" for row in rows)
    assert any(row["values"]["related"] == "Symptom analysis" for row in rows)


def test_privacy_search_distinguishes_team_and_context_relationships(dataset):
    rows, truncated = query(dataset, "Constraint", "PrivacyConstraint")
    assert not truncated
    assert {row["graph_iri"] for row in rows} == {scenario_graph_iri(f"s{i}") for i in (1, 4, 5, 7)}
    assert {row["values"]["connection"] for row in rows} == {"Team constraint", "Context constraint"}
    s7 = [row for row in rows if row["graph_iri"] == scenario_graph_iri("s7")]
    assert {evidence(row)["Concept owner"] for row in s7} == {
        "urn:hi-app:scenario:s7:team", "urn:hi-app:scenario:s7:context",
    }
    assert all(row["values"]["related"] is None for row in rows)
    assert all(not row["values"]["entity"].startswith("urn:") for row in rows)
    assert all(evidence(row)["Concept relationship"] == str(HI.hasConstraintConcept) for row in rows)


def test_methods_retain_execution_task_and_performer_relationships(dataset):
    rows, truncated = query(dataset, "Method", "PostHocExplanationMethod")
    assert not truncated
    assert {evidence(row)["Connection relationship"] for row in rows} == {str(HI.realizesTask), str(HI.performedBy)}
    assert all(evidence(row)["Concept relationship"] == str(HI.hasMethodConcept) for row in rows)
    assert all(not row["values"]["entity"].startswith("urn:") for row in rows)
    assert any(row["values"]["related"] == "Human clinician" for row in rows)


def test_metrics_keep_evaluation_and_experiment_owners_and_predicates(dataset):
    rows, truncated = query(dataset, "Metric", "DiagnosisAccuracyMetric")
    assert not truncated
    assert {row["graph_iri"] for row in rows} == {scenario_graph_iri("s5")}
    assert {evidence(row)["Concept relationship"] for row in rows} == {str(HI.hasMetricConcept), str(HI.hasMetricTested)}
    assert {evidence(row)["Concept owner"] for row in rows} == {
        "urn:hi-app:scenario:s5:evaluation:diagnosis-accuracy",
        "urn:hi-app:scenario:s5:experiment:diagnosis-accuracy",
    }
    assert any(evidence(row)["Connection relationship"] == str(HI.evaluatedBy) for row in rows)
    assert all(not row["values"]["entity"].startswith("urn:") for row in rows)


def test_comparison_uses_exact_concepts_while_retaining_different_relationships(dataset):
    rows, truncated = query(dataset, None, scenarios=("s1", "s5"), comparison=True)
    assert not truncated
    assert {row["values"]["overlap"] for row in rows} == {
        "Recorded in both", "Recorded only in draft", "Recorded only in shared",
    }
    for row in rows:
        concept = evidence(row)["HINT concept"]
        if concept in {str(HINT.PrivacyConstraint), str(HINT.ExplainingCapability), str(HINT.PostHocExplanationMethod)}:
            assert row["values"]["overlap"] == "Recorded in both"
        if concept == str(HINT.SensingCapability):
            assert row["values"]["overlap"] == "Recorded only in draft"
        if concept == str(HINT.ClinicalJudgmentCapability):
            assert row["values"]["overlap"] == "Recorded only in shared"
    explaining = [row for row in rows if evidence(row)["HINT concept"] == str(HINT.ExplainingCapability)]
    assert any(row["values"]["related"] == "Human clinician" for row in explaining)
    assert all(row["values"]["related"] != "Human clinician" for row in explaining if row["graph_iri"] == scenario_graph_iri("s1"))


def test_unassociated_capability_survives_without_borrowing_other_graph_relationships(dataset):
    graph = dataset.graph(scenario_graph_iri("s2"))
    capability = next(graph.subjects(HI.hasCapabilityConcept, HINT.KnowledgeGraphQueryingCapability))
    graph.remove((None, HI.hasCapability, capability))
    graph.remove((None, HI.requiresCapability, capability))
    graph.remove((capability, HI.allowsTask, None))
    foreign_agent = URIRef("urn:test:foreign-agent")
    for other in (dataset.default_graph, dataset.graph(scenario_graph_iri("s3"))):
        other.add((foreign_agent, HI.hasCapability, capability))
        other.add((foreign_agent, RDFS.label, Literal("Private unrelated member")))
    (row,), truncated = query(dataset, "Capability", "KnowledgeGraphQueryingCapability", scenarios=("s2",))
    assert not truncated
    assert row["values"]["connection"] == "Capability concept"
    assert row["values"]["related"] is None
    assert "Related entity" not in evidence(row)


def test_same_entity_ids_in_different_graphs_do_not_merge_or_establish_overlap(dataset):
    draft = scenario_graph_iri("s1")
    shared = "urn:test:shared-copy-with-same-entity-identifiers"
    shared_graph = dataset.graph(shared)
    shared_graph += dataset.graph(draft)
    capability = next(dataset.graph(shared).subjects(HI.hasCapabilityConcept, HINT.SensingCapability))
    dataset.graph(shared).remove((capability, HI.hasCapabilityConcept, HINT.SensingCapability))
    dataset.graph(shared).add((capability, HI.hasCapabilityConcept, HINT.ClinicalJudgmentCapability))
    scopes = [draft, shared]
    text = build_concept_query(scopes, "Capability", None, tuple(scopes))
    rows, _ = parse_concept_rows(json.loads(dataset.query(text).serialize(format="json")), scopes)
    sensing = [row for row in rows if evidence(row)["HINT concept"] == str(HINT.SensingCapability)]
    clinical = [row for row in rows if evidence(row)["HINT concept"] == str(HINT.ClinicalJudgmentCapability)]
    assert sensing and clinical
    assert all(row["graph_iri"] == draft and row["values"]["overlap"] == "Recorded only in draft" for row in sensing)
    assert all(row["graph_iri"] == shared and row["values"]["overlap"] == "Recorded only in shared" for row in clinical)


def test_concept_search_uses_the_named_hint_vocabulary(dataset):
    graph = dataset.graph(scenario_graph_iri("s1"))
    capability = URIRef("urn:test:foreign-capability")
    foreign = URIRef("https://example.invalid/foreign-concept")
    graph.add((capability, RDF.type, HI.Capability))
    graph.add((capability, HI.hasCapabilityConcept, foreign))
    # A label or concept declaration in scenario data cannot add to HINT.
    graph.add((foreign, RDF.type, SKOS.Concept))
    rows, _ = query(dataset, "Capability", scenarios=("s1",))
    assert rows
    assert all(evidence(row)["HINT concept"] != str(foreign) for row in rows)


def test_comparison_checks_other_graph_before_the_display_limit(dataset):
    draft, shared = scenario_graph_iri("s1"), scenario_graph_iri("s5")
    for index in range(ROW_LIMIT + 1):
        capability = URIRef(f"urn:test:many-capabilities:{index}")
        dataset.graph(draft).add((capability, RDF.type, HI.Capability))
        dataset.graph(draft).add((capability, HI.hasCapabilityConcept, HINT.ExplainingCapability))
    rows, truncated = query(dataset, "Capability", "ExplainingCapability", scenarios=("s1", "s5"), comparison=True)
    assert truncated
    assert len(rows) == ROW_LIMIT
    assert all(row["graph_iri"] == draft for row in rows)
    assert all(row["values"]["overlap"] == "Recorded in both" for row in rows)


def test_concept_query_rejects_unsupported_categories_and_unsafe_scopes():
    with pytest.raises(ValueError):
        build_concept_query([], None, None)
    with pytest.raises(ValueError):
        build_concept_query(["urn:test:scope"], "Goal", None)
    with pytest.raises(ValueError):
        build_concept_query(["urn:test:bad scope"], None, None)
    with pytest.raises(ValueError):
        build_concept_query(["urn:test:scope"], None, "Bad Concept")
    with pytest.raises(ValueError):
        build_concept_query(["urn:test:scope"], None, None, ("urn:test:scope", "urn:test:other"))


def test_concept_parser_requires_source_local_assertion_evidence(dataset):
    scopes = [scenario_graph_iri("s1")]
    text = build_concept_query(scopes, "Capability", None)
    result = json.loads(dataset.query(text).serialize(format="json"))
    result["results"]["bindings"][0]["graph"]["value"] = "urn:test:unselected"
    with pytest.raises(ValueError, match="outside the selection"):
        parse_concept_rows(result, scopes)
    result["results"]["bindings"][0]["graph"]["value"] = scopes[0]
    del result["results"]["bindings"][0]["assertion_iri"]
    with pytest.raises(ValueError, match="requires its recorded assertion"):
        parse_concept_rows(result, scopes)
