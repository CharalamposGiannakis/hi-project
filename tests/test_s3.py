import json
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS

from hi_scenario.api import app
from hi_scenario.model import Scenario
from hi_scenario.rdf import HI, HINT, ONTOLOGY_DIR, to_ntriples, to_rdf
from hi_scenario.validation import validate_rdf


BASE = "urn:hi-app:scenario:s3:"


@pytest.fixture
def payload():
    return json.loads((Path(__file__).resolve().parent.parent / "examples" / "s3.json").read_text(encoding="utf-8"))


def test_complete_s3_preserves_source_with_only_the_provisional_concept_alignment_and_entailed_inverse(payload):
    graph = to_rdf(Scenario.model_validate(payload))
    source = Graph().parse(ONTOLOGY_DIR / "scenarios_kgs.ttl", format="turtle")
    s3 = Namespace("https://w3id.org/hi-ontology/scenarios/3/")
    identities = {
        s3[original]: URIRef(BASE + application)
        for original, application in {
            "UseCaseGroupDeliberationHI": "use-case:group-deliberation",
            "HITeamGroupDeliberation": "team",
            "GoalFairAccurateVerdict": "goal:fair-accurate-verdict",
            "ContextJuryDeliberation": "context",
            "AIDeliberationAssistant": "agent:ai-deliberation-assistant",
            "HumanJuror1": "agent:human-juror-1",
            "HumanJuror2": "agent:human-juror-2",
            "TaskAssessCommunicationAccuracy": "task:assess-communication-accuracy",
            "TaskDecideIntervention": "task:decide-intervention",
            "TaskExplainDecision": "task:explain-decision",
            "TaskProvideStatement": "task:provide-statement",
            "CapabilityBayesianReasoning": "capability:bayesian-reasoning",
            "CapabilityMetaAnalysis": "capability:meta-analysis",
            "CapabilityExplanation": "capability:explaining",
            "CapabilitySelfReporting": "capability:self-reporting",
            "ExecAssessAccuracy": "execution:assess-accuracy",
            "ExecDecideIntervention": "execution:decide-intervention",
            "ExecExplainDecision": "execution:explain-decision",
            "ExecProvideStatement1": "execution:provide-statement-1",
            "ExecProvideStatement2": "execution:provide-statement-2",
            "InteractionGroupDeliberation": "interaction:group-deliberation",
            "InteractionExplainConditions": "interaction:explain-conditions",
            "ExperimentDeliberationSupport": "experiment:deliberation-support",
            "EvaluationAIInterventionImpact": "evaluation:ai-intervention-impact",
        }.items()
    }

    def is_s3(term):
        return isinstance(term, URIRef) and str(term).startswith(str(s3))

    original = {(s, p, o) for s, p, o in source if is_s3(s) or is_s3(o)}
    assert len(original) == 125
    entities = {term for s, _, o in original for term in (s, o) if is_s3(term)}
    assert len(identities) == len(set(identities.values())) == 24
    assert set(identities) == entities
    assert set(identities.values()) == set(graph.subjects())
    for original_node, application_node in identities.items():
        assert set(source.objects(original_node, RDF.type)) == set(graph.objects(application_node, RDF.type))
    assert Counter(graph.objects(None, RDF.type)) == {
        HI.UseCase: 1, HI.HITeam: 1, HI.Goal: 1, HI.Context: 1,
        HI.HumanAgent: 2, HI.ArtificialAgent: 1, HI.Task: 4, HI.Capability: 4,
        HI.TaskExecution: 5, HI.Evaluation: 1, HI.Experiment: 1, HI.Interaction: 2,
    }
    mapped = {(identities.get(s, s), p, identities.get(o, o)) for s, p, o in original}

    # This is a provisional project assumption, not an equivalence between these IRIs.
    undefined = HINT.AssessCommunicationAccuracyTask
    defined = HINT.AssessCommunicationAccuracy
    vocabulary = Graph().parse(ONTOLOGY_DIR / "hi-thesaurus.ttl", format="turtle")
    assert not any(undefined in triple for triple in vocabulary), "Review the provisional S3 concept alignment: the source IRI now occurs in HINT"
    assert (defined, RDF.type, SKOS.Concept) in vocabulary
    assert (defined, SKOS.broader, HINT.Task) in vocabulary
    assert (defined, SKOS.prefLabel, Literal("Assess Communication Accuracy Task", lang="en")) in vocabulary
    assert (defined, SKOS.definition, Literal("A task that involves assessing the accuracy of communication between agents.", lang="en")) in vocabulary
    task = identities[s3.TaskAssessCommunicationAccuracy]
    missing = (task, HI.hasTaskConcept, undefined)
    replacement = (task, HI.hasTaskConcept, defined)
    assert missing in mapped and replacement not in mapped
    assert mapped - set(graph) == {missing}
    assert len(mapped & set(graph)) == 124

    ontology = Graph().parse(ONTOLOGY_DIR / "hi-ontology.ttl", format="turtle")
    assert (HI.requiresCapability, OWL.inverseOf, HI.allowsTask) in ontology
    assert (s3.CapabilityMetaAnalysis, HI.allowsTask, s3.TaskAssessCommunicationAccuracy) in original
    entailed_inverse = (task, HI.requiresCapability, identities[s3.CapabilityMetaAnalysis])
    assert entailed_inverse not in mapped
    labels = {
        (URIRef(BASE + entity), RDFS.label, Literal(name))
        for entity, name in {
            "use-case:group-deliberation": "Group deliberation",
            "goal:fair-accurate-verdict": "Fair and accurate verdict",
            "agent:ai-deliberation-assistant": "AI deliberation assistant",
            "agent:human-juror-1": "Human juror 1",
            "agent:human-juror-2": "Human juror 2",
            "task:assess-communication-accuracy": "Assess communication accuracy",
            "task:decide-intervention": "Decide intervention",
            "task:explain-decision": "Explain decision",
            "task:provide-statement": "Provide statement",
        }.items()
    }
    assert len(labels) == 9
    assert set(graph) - mapped == labels | {replacement, entailed_inverse}
    assert len(graph) == 135
    before = set(graph)
    conforms, _, report = validate_rdf(graph)
    assert conforms, report
    assert set(graph) == before


