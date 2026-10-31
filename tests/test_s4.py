import json
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS

from hi_scenario.api import app
from hi_scenario.model import Scenario
from hi_scenario.rdf import HI, HINT, ONTOLOGY_DIR, to_ntriples, to_rdf
from hi_scenario.validation import validate_rdf


BASE = "urn:hi-app:scenario:s4:"


@pytest.fixture
def payload():
    return json.loads((Path(__file__).resolve().parent.parent / "examples" / "s4.json").read_text(encoding="utf-8"))


def test_complete_s4_preserves_every_source_assertion_plus_only_labels_and_agent_conventions(payload):
    graph = to_rdf(Scenario.model_validate(payload))
    source = Graph().parse(ONTOLOGY_DIR / "scenarios_kgs.ttl", format="turtle")
    s4 = Namespace("https://w3id.org/hi-ontology/scenarios/4/")
    identities = {
        s4[original]: URIRef(BASE + application)
        for original, application in {
            "UseCaseAutonomousTutoring": "use-case:autonomous-tutoring",
            "HITeamTutoring": "team",
            "GoalEffectiveLearning": "goal:effective-learning",
            "ContextOnlineLearning": "context",
            "AITutor": "agent:ai-tutor",
            "HumanLearner": "agent:human-learner",
            "TaskReconstructTrajectory": "task:reconstruct-trajectory",
            "TaskRecommendResources": "task:recommend-resources",
            "TaskSemanticReasoning": "task:semantic-reasoning",
            "TaskBayesianInference": "task:bayesian-inference",
            "TaskKGQuery": "task:kg-query",
            "TaskExplainRecommendations": "task:explain-recommendations",
            "CapabilityBayesianReasoning": "capability:bayesian-reasoning",
            "CapabilitySemanticReasoning": "capability:semantic-reasoning",
            "CapabilityKGQuery": "capability:kg-query",
            "CapabilityExplanation": "capability:explaining",
            "CapabilitySelfReporting": "capability:self-reporting",
            "ExecProvideLearningHistory": "execution:provide-learning-history",
            "ExecReconstructTrajectory": "execution:reconstruct-trajectory",
            "ExecBayesianModeling": "execution:bayesian-modeling",
            "ExecSemanticReasoning": "execution:semantic-reasoning",
            "ExecRecommendResources": "execution:recommend-resources",
            "ExecExplainRecommendations": "execution:explain-recommendations",
            "ExperimentTutoringRelevance": "experiment:tutoring-relevance",
            "EvaluationTutorImpact": "evaluation:tutor-impact",
            "InteractionExplainRecommendations": "interaction:explain-recommendations",
        }.items()
    }

    def is_s4(term):
        return isinstance(term, URIRef) and str(term).startswith(str(s4))

    # Full source graph, including incoming links; no supported-predicate projection.
    original = {(s, p, o) for s, p, o in source if is_s4(s) or is_s4(o)}
    assert len(original) == 142
    entities = {term for s, _, o in original for term in (s, o) if is_s4(term)}
    assert len(identities) == len(set(identities.values())) == 26
    assert set(identities) == entities
    assert set(identities.values()) == set(graph.subjects())
    for original_node, application_node in identities.items():
        assert set(source.objects(original_node, RDF.type)) == set(graph.objects(application_node, RDF.type))
    assert Counter(graph.objects(None, RDF.type)) == {
        HI.UseCase: 1, HI.HITeam: 1, HI.Goal: 1, HI.Context: 1,
        HI.HumanAgent: 1, HI.ArtificialAgent: 1, HI.Task: 6, HI.Capability: 5,
        HI.TaskExecution: 6, HI.Evaluation: 1, HI.Experiment: 1, HI.Interaction: 1,
    }

    # Direct RDF-term comparison preserves punctuation, datatypes, and language tags.
    mapped = {(identities.get(s, s), p, identities.get(o, o)) for s, p, o in original}
    assert not mapped - set(graph)
    assert len(mapped & set(graph)) == 142
    labels = {
        (URIRef(BASE + entity), RDFS.label, Literal(name))
        for entity, name in {
            "use-case:autonomous-tutoring": "Autonomous tutoring",
            "goal:effective-learning": "Effective learning",
            "agent:ai-tutor": "AI tutor",
            "agent:human-learner": "Human learner",
            "task:reconstruct-trajectory": "Reconstruct learning trajectory",
            "task:recommend-resources": "Recommend resources",
            "task:semantic-reasoning": "Semantic reasoning",
            "task:bayesian-inference": "Bayesian inference",
            "task:kg-query": "Knowledge graph query",
            "task:explain-recommendations": "Explain recommendations",
        }.items()
    }
    # These category-consistent app conventions are not source assertions or entailments.
    for agent in (s4.AITutor, s4.HumanLearner):
        assert not list(source.objects(agent, HI.hasAgentConcept))
    conventions = {
        (identities[s4.AITutor], HI.hasAgentConcept, HINT.ArtificialAgent),
        (identities[s4.HumanLearner], HI.hasAgentConcept, HINT.HumanAgent),
    }
    assert not mapped & (labels | conventions)
    assert len(labels) == 10 and len(conventions) == 2
    assert set(graph) - mapped == labels | conventions
    assert len(graph) == 154
    before = set(graph)
    conforms, _, report = validate_rdf(graph)
    assert conforms, report
    assert set(graph) == before


