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


BASE = "urn:hi-app:scenario:s7:"


@pytest.fixture
def payload():
    return json.loads((Path(__file__).resolve().parent.parent / "examples" / "s7.json").read_text(encoding="utf-8"))


def test_complete_s7_has_only_three_provisional_replacements_labels_entailed_inverse_and_conventions(payload):
    graph = to_rdf(Scenario.model_validate(payload))
    source = Graph().parse(ONTOLOGY_DIR / "scenarios_kgs.ttl", format="turtle")
    s7 = Namespace("https://w3id.org/hi-ontology/scenarios/7/")
    identities = {
        s7[original]: URIRef(BASE + application)
        for original, application in {
            "UseCaseVirtualMuseumGuide": "use-case:virtual-museum-guide",
            "HITeamVirtualMuseum": "team",
            "GoalEnhancedVisitorLearning": "goal:enhanced-visitor-learning",
            "ContextVirtualExhibition": "context",
            "AIVirtualGuide": "agent:ai-virtual-guide",
            "HumanVisitor": "agent:human-visitor",
            "TaskInterpretMultimodalInput": "task:interpret-multimodal-input",
            "TaskSemanticRetrieval": "task:semantic-retrieval",
            "TaskComputeSimilarity": "task:compute-similarity",
            "TaskRecommendArtifacts": "task:recommend-artifacts",
            "TaskAnswerQuestions": "task:answer-questions",
            "TaskExplainRecommendations": "task:explain-recommendations",
            "CapabilityMultimodalInterpretation": "capability:multimodal-interpretation",
            "CapabilitySemanticReasoning": "capability:semantic-reasoning",
            "CapabilityKGQuery": "capability:kg-query",
            "CapabilityEmbeddingReasoning": "capability:embedding-reasoning",
            "CapabilityExplanation": "capability:explaining",
            "CapabilitySelfReporting": "capability:self-reporting",
            "ExecProvideProfile": "execution:provide-profile",
            "ExecInterpretInput": "execution:interpret-input",
            "ExecSemanticRetrieval": "execution:semantic-retrieval",
            "ExecComputeSimilarity": "execution:compute-similarity",
            "ExecRecommendArtifacts": "execution:recommend-artifacts",
            "ExecAnswerQuestions": "execution:answer-questions",
            "ExecExplainRecommendations": "execution:explain-recommendations",
            "InteractionVRGuidedTour": "interaction:vr-guided-tour",
            "InteractionQA": "interaction:qa",
            "ExperimentVRGuideEffectiveness": "experiment:vr-guide-effectiveness",
            "EvaluationVRGuideImpact": "evaluation:vr-guide-impact",
        }.items()
    }

    def is_s7(term):
        return isinstance(term, URIRef) and str(term).startswith(str(s7))

    # Include incoming references, undefined intent objects, and every predicate.
    original = {(s, p, o) for s, p, o in source if is_s7(s) or is_s7(o)}
    assert len(original) == 160
    resources = {term for s, _, o in original for term in (s, o) if is_s7(term)}
    typed = {s for s, p, _ in original if p == RDF.type}
    unresolved = resources - typed
    assert len(resources) == 31
    assert unresolved == {s7.IntentGuide, s7.IntentAnswer}
    assert len(identities) == len(set(identities.values())) == len(typed) == 29
    assert set(identities) == typed
    assert set(identities.values()) == set(graph.subjects())
    for original_node, application_node in identities.items():
        assert set(source.objects(original_node, RDF.type)) == set(graph.objects(application_node, RDF.type))
    assert Counter(graph.objects(None, RDF.type)) == {
        HI.UseCase: 1, HI.HITeam: 1, HI.Goal: 1, HI.Context: 1,
        HI.HumanAgent: 1, HI.ArtificialAgent: 1, HI.Task: 6, HI.Capability: 6,
        HI.TaskExecution: 7, HI.Evaluation: 1, HI.Experiment: 1, HI.Interaction: 2,
    }
    # Do not map unresolved local resources to HINT: these are changed assertions.
    mapped = {(identities.get(s, s), p, identities.get(o, o)) for s, p, o in original}
    vocabulary = Graph().parse(ONTOLOGY_DIR / "hi-thesaurus.ttl", format="turtle")
    ontology = Graph().parse(ONTOLOGY_DIR / "hi-ontology.ttl", format="turtle")
    replaced = set()
    replacements = set()
    for interaction, local_intent, hint_intent in (
        (s7.InteractionVRGuidedTour, s7.IntentGuide, HINT.GuideIntent),
        (s7.InteractionQA, s7.IntentAnswer, HINT.AnswerIntent),
    ):
        # The only occurrence of each local intent is its incoming source reference.
        assert {triple for triple in source if local_intent in triple} == {
            (interaction, HI.hasInteractionIntentConcept, local_intent),
        }
        assert (hint_intent, RDF.type, SKOS.Concept) in vocabulary
        assert (hint_intent, SKOS.broader, HINT.InteractionIntent) in vocabulary
        replaced.add((identities[interaction], HI.hasInteractionIntentConcept, local_intent))
        replacements.add((identities[interaction], HI.hasInteractionIntentConcept, hint_intent))
    assert not any(HINT.SelfReportingMethod in triple for triple in vocabulary), "Review the provisional S7 method: SelfReportingMethod now occurs in HINT"
    assert (HINT.DataCollectionMethod, RDF.type, SKOS.Concept) in vocabulary
    assert (HINT.DataCollectionMethod, SKOS.broader, HINT.Method) in vocabulary
    assert (HINT.DataCollectionMethod, SKOS.definition, Literal(
        "A method used to gather and record multimodal, self-reported, or sensor-based data.", lang="en",
    )) in vocabulary
    replaced.add((identities[s7.ExecProvideProfile], HI.hasMethodConcept, HINT.SelfReportingMethod))
    replacements.add((identities[s7.ExecProvideProfile], HI.hasMethodConcept, HINT.DataCollectionMethod))
    assert len(replaced) == len(replacements) == 3
    assert replaced <= mapped
    # Direct RDF terms preserve literal text, punctuation, datatype, and language tags.
    assert mapped - set(graph) == replaced  # Nothing is omitted without replacement.
    assert len(mapped & set(graph)) == 157
    constraints = {HINT.PrivacyConstraint, HINT.TransparencyConstraint, HINT.AccessibilityConstraint}
    constraint_triples = {
        (identities[subject], HI.hasConstraintConcept, constraint)
        for subject in (s7.HITeamVirtualMuseum, s7.ContextVirtualExhibition)
        for constraint in constraints
    }
    assert len(constraint_triples) == 6
    assert constraint_triples <= mapped & set(graph)

    assert (HI.requiresCapability, OWL.inverseOf, HI.allowsTask) in ontology
    assert (s7.CapabilityKGQuery, HI.allowsTask, s7.TaskSemanticRetrieval) in original
    entailed_inverse = (identities[s7.TaskSemanticRetrieval], HI.requiresCapability, identities[s7.CapabilityKGQuery])
    assert entailed_inverse not in mapped
    forward = {(s, o) for s, p, o in original if p == HI.allowsTask}
    inverse = {(o, s) for s, p, o in original if p == HI.requiresCapability}
    assert forward - inverse == {(s7.CapabilityKGQuery, s7.TaskSemanticRetrieval)}
    assert not inverse - forward
    assert {(s, o) for s, p, o in original if p == HI.performedBy} == {
        (o, s) for s, p, o in original if p == HI.performsExecution
    }
    for agent in (s7.AIVirtualGuide, s7.HumanVisitor):
        assert not list(source.objects(agent, HI.hasAgentConcept))
    conventions = {
        (identities[s7.AIVirtualGuide], HI.hasAgentConcept, HINT.ArtificialAgent),
        (identities[s7.HumanVisitor], HI.hasAgentConcept, HINT.HumanAgent),
    }
    assert (s7.ContextVirtualExhibition, HI.hasInfluenceOn, s7.HITeamVirtualMuseum) in original
    labels = {
        (URIRef(BASE + entity), RDFS.label, Literal(name))
        for entity, name in {
            "use-case:virtual-museum-guide": "Virtual museum guide",
            "goal:enhanced-visitor-learning": "Enhanced visitor learning",
            "agent:ai-virtual-guide": "AI virtual guide",
            "agent:human-visitor": "Human visitor",
            "task:interpret-multimodal-input": "Interpret multimodal input",
            "task:semantic-retrieval": "Semantic retrieval",
            "task:compute-similarity": "Compute similarity",
            "task:recommend-artifacts": "Recommend artifacts",
            "task:answer-questions": "Answer questions",
            "task:explain-recommendations": "Explain recommendations",
        }.items()
    }
    assert len(labels) == 10 and len(conventions) == 2
    assert not mapped & (replacements | labels | conventions | {entailed_inverse})
    assert set(graph) - mapped == replacements | labels | conventions | {entailed_inverse}
    assert len(graph) == 173
    before = set(graph)
    conforms, _, report = validate_rdf(graph)
    assert conforms, report
    assert set(graph) == before