def test_s3_distinct_jurors_shared_capability_evaluation_hypotheses_and_preview(payload):
    scenario = Scenario.model_validate(payload)
    assert Scenario.model_validate_json(scenario.model_dump_json()) == scenario
    graph = to_rdf(scenario)
    jurors = {URIRef(BASE + "agent:human-juror-1"), URIRef(BASE + "agent:human-juror-2")}
    assert set(graph.subjects(RDF.type, HI.HumanAgent)) == jurors
    assert set(graph.subjects(HI.hasCapability, URIRef(BASE + "capability:self-reporting"))) == jurors
    statements = {URIRef(BASE + "execution:provide-statement-1"), URIRef(BASE + "execution:provide-statement-2")}
    assert set(graph.subjects(HI.realizesTask, URIRef(BASE + "task:provide-statement"))) == statements
    assert {graph.value(execution, HI.performedBy) for execution in statements} == jurors
    evaluation = URIRef(BASE + "evaluation:ai-intervention-impact")
    assert set(graph.subjects(HI.evaluatedBy, evaluation)) == set(graph.subjects(RDF.type, HI.TaskExecution))
    assert len(list(graph.objects(evaluation, HI.hasMetricConcept))) == 3
    experiment = URIRef(BASE + "experiment:deliberation-support")
    assert len(list(graph.objects(experiment, HI.hasMetricTested))) == 3
    assert graph.value(experiment, HI.hasNullHypothesis) == Literal("AI intervention has no effect on fairness or may increase undue influence.", lang="en")
    assert graph.value(experiment, HI.hasAlternativeHypothesis) == Literal("AI-supported Bayesian meta-analysis improves fairness without increasing undue influence.", lang="en")
    for interaction in graph.subjects(RDF.type, HI.Interaction):
        assert set(graph.objects(interaction, HI.hasAgentInvolved)) == jurors | {URIRef(BASE + "agent:ai-deliberation-assistant")}
    assert not list(graph.triples((None, HI.hasInteractionEpisode, None)))
    with TestClient(app) as client:
        response = client.post("/scenarios/preview", json=payload)
    assert response.status_code == 200
    assert response.json()["triple_count"] == 135
    assert response.json()["validation"]["conforms"] is True
    assert set(Graph().parse(data=response.json()["rdf"], format="nt")) == set(graph)
    for collection in ("tasks", "agents", "capabilities", "executions", "evaluations", "experiments", "interactions"):
        payload[collection].reverse()
    assert to_ntriples(to_rdf(Scenario.model_validate(payload))) == to_ntriples(graph)


def test_original_undefined_s3_term_is_still_rejected_without_an_alias(payload):
    payload["tasks"][0]["concept"] = "AssessCommunicationAccuracyTask"
    with pytest.raises(ValueError, match="Unknown HINT concept: AssessCommunicationAccuracyTask"):
        to_rdf(Scenario.model_validate(payload))
    with TestClient(app) as client:
        response = client.post("/scenarios/preview", json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_vocabulary"
