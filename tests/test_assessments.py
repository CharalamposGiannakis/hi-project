import json
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, RDFS, XSD

from hi_scenario.api import app
from hi_scenario.model import Scenario
from hi_scenario.rdf import HI, HINT, ONTOLOGY_DIR, to_ntriples, to_rdf
from hi_scenario.validation import validate_rdf


ROOT = Path(__file__).resolve().parent.parent
BASE = "urn:hi-app:scenario:s1:"


@pytest.fixture
def payload():
    return json.loads((ROOT / "examples" / "s1.json").read_text(encoding="utf-8"))


def test_s1_adds_exactly_thirty_three_original_assessment_triples(payload):
    source = Graph().parse(ONTOLOGY_DIR / "scenarios_kgs.ttl", format="turtle")
    s1 = "https://w3id.org/hi-ontology/scenarios/1/"
    identities = {
        URIRef(s1 + original): URIRef(BASE + application)
        for original, application in {
            "ExperimentDataCollectionQuality": "experiment:data-collection-quality",
            "ExperimentConflictAccuracy": "experiment:conflict-accuracy",
            "ExperimentTransparencyTrust": "experiment:transparency-trust",
            "EvaluationDataCollectionQuality": "evaluation:data-collection-quality",
            "EvaluationConflictAccuracy": "evaluation:conflict-accuracy",
            "EvaluationTransparencyImpact": "evaluation:transparency-impact",
            "ExecutionDataCollection": "execution:data-collection",
            "ExecutionConflictResolution": "execution:conflict-resolution",
            "ExecutionExplanation": "execution:explanation",
        }.items()
    }
    nodes = {s for kind in (HI.Experiment, HI.Evaluation) for s in source.subjects(RDF.type, kind) if s in identities}
    expected = {(identities.get(s, s), p, identities.get(o, o)) for s, p, o in source if s in nodes or (p == HI.evaluatedBy and o in nodes)}
    graph = to_rdf(Scenario.model_validate(payload))
    payload.pop("experiments")
    payload.pop("evaluations")
    legacy = to_rdf(Scenario.model_validate(payload))
    assert len(expected) == 33 and len(graph) == 117
    assert set(graph) - set(legacy) == expected and set(legacy) <= set(graph)
    assert all(value.language is None and value.datatype is None for value in graph.objects(None, HI.hasNullHypothesis))
    assert not list(graph.triples((None, HI.hasInteractionEpisode, None)))
    conforms, _, report = validate_rdf(graph)
    assert conforms, report


def research_projection(payload, number):
    """Use a valid execution scaffold; compare only the original assessment RDF."""
    source = Graph().parse(ONTOLOGY_DIR / "scenarios_kgs.ttl", format="turtle")
    namespace = f"https://w3id.org/hi-ontology/scenarios/{number}/"
    experiments = sorted(s for s in source.subjects(RDF.type, HI.Experiment) if str(s).startswith(namespace))
    evaluations = sorted(s for s in source.subjects(RDF.type, HI.Evaluation) if str(s).startswith(namespace))
    executions = sorted({s for e in evaluations for s in source.subjects(HI.evaluatedBy, e)})
    payload["id"] = f"source-s{number}"
    identities = {}
    for kind, nodes in (("experiment", experiments), ("evaluation", evaluations), ("execution", executions)):
        for node in nodes:
            identities[node] = URIRef(f"urn:hi-app:scenario:{payload['id']}:{kind}:{str(node).removeprefix(namespace).lower()}")
    local_id = lambda node: str(node).removeprefix(namespace).lower()
    concept = lambda node, predicate: str(source.value(node, predicate)).removeprefix(str(HINT))
    metrics = lambda node, predicate: sorted(str(value).removeprefix(str(HINT)) for value in source.objects(node, predicate))
    scaffold = payload["executions"][0]
    payload["executions"] = [{**scaffold, "id": local_id(node)} for node in executions]
    payload["experiments"] = []
    for node in experiments:
        null = source.value(node, HI.hasNullHypothesis)
        alternative = source.value(node, HI.hasAlternativeHypothesis)
        assert isinstance(null, Literal) and isinstance(alternative, Literal)
        assert null.language == alternative.language and null.language in (None, "en")
        payload["experiments"].append({
            "id": local_id(node), "concept": concept(node, HI.hasExperimentConcept),
            "metrics": metrics(node, HI.hasMetricTested), "null_hypothesis": str(null), "alternative_hypothesis": str(alternative),
            **({"hypothesis_language": null.language} if null.language else {}),
        })
    payload["evaluations"] = [{
        "id": local_id(node), "concept": concept(node, HI.hasEvaluationConcept),
        "metrics": metrics(node, HI.hasMetricConcept), "experiment": local_id(source.value(node, HI.hasExperiment)),
        "executions": sorted(local_id(s) for s in source.subjects(HI.evaluatedBy, node)),
    } for node in evaluations]
    for node, record in zip(experiments + evaluations, payload["experiments"] + payload["evaluations"]):
        comment = source.value(node, RDFS.comment)
        if comment is not None:
            assert comment.language == "en"
            record["description"] = str(comment)
    nodes = set(experiments + evaluations)
    expected = {(identities.get(s, s), p, identities.get(o, o)) for s, p, o in source if s in nodes or (p == HI.evaluatedBy and o in nodes)}
    return payload, expected


