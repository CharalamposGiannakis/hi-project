import json
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, SKOS

from hi_scenario.api import app
from hi_scenario.model import Scenario
from hi_scenario.rdf import HI, HINT, ONTOLOGY_DIR, to_ntriples, to_rdf
from hi_scenario.validation import validate_rdf


BASE = "urn:hi-app:scenario:s5:"


@pytest.fixture
def payload():
    return json.loads((Path(__file__).resolve().parent.parent / "examples" / "s5.json").read_text(encoding="utf-8"))


def test_complete_s5_has_only_the_two_provisional_replacements_omission_labels_and_conventions(payload):
    graph = to_rdf(Scenario.model_validate(payload))
    source = Graph().parse(ONTOLOGY_DIR / "scenarios_kgs.ttl", format="turtle")
    s5 = Namespace("https://w3id.org/hi-ontology/scenarios/5/")
    identities = {
        s5[original]: URIRef(BASE + application)
        for original, application in {
            "UseCaseHybridMedicalDiagnosis": "use-case:hybrid-medical-diagnosis",
            "HITeamDiagnosis": "team",
            "GoalAccurateTrustworthyDiagnosis": "goal:accurate-trustworthy-diagnosis",
            "ContextClinicalConsultation": "context",
            "AIDiagnosticAssistant": "agent:ai-diagnostic-assistant",
            "HumanClinician": "agent:human-clinician",
            "TaskSymptomAnalysis": "task:symptom-analysis",
            "TaskCandidateGeneration": "task:candidate-generation",
            "TaskHypothesisComparison": "task:hypothesis-comparison",
            "TaskExplainReasoning": "task:explain-reasoning",
            "CapabilityEmbeddingReasoning": "capability:embedding-reasoning",
            "CapabilityKGQuery": "capability:kg-query",
            "CapabilityExplanation": "capability:explaining",
            "CapabilityClinicalJudgment": "capability:clinical-judgment",
            "ExecSymptomEmbedding": "execution:symptom-embedding",
            "ExecCandidateGeneration": "execution:candidate-generation",
            "ExecHypothesisComparison": "execution:hypothesis-comparison",
            "ExecExplainAI": "execution:explain-ai",
            "ExecExplainHuman": "execution:explain-human",
            "EvalDiagnosisAccuracy": "evaluation:diagnosis-accuracy",
            "EvalExplanationClarity": "evaluation:explanation-clarity",
            "ExperimentDiagnosisAccuracy": "experiment:diagnosis-accuracy",
            "ExperimentExplanationClarity": "experiment:explanation-clarity",
            "InteractionClinicalDialogue": "interaction:clinical-dialogue",
        }.items()
    }

    def is_s5(term):
        return isinstance(term, URIRef) and str(term).startswith(str(s5))

    # Include incoming links and every predicate, including the unsupported one.
    original = {(s, p, o) for s, p, o in source if is_s5(s) or is_s5(o)}
    assert len(original) == 129
    entities = {term for s, _, o in original for term in (s, o) if is_s5(term)}
    assert len(identities) == len(set(identities.values())) == 24
    assert set(identities) == entities
    assert set(identities.values()) == set(graph.subjects())
    for original_node, application_node in identities.items():
        assert set(source.objects(original_node, RDF.type)) == set(graph.objects(application_node, RDF.type))
    assert Counter(graph.objects(None, RDF.type)) == {
        HI.UseCase: 1, HI.HITeam: 1, HI.Goal: 1, HI.Context: 1,
        HI.HumanAgent: 1, HI.ArtificialAgent: 1, HI.Task: 4, HI.Capability: 4,
        HI.TaskExecution: 5, HI.Evaluation: 2, HI.Experiment: 2, HI.Interaction: 1,
    }
    mapped = {(identities.get(s, s), p, identities.get(o, o)) for s, p, o in original}

    # Generic evaluations are provisional; the source metrics are not equivalent to them.
    vocabulary = Graph().parse(ONTOLOGY_DIR / "hi-thesaurus.ttl", format="turtle")
    assert (HINT.Evaluation, RDF.type, SKOS.Concept) in vocabulary
    replaced = set()
    replacements = set()
    for evaluation, metric in (
        (s5.EvalDiagnosisAccuracy, HINT.DiagnosisAccuracyMetric),
        (s5.EvalExplanationClarity, HINT.ExplanationClarityMetric),
    ):
        assert (evaluation, HI.hasEvaluationConcept, metric) in original
        assert (metric, RDF.type, SKOS.Concept) in vocabulary
        ancestors = set(vocabulary.transitive_objects(metric, SKOS.broader))
        assert HINT.Metric in ancestors and HINT.Evaluation not in ancestors
        replaced.add((identities[evaluation], HI.hasEvaluationConcept, metric))
        replacements.add((identities[evaluation], HI.hasEvaluationConcept, HINT.Evaluation))
    assert len(replaced) == len(replacements) == 2

    ontology = Graph().parse(ONTOLOGY_DIR / "hi-ontology.ttl", format="turtle")
    assert not any(HI.hasInteractionConcept in triple for triple in ontology), "Review the S5 omission: the predicate now occurs in the ontology"
    omission = (identities[s5.InteractionClinicalDialogue], HI.hasInteractionConcept, HINT.Interaction)
    assert omission in mapped
    # Full RDF-term comparison retains literal text, punctuation, datatype, and language.
    assert mapped - set(graph) == replaced | {omission}
    assert len(mapped & set(graph)) == 126
    labels = {
        (URIRef(BASE + entity), RDFS.label, Literal(name))
        for entity, name in {
            "use-case:hybrid-medical-diagnosis": "Hybrid medical diagnosis",
            "goal:accurate-trustworthy-diagnosis": "Accurate and trustworthy diagnosis",
            "agent:ai-diagnostic-assistant": "AI diagnostic assistant",
            "agent:human-clinician": "Human clinician",
            "task:symptom-analysis": "Symptom analysis",
            "task:candidate-generation": "Generate candidate hypotheses",
            "task:hypothesis-comparison": "Compare hypotheses",
            "task:explain-reasoning": "Explain reasoning",
        }.items()
    }
    for agent in (s5.AIDiagnosticAssistant, s5.HumanClinician):
        assert not list(source.objects(agent, HI.hasAgentConcept))
    assert not list(source.objects(s5.ContextClinicalConsultation, HI.hasInfluenceOn))
    assert not list(source.objects(s5.HITeamDiagnosis, HI.isInfluencedBy))
    # Existing application conventions, not source assertions or logical entailments.
    conventions = {
        (identities[s5.AIDiagnosticAssistant], HI.hasAgentConcept, HINT.ArtificialAgent),
        (identities[s5.HumanClinician], HI.hasAgentConcept, HINT.HumanAgent),
        (identities[s5.ContextClinicalConsultation], HI.hasInfluenceOn, identities[s5.HITeamDiagnosis]),
    }
    assert len(labels) == 8 and len(conventions) == 3
    assert not mapped & (labels | conventions | replacements)
    assert set(graph) - mapped == replacements | labels | conventions
    assert len(graph) == 139
    before = set(graph)
    conforms, _, report = validate_rdf(graph)
    assert conforms, report
    assert set(graph) == before


