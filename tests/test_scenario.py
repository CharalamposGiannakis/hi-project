import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError
from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SH

from hi_scenario.model import Scenario
from hi_scenario.rdf import HI, HINT, ONTOLOGY_DIR, to_ntriples, to_rdf
from hi_scenario.validation import validate_rdf


ROOT = Path(__file__).resolve().parent.parent
BASE = "urn:hi-app:scenario:s1:"
TEAM = URIRef(BASE + "team")


@pytest.fixture
def payload():
    return json.loads((ROOT / "examples" / "s1.json").read_text(encoding="utf-8"))


def assert_conforms(graph):
    before = set(graph)
    conforms, _, report = validate_rdf(graph)
    assert conforms, report
    assert set(graph) == before  # Validation must not materialize facts in the ABox.


def test_s1_reproduces_research_core_and_passes_shacl(payload):
    scenario = Scenario.model_validate(payload)
    graph = to_rdf(scenario)
    assert_conforms(graph)

    # Compare the entire supported projection with S1 in the research artefact.
    source = Graph().parse(ONTOLOGY_DIR / "scenarios_kgs.ttl", format="turtle")
    s1 = Namespace("https://w3id.org/hi-ontology/scenarios/1/")
    identities = {
        s1.UseCasePersonalAssistantHI: URIRef(BASE + "use-case:personal-assistant"),
        s1.HITeamPersonalAssistant: TEAM,
        s1.GoalUserWellbeing: URIRef(BASE + "goal:user-wellbeing"),
        s1.TaskDataCollection: URIRef(BASE + "task:data-collection"),
        s1.TaskConflictResolution: URIRef(BASE + "task:conflict-resolution"),
        s1.TaskExplanation: URIRef(BASE + "task:explanation"),
        s1.HumanUser: URIRef(BASE + "agent:human-user"),
        s1.AIAssistant: URIRef(BASE + "agent:ai-assistant"),
        s1.ContextHealthMonitoring: URIRef(BASE + "context"),
        s1.CapabilitySensing: URIRef(BASE + "capability:sensing"),
        s1.CapabilitySelfReporting: URIRef(BASE + "capability:self-reporting"),
        s1.CapabilityReasoning: URIRef(BASE + "capability:reasoning"),
        s1.CapabilityExplanation: URIRef(BASE + "capability:explaining"),
        s1.ExecutionDataCollection: URIRef(BASE + "execution:data-collection"),
        s1.ExecutionConflictResolution: URIRef(BASE + "execution:conflict-resolution"),
        s1.ExecutionExplanation: URIRef(BASE + "execution:explanation"),
        s1.ExperimentDataCollectionQuality: URIRef(BASE + "experiment:data-collection-quality"),
        s1.ExperimentConflictAccuracy: URIRef(BASE + "experiment:conflict-accuracy"),
        s1.ExperimentTransparencyTrust: URIRef(BASE + "experiment:transparency-trust"),
        s1.EvaluationDataCollectionQuality: URIRef(BASE + "evaluation:data-collection-quality"),
        s1.EvaluationConflictAccuracy: URIRef(BASE + "evaluation:conflict-accuracy"),
        s1.EvaluationTransparencyImpact: URIRef(BASE + "evaluation:transparency-impact"),
        s1.InteractionExplainDecision: URIRef(BASE + "interaction:explain-decision"),
    }
    predicates = {
        RDF.type, HI.hasUseCaseConcept, HI.hasDomainConcept, HI.hasHITeam,
        HI.hasGoal, HI.hasMember, HI.hasGoalConcept, HI.requiresTask,
        HI.hasTaskConcept, HI.hasAgentConcept, HI.hasRoleConcept,
        HI.hasContextConcept, HI.hasPhenomenonConcept, HI.hasConstraintConcept,
        HI.operatesInContext, HI.hasInfluenceOn,
        HI.hasCapabilityConcept, HI.hasCapability, HI.allowsTask, HI.requiresCapability,
        HI.hasExecutionConcept, HI.hasMethodConcept, HI.realizesTask,
        HI.performedBy, HI.performsExecution, HI.towardsGoal,
        HI.hasExperimentConcept, HI.hasMetricTested, HI.hasNullHypothesis, HI.hasAlternativeHypothesis,
        HI.hasEvaluationConcept, HI.hasMetricConcept, HI.hasExperiment, HI.evaluatedBy,
        HI.hasAgentInvolved, HI.hasInteractionIntentConcept, HI.hasInteractionModalityConcept, HI.hasInteractionEpisode,
    }
    expected = {
        (identities[s], p, identities.get(o, o))
        for s, p, o in source
        if s in identities and (p in predicates or (p == RDFS.comment and s in {
            s1.ContextHealthMonitoring, s1.EvaluationDataCollectionQuality,
            s1.EvaluationConflictAccuracy, s1.EvaluationTransparencyImpact,
        }))
    }
    assert len(expected) == 116
    assert {(s, p, o) for s, p, o in graph if p != RDFS.label} == expected
    assert len(set(graph.subjects(RDF.type, HI.UseCase))) == 1
    assert len(set(graph.subjects(RDF.type, HI.Goal))) == 1
    assert len(set(graph.subjects(RDF.type, HI.Task))) == 3
    for agent in scenario.agents:
        node = URIRef(BASE + "agent:" + agent.id)
        assert set(graph.objects(node, RDFS.label)) == {Literal(agent.name)}
        assert set(graph.objects(node, HI.hasRoleConcept)) == {HINT[r] for r in agent.roles}

    ontology = Graph().parse(ONTOLOGY_DIR / "hi-ontology.ttl", format="turtle")
    for _, predicate, obj in graph:
        if str(predicate).startswith(str(HI)):
            assert any((predicate, RDF.type, kind) in ontology for kind in (OWL.ObjectProperty, OWL.DatatypeProperty))
        if predicate == RDF.type:
            assert (obj, RDF.type, OWL.Class) in ontology
    assert all(str(subject).startswith("urn:hi-app:") for subject in graph.subjects())
    assert not any(isinstance(term, BNode) for triple in graph for term in triple)