def test_s7_shared_tasks_capabilities_evaluation_episodes_hypotheses_and_preview(payload):
    scenario = Scenario.model_validate(payload)
    assert Scenario.model_validate_json(scenario.model_dump_json()) == scenario
    graph = to_rdf(scenario)
    assert set(graph.objects(URIRef(BASE + "goal:enhanced-visitor-learning"), HI.requiresTask)) == set(graph.subjects(RDF.type, HI.Task))
    assert len(set(graph.subjects(RDF.type, HI.Capability))) == 6
    assert set(graph.subjects(HI.hasTaskConcept, HINT.SemanticReasoningTask)) == {
        URIRef(BASE + "task:semantic-retrieval"), URIRef(BASE + "task:compute-similarity"),
    }
    for task, capabilities in (
        ("semantic-retrieval", {"semantic-reasoning", "kg-query"}),
        ("interpret-multimodal-input", {"multimodal-interpretation", "self-reporting"}),
    ):
        assert set(graph.objects(URIRef(BASE + "task:" + task), HI.requiresCapability)) == {
            URIRef(BASE + "capability:" + capability) for capability in capabilities
        }
    profiles = {URIRef(BASE + "execution:provide-profile"), URIRef(BASE + "execution:interpret-input")}
    assert set(graph.subjects(HI.realizesTask, URIRef(BASE + "task:interpret-multimodal-input"))) == profiles
    assert {graph.value(execution, HI.performedBy) for execution in profiles} == {
        URIRef(BASE + "agent:human-visitor"), URIRef(BASE + "agent:ai-virtual-guide"),
    }
    evaluation = URIRef(BASE + "evaluation:vr-guide-impact")
    executions = set(graph.subjects(RDF.type, HI.TaskExecution))
    assert len(executions) == 7
    assert set(graph.subjects(HI.evaluatedBy, evaluation)) == executions
    assert set(graph.triples((None, HI.hasInteractionEpisode, None))) == {
        (URIRef(BASE + "execution:recommend-artifacts"), HI.hasInteractionEpisode, URIRef(BASE + "interaction:vr-guided-tour")),
        (URIRef(BASE + "execution:answer-questions"), HI.hasInteractionEpisode, URIRef(BASE + "interaction:qa")),
    }
    experiment = URIRef(BASE + "experiment:vr-guide-effectiveness")
    assert graph.value(evaluation, HI.hasExperiment) == experiment
    metrics = {HINT.RecommendationRelevanceMetric, HINT.AnswerAccuracyMetric, HINT.EngagementTimeMetric, HINT.ExplanationClarityMetric}
    assert set(graph.objects(experiment, HI.hasMetricTested)) == metrics
    assert set(graph.objects(evaluation, HI.hasMetricConcept)) == metrics
    assert graph.value(experiment, HI.hasNullHypothesis) == Literal("No improvement over a non-personalized baseline.", lang="en")
    assert graph.value(experiment, HI.hasAlternativeHypothesis) == Literal("Multimodal input + KG reasoning improves engagement and relevance.", lang="en")
    with TestClient(app) as client:
        response = client.post("/scenarios/preview", json=payload)
    assert response.status_code == 200
    assert response.json()["triple_count"] == 173
    assert response.json()["validation"]["conforms"] is True
    assert set(Graph().parse(data=response.json()["rdf"], format="nt")) == set(graph)
    for collection in ("tasks", "agents", "capabilities", "executions", "evaluations", "experiments", "interactions", "team_constraints"):
        payload[collection].reverse()
    assert to_ntriples(to_rdf(Scenario.model_validate(payload))) == to_ntriples(graph)


def test_undefined_source_method_and_local_intent_names_are_not_accepted_as_aliases(payload):
    payload["executions"][0]["method"] = "SelfReportingMethod"
    with pytest.raises(ValueError, match="Unknown HINT concept: SelfReportingMethod"):
        to_rdf(Scenario.model_validate(payload))
    payload["executions"][0]["method"] = "DataCollectionMethod"
    for original_local_name in ("IntentGuide", "IntentAnswer"):
        payload["interactions"][0]["intent"] = original_local_name
        with pytest.raises(ValueError, match=f"Unknown HINT concept: {original_local_name}"):
            to_rdf(Scenario.model_validate(payload))