def test_s5_shared_capability_evaluation_groups_descriptions_hypotheses_and_preview(payload):
    scenario = Scenario.model_validate(payload)
    assert Scenario.model_validate_json(scenario.model_dump_json()) == scenario
    graph = to_rdf(scenario)
    goal = URIRef(BASE + "goal:accurate-trustworthy-diagnosis")
    assert set(graph.objects(goal, HI.requiresTask)) == set(graph.subjects(RDF.type, HI.Task))
    agents = {URIRef(BASE + "agent:ai-diagnostic-assistant"), URIRef(BASE + "agent:human-clinician")}
    assert set(graph.subjects(HI.hasCapability, URIRef(BASE + "capability:explaining"))) == agents
    explanations = {URIRef(BASE + "execution:explain-ai"), URIRef(BASE + "execution:explain-human")}
    assert set(graph.subjects(HI.realizesTask, URIRef(BASE + "task:explain-reasoning"))) == explanations
    assert {graph.value(execution, HI.performedBy) for execution in explanations} == agents
    evaluation_groups = {
        "diagnosis-accuracy": {"symptom-embedding", "candidate-generation", "hypothesis-comparison"},
        "explanation-clarity": {"explain-ai", "explain-human"},
    }
    for evaluation_id, executions in evaluation_groups.items():
        evaluation = URIRef(BASE + "evaluation:" + evaluation_id)
        assert graph.value(evaluation, HI.hasEvaluationConcept) == HINT.Evaluation
        assert graph.value(evaluation, HI.hasExperiment) == URIRef(BASE + "experiment:" + evaluation_id)
        assert set(graph.subjects(HI.evaluatedBy, evaluation)) == {URIRef(BASE + "execution:" + execution) for execution in executions}
    comments = set(graph.triples((None, RDFS.comment, None)))
    assert len(comments) == 6
    assert {s for s, _, _ in comments} == {
        URIRef(BASE + "context"), URIRef(BASE + "interaction:clinical-dialogue"),
        *(URIRef(BASE + "evaluation:" + id) for id in evaluation_groups),
        *(URIRef(BASE + "experiment:" + id) for id in evaluation_groups),
    }
    hypotheses = {triple for predicate in (HI.hasNullHypothesis, HI.hasAlternativeHypothesis) for triple in graph.triples((None, predicate, None))}
    assert len(hypotheses) == 4
    assert all(literal.language == "en" for _, _, literal in comments | hypotheses)
    interaction = URIRef(BASE + "interaction:clinical-dialogue")
    assert set(graph.objects(interaction, HI.hasAgentInvolved)) == agents
    assert set(graph.triples((None, HI.hasInteractionEpisode, None))) == {
        (execution, HI.hasInteractionEpisode, interaction) for execution in explanations
    }
    with TestClient(app) as client:
        response = client.post("/scenarios/preview", json=payload)
    assert response.status_code == 200
    assert response.json()["triple_count"] == 139
    assert response.json()["validation"]["conforms"] is True
    assert set(Graph().parse(data=response.json()["rdf"], format="nt")) == set(graph)
    for collection in ("tasks", "agents", "capabilities", "executions", "evaluations", "experiments", "interactions"):
        payload[collection].reverse()
    assert to_ntriples(to_rdf(Scenario.model_validate(payload))) == to_ntriples(graph)


@pytest.mark.parametrize("index, metric", [(0, "DiagnosisAccuracyMetric"), (1, "ExplanationClarityMetric")])
def test_source_metric_as_evaluation_assignments_remain_rejected(payload, index, metric):
    payload["evaluations"][index]["concept"] = metric
    with pytest.raises(ValueError, match=f"HINT concept {metric} is not a Evaluation concept"):
        to_rdf(Scenario.model_validate(payload))
    with TestClient(app) as client:
        response = client.post("/scenarios/preview", json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_vocabulary"