def test_three_agents_preserve_identities_even_with_shared_names_and_roles(payload):
    payload["agents"][0]["name"] = "Alex"
    payload["agents"].append({
        "id": "second-human",
        "name": "Alex",
        "kind": "human",
        "roles": ["HumanUserRole", "ClinicianRole"],
    })
    scenario = Scenario.model_validate(payload)
    graph = to_rdf(scenario)
    assert_conforms(graph)

    members = set(graph.objects(TEAM, HI.hasMember))
    assert members == {URIRef(BASE + "agent:" + a.id) for a in scenario.agents}
    assert len(set(graph.subjects(RDF.type, HI.HumanAgent))) == 2
    assert len(set(graph.subjects(RDF.type, HI.ArtificialAgent))) == 1
    for agent in scenario.agents:
        node = URIRef(BASE + "agent:" + agent.id)
        assert set(graph.objects(node, RDFS.label)) == {Literal(agent.name)}
        assert set(graph.objects(node, HI.hasRoleConcept)) == {HINT[r] for r in agent.roles}


def test_minimum_one_task_and_optional_domain(payload):
    payload.pop("capabilities")  # Capabilities remain optional, including for tasks.
    payload.pop("executions")
    payload.pop("experiments")
    payload.pop("evaluations")
    payload.pop("interactions")
    payload["tasks"] = payload["tasks"][:1]
    del payload["use_case"]["domain"]
    graph = to_rdf(Scenario.model_validate(payload))
    assert_conforms(graph)
    assert len(set(graph.subjects(RDF.type, HI.Task))) == 1
    assert not list(graph.triples((None, HI.hasDomainConcept, None)))


