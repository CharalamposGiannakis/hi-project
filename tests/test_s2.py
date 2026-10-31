import json
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS

from hi_scenario.api import app
from hi_scenario.model import Scenario
from hi_scenario.rdf import HI, ONTOLOGY_DIR, to_ntriples, to_rdf
from hi_scenario.validation import validate_rdf


BASE = "urn:hi-app:scenario:s2:"


@pytest.fixture
def payload():
    return json.loads((Path(__file__).resolve().parent.parent / "examples" / "s2.json").read_text(encoding="utf-8"))


def test_complete_s2_preserves_all_source_facts_except_the_documented_interaction_goal(payload):
    graph = to_rdf(Scenario.model_validate(payload))
    source = Graph().parse(ONTOLOGY_DIR / "scenarios_kgs.ttl", format="turtle")
    s2 = Namespace("https://w3id.org/hi-ontology/scenarios/2/")
    identities = {
        s2[original]: URIRef(BASE + application)
        for original, application in {
            "UseCaseCollaborativeManipulation": "use-case:collaborative-manipulation",
            "HITeamCollabManipulation": "team",
            "GoalSafeToolRetrieval": "goal:safe-tool-retrieval",
            "ContextWorkspaceManipulation": "context",
            "HumanTechnician": "agent:human-technician",
            "RobotManipulator": "agent:robot-manipulator",
            "TaskUnlockCabinet": "task:unlock-cabinet",
            "TaskOpenCabinet": "task:open-cabinet",
            "TaskRetrieveTool": "task:retrieve-tool",
            "TaskFineInsertion": "task:fine-insertion",
            "TaskHeavyLift": "task:heavy-lift",
            "TaskSituationalAssessment": "task:situational-assessment",
            "TaskDataCollection": "task:data-collection",
            "TaskPolicyLearning": "task:policy-learning",
            "TaskKnowledgeQuery": "task:knowledge-query",
            "TaskExplanation": "task:explanation",
            "CapabilityHeavyLifting": "capability:heavy-lifting",
            "CapabilityConfinedReach": "capability:confined-reach",
            "CapabilityRLPolicyLearning": "capability:rl-policy-learning",
            "CapabilityExplanation": "capability:explaining",
            "CapabilityKGQuery": "capability:kg-query",
            "CapabilityFineDexterity": "capability:fine-dexterity",
            "CapabilitySituationalAwareness": "capability:situational-awareness",
            "CapabilitySelfReporting": "capability:self-reporting",
            "ExecUnlockCabinet": "execution:unlock-cabinet",
            "ExecOpenCabinet": "execution:open-cabinet",
            "ExecConfinedReach": "execution:confined-reach",
            "ExecHeavyLift": "execution:heavy-lift",
            "ExecRLExplain": "execution:rl-explain",
            "EvalFineManipulation": "evaluation:fine-manipulation",
            "EvalKGQueryAccuracy": "evaluation:kg-query-accuracy",
            "EvalReachSafety": "evaluation:reach-safety",
            "EvalLoadSafety": "evaluation:load-safety",
            "EvalExplanationTransparency": "evaluation:explanation-transparency",
            "ExperimentFineManipulation": "experiment:fine-manipulation",
            "ExperimentKGSupport": "experiment:kg-support",
            "ExperimentReachSafety": "experiment:reach-safety",
            "ExperimentLoadSafety": "experiment:load-safety",
            "ExperimentExplanationTransparency": "experiment:explanation-transparency",
            "InteractionExplainRisk": "interaction:explain-risk",
        }.items()
    }

    def is_s2(term):
        return isinstance(term, URIRef) and str(term).startswith(str(s2))

    # Include incoming links and every predicate; do not compare a supported projection.
    original = {(s, p, o) for s, p, o in source if is_s2(s) or is_s2(o)}
    assert len(original) == 182
    entities = {term for s, _, o in original for term in (s, o) if is_s2(term)}
    assert len(identities) == len(set(identities.values())) == 40
    assert set(identities) == entities
    assert set(identities.values()) == set(graph.subjects())
    for original_node, application_node in identities.items():
        assert set(source.objects(original_node, RDF.type)) == set(graph.objects(application_node, RDF.type))
    assert Counter(graph.objects(None, RDF.type)) == {
        HI.UseCase: 1, HI.HITeam: 1, HI.Goal: 1, HI.Context: 1,
        HI.HumanAgent: 1, HI.ArtificialAgent: 1, HI.Task: 10, HI.Capability: 8,
        HI.TaskExecution: 5, HI.Evaluation: 5, HI.Experiment: 5, HI.Interaction: 1,
    }

    # RDF terms retain exact literal text, datatypes, and language tags.
    mapped = {(identities.get(s, s), p, identities.get(o, o)) for s, p, o in original}
    exception = (identities[s2.InteractionExplainRisk], HI.towardsGoal, identities[s2.GoalSafeToolRetrieval])
    assert exception in mapped
    assert mapped - set(graph) == {exception}
    assert len(mapped & set(graph)) == 181
    labels = {
        (URIRef(BASE + entity), RDFS.label, Literal(name))
        for entity, name in {
            "use-case:collaborative-manipulation": "Collaborative manipulation",
            "goal:safe-tool-retrieval": "Safe tool retrieval",
            "agent:human-technician": "Human technician",
            "agent:robot-manipulator": "Robot manipulator",
            "task:unlock-cabinet": "Unlock cabinet",
            "task:open-cabinet": "Open cabinet",
            "task:retrieve-tool": "Retrieve tool",
            "task:fine-insertion": "Fine insertion",
            "task:heavy-lift": "Heavy lifting",
            "task:situational-assessment": "Situational assessment",
            "task:data-collection": "Data collection",
            "task:policy-learning": "Policy learning",
            "task:knowledge-query": "Knowledge graph query",
            "task:explanation": "Explanation",
        }.items()
    }
    assert len(labels) == 14
    assert set(graph) - mapped == labels  # No additional semantic relationships.
    assert len(graph) == 195
    ontology = Graph().parse(ONTOLOGY_DIR / "hi-ontology.ttl", format="turtle")
    assert (HI.towardsGoal, RDFS.domain, HI.TaskExecution) in ontology
    before = set(graph)
    conforms, _, report = validate_rdf(graph)
    assert conforms, report
    assert set(graph) == before


