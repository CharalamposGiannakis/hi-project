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


BASE = "urn:hi-app:scenario:s6:"


@pytest.fixture
def payload():
    return json.loads((Path(__file__).resolve().parent.parent / "examples" / "s6.json").read_text(encoding="utf-8"))


def test_complete_s6_preserves_every_source_assertion_plus_only_labels_and_agent_conventions(payload):
    graph = to_rdf(Scenario.model_validate(payload))
    source = Graph().parse(ONTOLOGY_DIR / "scenarios_kgs.ttl", format="turtle")
    s6 = Namespace("https://w3id.org/hi-ontology/scenarios/6/")
    identities = {
        s6[original]: URIRef(BASE + application)
        for original, application in {
            "UseCaseCampusEnergyNegotiation": "use-case:campus-energy-negotiation",
            "HITeamCampusEnergy": "team",
            "GoalFairEfficientHeating": "goal:fair-efficient-heating",
            "ContextSmartCampus": "context",
            "AIBuildingAgent": "agent:ai-building-agent",
            "HumanGridOperator": "agent:human-grid-operator",
            "TaskLearnOccupancy": "task:learn-occupancy",
            "TaskLearnEnergyBehavior": "task:learn-energy-behavior",
            "TaskNegotiateAllocation": "task:negotiate-allocation",
            "TaskCoordinateWithOperator": "task:coordinate-with-operator",
            "TaskExplainDecision": "task:explain-decision",
            "CapabilityPatternLearning": "capability:pattern-learning",
            "CapabilityNegotiation": "capability:negotiation",
            "CapabilityKGQuery": "capability:kg-query",
            "CapabilityExplanation": "capability:explaining",
            "CapabilityOperatorCoordination": "capability:operator-coordination",
            "ExecLearnOccupancy": "execution:learn-occupancy",
            "ExecLearnEnergyBehavior": "execution:learn-energy-behavior",
            "ExecNegotiate": "execution:negotiate",
            "ExecCoordinateWithOperator": "execution:coordinate-with-operator",
            "ExecExplainDecision": "execution:explain-decision",
            "ExecExplainOperator": "execution:explain-operator",
            "InteractionNegotiation": "interaction:negotiation",
            "InteractionExplainAllocation": "interaction:explain-allocation",
            "ExperimentCampusEnergy": "experiment:campus-energy",
            "EvaluationNegotiationImpact": "evaluation:negotiation-impact",
        }.items()
    }

    def is_s6(term):
        return isinstance(term, URIRef) and str(term).startswith(str(s6))

    # Full source graph, including incoming links and every predicate.
    original = {(s, p, o) for s, p, o in source if is_s6(s) or is_s6(o)}
    assert len(original) == 139
    entities = {term for s, _, o in original for term in (s, o) if is_s6(term)}
    assert len(identities) == len(set(identities.values())) == 26
    assert set(identities) == entities
    assert set(identities.values()) == set(graph.subjects())
    for original_node, application_node in identities.items():
        assert set(source.objects(original_node, RDF.type)) == set(graph.objects(application_node, RDF.type))
    assert Counter(graph.objects(None, RDF.type)) == {
        HI.UseCase: 1, HI.HITeam: 1, HI.Goal: 1, HI.Context: 1,
        HI.HumanAgent: 1, HI.ArtificialAgent: 1, HI.Task: 5, HI.Capability: 5,
        HI.TaskExecution: 6, HI.Evaluation: 1, HI.Experiment: 1, HI.Interaction: 2,
    }
    # Compare RDF terms directly, preserving text, punctuation, language, and datatype.
    mapped = {(identities.get(s, s), p, identities.get(o, o)) for s, p, o in original}
    assert not mapped - set(graph)
    assert len(mapped & set(graph)) == 139
    labels = {
        (URIRef(BASE + entity), RDFS.label, Literal(name))
        for entity, name in {
            "use-case:campus-energy-negotiation": "Campus energy negotiation",
            "goal:fair-efficient-heating": "Fair and efficient heating",
            "agent:ai-building-agent": "AI building agent",
            "agent:human-grid-operator": "Human grid operator",
            "task:learn-occupancy": "Learn occupancy",
            "task:learn-energy-behavior": "Learn energy behavior",
            "task:negotiate-allocation": "Negotiate allocation",
            "task:coordinate-with-operator": "Coordinate with operator",
            "task:explain-decision": "Explain decision",
        }.items()
    }
    for agent in (s6.AIBuildingAgent, s6.HumanGridOperator):
        assert not list(source.objects(agent, HI.hasAgentConcept))
    # Category-consistent application conventions, not source assertions or entailments.
    conventions = {
        (identities[s6.AIBuildingAgent], HI.hasAgentConcept, HINT.ArtificialAgent),
        (identities[s6.HumanGridOperator], HI.hasAgentConcept, HINT.HumanAgent),
    }
    assert len(labels) == 9 and len(conventions) == 2
    assert not mapped & (labels | conventions)
    assert set(graph) - mapped == labels | conventions
    assert len(graph) == 150
    assert (s6.ContextSmartCampus, HI.hasInfluenceOn, s6.HITeamCampusEnergy) in original
    for forward, inverse, count in ((HI.allowsTask, HI.requiresCapability, 5), (HI.performedBy, HI.performsExecution, 6)):
        pairs = {(s, o) for s, p, o in original if p == forward}
        assert len(pairs) == count
        assert pairs == {(o, s) for s, p, o in original if p == inverse}
    before = set(graph)
    conforms, _, report = validate_rdf(graph)
    assert conforms, report
    assert set(graph) == before