@pytest.mark.parametrize("name", [
    'Zoë "Researcher"\nSecond line \\ ☃',
    "Alex\u0085with\u2028Unicode\u2029separators",
])
def test_json_round_trip_order_independence_and_valid_rdf(payload, name):
    payload["agents"][0]["name"] = name
    payload["agents"][0]["roles"].append("ClinicianRole")
    scenario = Scenario.model_validate(payload)
    output = to_ntriples(to_rdf(scenario))
    assert Scenario.model_validate_json(scenario.model_dump_json()) == scenario
    parsed = Graph().parse(data=output, format="nt")
    assert set(parsed) == set(to_rdf(scenario))
    assert_conforms(parsed)
    payload["tasks"].reverse()
    payload["agents"].reverse()
    for agent in payload["agents"]:
        agent["roles"].reverse()
    assert to_ntriples(to_rdf(Scenario.model_validate(payload))) == output


def test_names_and_roles_do_not_determine_identity(payload):
    before = to_rdf(Scenario.model_validate(payload))
    payload["agents"][0]["name"] = "Renamed user"
    payload["agents"][0]["roles"] = ["ClinicianRole"]
    after = to_rdf(Scenario.model_validate(payload))
    assert set(before.objects(TEAM, HI.hasMember)) == set(after.objects(TEAM, HI.hasMember))
    node = URIRef(BASE + "agent:human-user")
    assert (node, RDFS.label, Literal("Renamed user")) in after
    assert set(after.objects(node, HI.hasRoleConcept)) == {HINT.ClinicianRole}


def test_ids_are_scoped_by_entity_kind_and_scenario(payload):
    original_task = payload["tasks"][0]["id"]
    original_agent = payload["agents"][0]["id"]
    for field in ("use_case", "goal"):
        payload[field]["id"] = "same"
    payload["tasks"][0]["id"] = "same"
    payload["agents"][0]["id"] = "same"
    payload["capabilities"][0]["id"] = "same"
    payload["executions"][0]["id"] = "same"
    payload["experiments"][0]["id"] = "same"
    payload["evaluations"][0]["id"] = "same"
    payload["interactions"][0]["id"] = "same"
    for interaction in payload["interactions"]:
        interaction["agents"] = ["same" if id == original_agent else id for id in interaction["agents"]]
        interaction["executions"] = ["same" if id == "data-collection" else id for id in interaction["executions"]]
    for evaluation in payload["evaluations"]:
        if evaluation["experiment"] == "data-collection-quality":
            evaluation["experiment"] = "same"
        evaluation["executions"] = ["same" if id == "data-collection" else id for id in evaluation["executions"]]
    for capability in payload["capabilities"]:
        capability["agents"] = ["same" if id == original_agent else id for id in capability["agents"]]
        capability["tasks"] = ["same" if id == original_task else id for id in capability["tasks"]]
    for execution in payload["executions"]:
        if execution["agent"] == original_agent:
            execution["agent"] = "same"
        if execution["task"] == original_task:
            execution["task"] = "same"
    graph = to_rdf(Scenario.model_validate(payload))
    assert {URIRef(BASE + kind + ":same") for kind in ("use-case", "goal", "task", "agent", "capability", "execution", "experiment", "evaluation", "interaction")} <= set(graph.subjects())
    assert_conforms(graph)
    payload["id"] = "other-scenario"
    other = to_rdf(Scenario.model_validate(payload))
    assert set(graph.subjects()).isdisjoint(other.subjects())


@pytest.mark.parametrize("field", ["agents", "tasks", "capabilities", "executions", "experiments", "evaluations", "interactions"])
def test_duplicate_ids_are_rejected(payload, field):
    payload[field].append(dict(payload[field][0]))
    with pytest.raises(ValidationError, match="Duplicate"):
        Scenario.model_validate(payload)


@pytest.mark.parametrize("kind", ["human", "artificial"])
def test_requires_both_agent_kinds(payload, kind):
    for agent in payload["agents"]:
        agent["kind"] = kind
    with pytest.raises(ValidationError, match="human and an artificial"):
        Scenario.model_validate(payload)