@pytest.mark.parametrize("number", [2, 3, 4, 6, 7])
def test_original_s2_to_s7_assessment_patterns_round_trip(payload, number):
    data, expected = research_projection(payload, number)
    scenario = Scenario.model_validate(data)
    assert Scenario.model_validate_json(scenario.model_dump_json()) == scenario
    graph = to_rdf(scenario)
    legacy = scenario.model_copy(update={"experiments": (), "evaluations": ()})
    assert set(graph) - set(to_rdf(legacy)) == expected
    if number == 3:
        assert len(scenario.evaluations) == 1 and len(scenario.evaluations[0].executions) == 5
        assert len(scenario.evaluations[0].metrics) == len(scenario.experiments[0].metrics) == 3
    if number == 6:
        assert scenario.evaluations[0].concept == "NegotationImpactEvaluation"  # Actual HINT spelling.
    if number in (3, 4, 7):
        assert all(value.language == "en" for value in graph.objects(None, HI.hasNullHypothesis))


@pytest.mark.parametrize("index", [0, 1])
def test_s5_metric_concepts_used_as_evaluations_are_rejected(payload, index):
    data, _ = research_projection(payload, 5)
    data["evaluations"] = [data["evaluations"][index]]
    with pytest.raises(ValueError, match="not a Evaluation concept"):
        to_rdf(Scenario.model_validate(data))


def test_s5_experiments_reproduce_hypotheses_and_descriptions_without_invalid_evaluations(payload):
    data, expected = research_projection(payload, 5)
    data["evaluations"] = []
    scenario = Scenario.model_validate(data)
    graph = to_rdf(scenario)
    experiment_nodes = set(graph.subjects(RDF.type, HI.Experiment))
    assert len(experiment_nodes) == 2
    expected = {triple for triple in expected if triple[0] in experiment_nodes}
    legacy = scenario.model_copy(update={"experiments": ()})
    assert len(expected) == 12 and set(graph) - set(to_rdf(legacy)) == expected


def test_language_tagged_source_hypotheses_are_preserved_despite_declared_range(payload):
    ontology = Graph().parse(ONTOLOGY_DIR / "hi-ontology.ttl", format="turtle")
    assert (HI.hasNullHypothesis, RDFS.range, XSD.string) in ontology
    data, _ = research_projection(payload, 3)
    graph = to_rdf(Scenario.model_validate(data))
    assert next(graph.objects(None, HI.hasNullHypothesis)).language == "en"


def test_optional_collections_descriptions_and_stable_order(payload):
    scenario = Scenario.model_validate(payload)
    original = to_rdf(scenario)
    assert Scenario.model_validate_json(scenario.model_dump_json()) == scenario
    payload["experiments"].reverse()
    payload["evaluations"].reverse()
    for e in payload["evaluations"]:
        e["metrics"].reverse()
        e["executions"].reverse()
    assert to_ntriples(to_rdf(Scenario.model_validate(payload))) == to_ntriples(original)
    assert set(Graph().parse(data=to_ntriples(original), format="nt")) == set(original)
    payload["experiments"][0]["description"] = "Optional experiment description."
    payload["evaluations"][0].pop("description")
    payload["experiments"][0]["hypothesis_language"] = "en"
    changed = to_rdf(Scenario.model_validate(payload))
    assert set(changed.subjects(RDF.type, HI.Experiment)) == set(original.subjects(RDF.type, HI.Experiment))
    assert set(changed.subjects(RDF.type, HI.Evaluation)) == set(original.subjects(RDF.type, HI.Evaluation))
    assert Literal("Optional experiment description.", lang="en") in set(changed.objects(None, RDFS.comment))
    payload["experiments"] = []
    payload["evaluations"] = []
    assert len(to_rdf(Scenario.model_validate(payload))) == 84
    del payload["experiments"], payload["evaluations"]
    assert len(to_rdf(Scenario.model_validate(payload))) == 84


@pytest.mark.parametrize(("collection", "field", "value", "code"), [
    ("experiments", "id", "conflict-accuracy", "invalid_request"),
    ("evaluations", "id", "conflict-accuracy", "invalid_request"),
    ("evaluations", "experiment", "missing", "invalid_request"),
    ("evaluations", "executions", ["missing"], "invalid_request"),
    ("experiments", "concept", "MadeUpExperiment", "invalid_vocabulary"),
    ("experiments", "concept", "TransparencyEvaluation", "invalid_vocabulary"),
    ("evaluations", "concept", "MadeUpEvaluation", "invalid_vocabulary"),
    ("evaluations", "concept", "DiagnosisAccuracyMetric", "invalid_vocabulary"),
    ("experiments", "metrics", ["MadeUpMetric"], "invalid_vocabulary"),
    ("evaluations", "metrics", ["TransparencyEvaluation"], "invalid_vocabulary"),
    ("experiments", "null_hypothesis", "  ", "invalid_request"),
    ("experiments", "alternative_hypothesis", 12, "invalid_request"),
    ("experiments", "hypothesis_language", "fr", "invalid_request"),
    ("evaluations", "description", " ", "invalid_request"),
])
@pytest.mark.parametrize("endpoint", ["/scenarios/preview", "/scenarios"])
def test_assessment_validation_returns_422_before_storage(payload, collection, field, value, code, endpoint):
    payload[collection][0][field] = value
    with TestClient(app) as client:
        response = client.post(endpoint, json=payload)
    assert response.status_code == 422 and response.json()["code"] == code


@pytest.mark.parametrize(("field", "value"), [
    ("experiments", None), ("evaluations", {}),
    ("experiments", [{}]), ("evaluations", [{}]),
])
def test_invalid_collection_structure(payload, field, value):
    payload[field] = value
    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)


def test_deleting_referenced_records_is_rejected_without_changing_evaluation_data(payload):
    original = deepcopy(payload["evaluations"])
    for field in ("experiments", "executions"):
        invalid = deepcopy(payload)
        invalid[field].pop(0)
        with pytest.raises(ValidationError, match="references unknown"):
            Scenario.model_validate(invalid)
        assert invalid["evaluations"] == original