def test_s6_assignments_shared_entities_separate_episodes_plain_hypotheses_and_preview(payload):
    scenario = Scenario.model_validate(payload)
    assert Scenario.model_validate_json(scenario.model_dump_json()) == scenario
    graph = to_rdf(scenario)
    goal = URIRef(BASE + "goal:fair-efficient-heating")
    assert set(graph.objects(goal, HI.requiresTask)) == set(graph.subjects(RDF.type, HI.Task))
    agents = {URIRef(BASE + "agent:ai-building-agent"), URIRef(BASE + "agent:human-grid-operator")}
    assert set(graph.subjects(HI.hasCapability, URIRef(BASE + "capability:explaining"))) == agents
    evaluation = URIRef(BASE + "evaluation:negotiation-impact")
    assignments = {
        "learn-occupancy": ("learn-occupancy", "ai-building-agent", HINT.CooperativeLearningMethod),
        "learn-energy-behavior": ("learn-energy-behavior", "ai-building-agent", HINT.KnowledgeGraphQueryMethod),
        "negotiate": ("negotiate-allocation", "ai-building-agent", HINT.ProtocolNegotiationMethod),
        "coordinate-with-operator": ("coordinate-with-operator", "human-grid-operator", HINT.ProtocolNegotiationMethod),
        "explain-decision": ("explain-decision", "ai-building-agent", HINT.PostHocExplanationMethod),
        "explain-operator": ("explain-decision", "human-grid-operator", HINT.PostHocExplanationMethod),
    }
    executions = {URIRef(BASE + "execution:" + id) for id in assignments}
    assert set(graph.subjects(RDF.type, HI.TaskExecution)) == executions
    assert set(graph.subjects(HI.evaluatedBy, evaluation)) == executions
    for id, (task, agent, method) in assignments.items():
        execution = URIRef(BASE + "execution:" + id)
        assert graph.value(execution, HI.realizesTask) == URIRef(BASE + "task:" + task)
        assert graph.value(execution, HI.performedBy) == URIRef(BASE + "agent:" + agent)
        assert (URIRef(BASE + "agent:" + agent), HI.performsExecution, execution) in graph
        assert graph.value(execution, HI.hasMethodConcept) == method
        assert graph.value(execution, HI.towardsGoal) == goal
    assert set(graph.subjects(HI.realizesTask, URIRef(BASE + "task:explain-decision"))) == {
        URIRef(BASE + "execution:explain-decision"), URIRef(BASE + "execution:explain-operator"),
    }
    assert set(graph.triples((None, HI.hasInteractionEpisode, None))) == {
        (URIRef(BASE + "execution:negotiate"), HI.hasInteractionEpisode, URIRef(BASE + "interaction:negotiation")),
        (URIRef(BASE + "execution:explain-decision"), HI.hasInteractionEpisode, URIRef(BASE + "interaction:explain-allocation")),
    }
    assert not list(graph.objects(URIRef(BASE + "execution:explain-operator"), HI.hasInteractionEpisode))
    for interaction in graph.subjects(RDF.type, HI.Interaction):
        assert set(graph.objects(interaction, HI.hasAgentInvolved)) == agents
    experiment = URIRef(BASE + "experiment:campus-energy")
    assert graph.value(evaluation, HI.hasExperiment) == experiment
    metrics = {HINT.EnergyEfficiencyMetric, HINT.UserComfortMetric, HINT.FairOutcomeMetric, HINT.CO2ReductionMetric}
    assert set(graph.objects(experiment, HI.hasMetricTested)) == metrics
    assert set(graph.objects(evaluation, HI.hasMetricConcept)) == metrics
    assert graph.value(experiment, HI.hasNullHypothesis) == Literal(
        "Negotiation and co-learning do not improve fairness or efficiency compared to independent building control.",
    )
    assert graph.value(experiment, HI.hasAlternativeHypothesis) == Literal(
        "Co-learning and negotiation improve efficiency, fairness, and comfort while reducing CO2 emissions.",
    )
    for predicate in (HI.hasNullHypothesis, HI.hasAlternativeHypothesis):
        literal = graph.value(experiment, predicate)
        assert literal.language is None and literal.datatype is None
    vocabulary = Graph().parse(ONTOLOGY_DIR / "hi-thesaurus.ttl", format="turtle")
    for term, category in ((HINT.AllocationNegotationTask, HINT.Task), (HINT.NegotationImpactEvaluation, HINT.Evaluation)):
        assert (term, RDF.type, SKOS.Concept) in vocabulary
        assert (term, SKOS.broader, category) in vocabulary
    assert graph.value(URIRef(BASE + "task:negotiate-allocation"), HI.hasTaskConcept) == HINT.AllocationNegotationTask
    assert graph.value(evaluation, HI.hasEvaluationConcept) == HINT.NegotationImpactEvaluation
    with TestClient(app) as client:
        response = client.post("/scenarios/preview", json=payload)
    assert response.status_code == 200
    assert response.json()["triple_count"] == 150
    assert response.json()["validation"]["conforms"] is True
    assert set(Graph().parse(data=response.json()["rdf"], format="nt")) == set(graph)
    for collection in ("tasks", "agents", "capabilities", "executions", "evaluations", "experiments", "interactions"):
        payload[collection].reverse()
    assert to_ntriples(to_rdf(Scenario.model_validate(payload))) == to_ntriples(graph)