@pytest.mark.parametrize(("path", "value"), [
    (("tasks",), []),
    (("agents",), []),
    (("agents", 0, "roles"), []),
    (("agents", 0, "kind"), "robot"),
    (("agents", 0, "name"), " \n "),
    (("agents", 0, "name"), 123),
    (("id",), "https://w3id.org/hi-ontology/scenarios/new/"),
    (("id",), "s1:agent:injected"),
    (("id",), "s1\n"),
    (("agents", 0, "id"), ""),
    (("use_case", "concept"), "hint:PersonalAssistantUseCase"),
    (("use_case", "extra_field"), "unhandled data"),
    (("extra_field",), "unhandled data"),
    (("goal",), None),
])
def test_invalid_structure_is_rejected(payload, path, value):
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)


def test_single_agent_is_rejected(payload):
    payload["agents"] = payload["agents"][:1]
    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)


@pytest.mark.parametrize(("field", "concept", "error"), [
    ("use_case", "MadeUpUseCase", "Unknown HINT"),
    ("use_case", "HumanUserRole", "not a UseCase"),
    ("goal", "DataCollectionTask", "not a Goal"),
])
def test_invalid_concepts_are_rejected(payload, field, concept, error):
    payload[field]["concept"] = concept
    with pytest.raises(ValueError, match=error):
        to_rdf(Scenario.model_validate(payload))


@pytest.mark.parametrize("role", ["InventedRole", "DataCollectionTask"])
def test_invalid_roles_are_rejected(payload, role):
    payload["agents"][0]["roles"] = [role]
    with pytest.raises(ValueError, match="HINT concept"):
        to_rdf(Scenario.model_validate(payload))


@pytest.mark.parametrize(("mutation", "focus", "path"), [
    ("role", URIRef(BASE + "agent:human-user"), HI.hasRoleConcept),
    ("task", URIRef(BASE + "goal:user-wellbeing"), HI.requiresTask),
    ("human", TEAM, HI.hasMember),
    ("member", TEAM, HI.hasMember),
])
def test_existing_shacl_catches_missing_core_facts(payload, mutation, focus, path):
    graph = to_rdf(Scenario.model_validate(payload))
    human = URIRef(BASE + "agent:human-user")
    if mutation == "role":
        graph.remove((human, HI.hasRoleConcept, None))
    elif mutation == "task":
        graph.remove((None, HI.requiresTask, None))
    elif mutation == "human":
        graph.remove((human, RDF.type, HI.HumanAgent))
    elif mutation == "member":
        graph.remove((TEAM, HI.hasMember, human))
    conforms, report_graph, _ = validate_rdf(graph)
    assert not conforms
    assert any(
        (result, SH.focusNode, focus) in report_graph
        and (result, SH.resultPath, path) in report_graph
        for result in report_graph.subjects(RDF.type, SH.ValidationResult)
    )


def test_cli_output_is_stable_across_processes_and_working_directories(tmp_path):
    outputs = []
    for seed in ("1", "2"):
        output = tmp_path / f"s1-{seed}.nt"
        result = subprocess.run(
            [sys.executable, "-m", "hi_scenario", str(ROOT / "examples" / "s1.json"), "--output", str(output)],
            cwd=tmp_path,
            env={**os.environ, "PYTHONPATH": str(ROOT), "PYTHONHASHSEED": seed},
            capture_output=True, text=True, check=True,
        )
        assert "SHACL conforms: 123 triples" in result.stderr
        assert result.stdout == ""
        outputs.append(output.read_bytes())
    assert outputs[0] == outputs[1]
    assert_conforms(Graph().parse(data=outputs[0], format="nt"))


def test_cli_rejects_bad_input_before_writing_output(payload, tmp_path):
    payload["agents"][0]["roles"] = ["MadeUpRole"]
    source = tmp_path / "invalid.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    output = tmp_path / "result.nt"
    result = subprocess.run(
        [sys.executable, "-m", "hi_scenario", str(source), "--output", str(output)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "Unknown HINT concept: MadeUpRole" in result.stderr
    assert not output.exists()
