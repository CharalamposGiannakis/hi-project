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


def test_s1_preserves_every_research_triple_plus_only_seven_labels_and_passes_shacl(payload):
    scenario = Scenario.model_validate(payload)
    graph = to_rdf(scenario)
    assert_conforms(graph)

    # Extract all S1 assertions, including incoming links and every predicate.
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
    def is_s1(term):
        return isinstance(term, URIRef) and str(term).startswith(str(s1))

    original = {(s, p, o) for s, p, o in source if is_s1(s) or is_s1(o)}
    assert len(original) == 120
    original_entities = {term for s, _, o in original for term in (s, o) if is_s1(term)}
    assert len(identities) == len(set(identities.values())) == 23
    assert set(identities) == original_entities
    assert set(identities.values()) == set(graph.subjects())
    for original_node, application_node in identities.items():
        assert set(source.objects(original_node, RDF.type)) == set(graph.objects(application_node, RDF.type))

    # Compare RDF terms directly: literal text, datatype, and language all matter.
    expected = {
        (identities.get(s, s), p, identities.get(o, o))
        for s, p, o in original
    }
    assert len(expected) == 120
    assert not expected - set(graph)
    additional = set(graph) - expected
    expected_labels = {
        (URIRef(BASE + entity), RDFS.label, Literal(name))
        for entity, name in {
            "use-case:personal-assistant": "Personal assistant HI system",
            "goal:user-wellbeing": "Maintain and improve user wellbeing",
            "task:data-collection": "Collect self-reports and sensor activity data",
            "task:conflict-resolution": "Resolve inconsistencies between reported and sensed data",
            "task:explanation": "Provide explanations to maintain trust and engagement",
            "agent:human-user": "Human user",
            "agent:ai-assistant": "AI assistant",
        }.items()
    }
    assert len(additional) == 7
    assert additional == expected_labels
    assert len(graph) == 127
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


@pytest.mark.parametrize("description", [None, "English description with quotes: \"example\".\nSecond line."])
def test_goal_and_task_descriptions_preserve_labels_and_json(payload, description):
    payload["goal"]["description"] = description
    for task in payload["tasks"]:
        task["description"] = description
    scenario = Scenario.model_validate(payload)
    assert Scenario.model_validate_json(scenario.model_dump_json()) == scenario
    graph = to_rdf(scenario)
    for kind, entity in [("goal", scenario.goal)] + [("task", task) for task in scenario.tasks]:
        node = URIRef(BASE + kind + ":" + entity.id)
        assert set(graph.objects(node, RDFS.label)) == {Literal(entity.name)}
        assert set(graph.objects(node, RDFS.comment)) == (
            set() if description is None else {Literal(description, lang="en")}
        )
    assert set(Graph().parse(data=to_ntriples(graph), format="nt")) == set(graph)
    assert_conforms(graph)


def test_legacy_goal_and_tasks_without_descriptions_keep_the_previous_rdf(payload):
    complete = to_rdf(Scenario.model_validate(payload))
    payload["goal"].pop("description")
    for task in payload["tasks"]:
        task.pop("description")
    scenario = Scenario.model_validate(payload)
    assert scenario.goal.description is None
    assert all(task.description is None for task in scenario.tasks)
    legacy = to_rdf(scenario)
    nodes = {URIRef(BASE + "goal:" + scenario.goal.id)} | {URIRef(BASE + "task:" + task.id) for task in scenario.tasks}
    assert set(legacy) == {t for t in complete if not (t[0] in nodes and t[1] == RDFS.comment)}
    assert len(legacy) == 123


@pytest.mark.parametrize("path", [("goal",), ("tasks", 0)])
@pytest.mark.parametrize("description", ["", " \n ", 123, False, {}])
def test_goal_and_task_descriptions_reject_blank_or_non_text(payload, path, description):
    entity = payload
    for key in path:
        entity = entity[key]
    entity["description"] = description
    with pytest.raises(ValidationError):
        Scenario.model_validate(payload)


@pytest.mark.parametrize("path", [("use_case",), ("agents", 0)])
def test_descriptions_do_not_extend_other_named_entities(payload, path):
    entity = payload
    for key in path:
        entity = entity[key]
    entity["description"] = "Outside this increment"
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Scenario.model_validate(payload)


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
        assert "SHACL conforms: 127 triples" in result.stderr
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