def test_s4_descriptions_repeated_task_shared_evaluation_interaction_and_preview(payload):
    scenario = Scenario.model_validate(payload)
    assert Scenario.model_validate_json(scenario.model_dump_json()) == scenario
    graph = to_rdf(scenario)
    tasks = set(graph.subjects(RDF.type, HI.Task))
    assert set(graph.objects(URIRef(BASE + "goal:effective-learning"), HI.requiresTask)) == tasks
    comments = set(graph.triples((None, RDFS.comment, None)))
    assert len(comments) == 7
    assert {s for s, _, _ in comments} == tasks | {URIRef(BASE + "context")}
    assert all(value.language == "en" for _, _, value in comments)
    assert set(graph.objects(URIRef(BASE + "capability:semantic-reasoning"), HI.allowsTask)) == {
        URIRef(BASE + "task:semantic-reasoning"), URIRef(BASE + "task:recommend-resources"),
    }
    trajectory = {URIRef(BASE + "execution:provide-learning-history"), URIRef(BASE + "execution:reconstruct-trajectory")}
    assert set(graph.subjects(HI.realizesTask, URIRef(BASE + "task:reconstruct-trajectory"))) == trajectory
    assert {graph.value(execution, HI.performedBy) for execution in trajectory} == {
        URIRef(BASE + "agent:human-learner"), URIRef(BASE + "agent:ai-tutor"),
    }
    assert not list(graph.subjects(HI.realizesTask, URIRef(BASE + "task:kg-query")))
    assert len(list(graph.triples((None, HI.hasMethodConcept, None)))) == 6
    assert len(set(graph.objects(None, HI.hasMethodConcept))) == 5
    evaluation = URIRef(BASE + "evaluation:tutor-impact")
    assert set(graph.subjects(HI.evaluatedBy, evaluation)) == set(graph.subjects(RDF.type, HI.TaskExecution))
    experiment = URIRef(BASE + "experiment:tutoring-relevance")
    assert graph.value(evaluation, HI.hasExperiment) == experiment
    metrics = {HINT.RecommendationRelevanceMetric, HINT.LearningGainMetric, HINT.ExplanationClarityMetric}
    assert set(graph.objects(experiment, HI.hasMetricTested)) == metrics
    assert set(graph.objects(evaluation, HI.hasMetricConcept)) == metrics
    assert graph.value(experiment, HI.hasNullHypothesis) == Literal(
        "Personalized AI tutoring does not significantly improve relevance or learning gains over a non-personalized baseline.", lang="en",
    )
    assert graph.value(experiment, HI.hasAlternativeHypothesis) == Literal(
        "Combining Bayesian inference with semantic reasoning yields higher recommendation relevance, learning gains, and clearer explanations.", lang="en",
    )
    interaction = URIRef(BASE + "interaction:explain-recommendations")
    assert set(graph.triples((None, HI.hasInteractionEpisode, None))) == {
        (URIRef(BASE + "execution:explain-recommendations"), HI.hasInteractionEpisode, interaction),
    }
    assert set(graph.objects(interaction, HI.hasAgentInvolved)) == {
        URIRef(BASE + "agent:ai-tutor"), URIRef(BASE + "agent:human-learner"),
    }
    with TestClient(app) as client:
        response = client.post("/scenarios/preview", json=payload)
    assert response.status_code == 200
    assert response.json()["triple_count"] == 154
    assert response.json()["validation"]["conforms"] is True
    assert set(Graph().parse(data=response.json()["rdf"], format="nt")) == set(graph)
    for collection in ("tasks", "agents", "capabilities", "executions", "evaluations", "experiments", "interactions"):
        payload[collection].reverse()
    assert to_ntriples(to_rdf(Scenario.model_validate(payload))) == to_ntriples(graph)