def test_s2_json_round_trip_preview_and_distinctive_patterns(payload):
    scenario = Scenario.model_validate(payload)
    assert Scenario.model_validate_json(scenario.model_dump_json()) == scenario
    graph = to_rdf(scenario)
    goal = URIRef(BASE + "goal:safe-tool-retrieval")
    assert set(graph.objects(goal, HI.requiresTask)) == {
        URIRef(BASE + "task:" + id) for id in ("unlock-cabinet", "open-cabinet", "retrieve-tool")
    }
    assert set(graph.subjects(HI.realizesTask, URIRef(BASE + "task:heavy-lift"))) == {
        URIRef(BASE + "execution:confined-reach"), URIRef(BASE + "execution:heavy-lift"),
    }
    assert not list(graph.subjects(HI.realizesTask, URIRef(BASE + "task:retrieve-tool")))
    assert len(list(graph.triples((None, HI.hasMethodConcept, None)))) == 3
    assert not list(graph.triples((None, HI.hasInteractionEpisode, None)))
    hypotheses = [o for _, p, o in graph if p in (HI.hasNullHypothesis, HI.hasAlternativeHypothesis)]
    assert len(hypotheses) == 10
    assert all(value.language is None and value.datatype is None for value in hypotheses)
    with TestClient(app) as client:
        response = client.post("/scenarios/preview", json=payload)
    assert response.status_code == 200
    assert response.json()["triple_count"] == 195
    assert response.json()["validation"]["conforms"] is True
    assert set(Graph().parse(data=response.json()["rdf"], format="nt")) == set(graph)
    for collection in ("tasks", "agents", "capabilities", "executions", "evaluations", "experiments"):
        payload[collection].reverse()
    assert to_ntriples(to_rdf(Scenario.model_validate(payload))) == to_ntriples(graph)
