"""Opt-in semantic evaluation of Nebula using three public example-derived descriptions."""

import os
from collections import Counter
from time import monotonic

import pytest

from hi_scenario import nebula
from hi_scenario.interpretation import InterpretationRequest, assemble_interpretation
from hi_scenario.model import Scenario
from hi_scenario.rdf import to_rdf
from hi_scenario.validation import validate_rdf


LIVE_ENABLED = os.getenv("HI_NEBULA_LIVE") == "1"
S2_REPEATS = int(os.getenv("HI_NEBULA_S2_REPEATS", "1")) if LIVE_ENABLED else 1
if S2_REPEATS < 1:
    raise ValueError("HI_NEBULA_S2_REPEATS must be a positive integer.")

pytestmark = pytest.mark.skipif(
    not LIVE_ENABLED, reason="Set HI_NEBULA_LIVE=1 to evaluate Nebula",
)


def _interpret(case, description):
    submitted = InterpretationRequest(description=description)
    start = monotonic()
    try:
        model, raw = nebula.request_interpretation(submitted.description)
    except nebula.NebulaError as error:
        if error.status_code == 503:
            pytest.fail("Set NEBULA_API_KEY in the environment or .env.nebula for live tests.", pytrace=False)
        pytest.fail(str(error), pytrace=False)
    result = assemble_interpretation(
        raw, model, nebula.PROMPT_VERSION, prompt_sha256=nebula.system_prompt_sha256(),
    )
    findings = result.interpretation
    candidate = result.scenario or {}
    counts = Counter(item.kind for item in findings.diagnostics)
    tasks = candidate.get("tasks", [])
    task_concepts = {task["id"]: task.get("concept") for task in tasks}
    required_tasks = candidate.get("goal", {}).get("required_tasks", [])
    print(
        f"\n{case} ({monotonic() - start:.1f}s, model {findings.model}, "
        f"prompt {findings.prompt_version}, SHA-256 {findings.prompt_sha256}): {findings.status}; "
        f"{len(tasks)} tasks, {len(candidate.get('agents', []))} agents, "
        f"{len(candidate.get('executions', []))} executions; diagnostic counts {dict(sorted(counts.items()))}"
    )
    print(f"  Task inventory: {task_concepts}; goal-required task IDs: {required_tasks}", flush=True)
    assert result.scenario is not None, f"{case} produced no editable candidate."
    return result.scenario, findings


def test_live_s1_preserves_supported_facts_and_separates_capability_from_execution():
    candidate, _ = _interpret("S1 complete", {
        "use_case": "A personal assistant in the health and lifestyle domain supports one human user.",
        "goal": "The team's shared goal is to maintain and improve user wellbeing.",
        "tasks": (
            "The goal requires two tasks: collecting self-reports and sensor activity data, and resolving "
            "inconsistencies between reported and sensed data. Providing explanations is another task in the "
            "inventory, but it is not required for this goal."
        ),
        "agents": "The two team members are the human user and the AI assistant. Each acts in that role.",
        "context": "The team operates in a health-monitoring setting. Sensor noise affects it and privacy constrains the setting.",
        "team_constraints": "Separately, transparency is an obligation on the team as a whole.",
        "capabilities": "The AI assistant has a sensing capability that enables the data-collection task.",
        "executions": (
            "In the recorded trial, only the human user carried out the data collection. The AI assistant "
            "carried out the conflict resolution using argumentation reasoning. No explanation was performed."
        ),
    })
    scenario = Scenario.model_validate(candidate)
    assert scenario.use_case.concept == "PersonalAssistantUseCase"
    assert scenario.use_case.domain == "HealthAndLifestyleDomain"
    assert scenario.goal.concept == "UserWellbeingGoal"
    assert {agent.kind: agent.roles for agent in scenario.agents} == {
        "human": ("HumanUserRole",), "artificial": ("AIAssistantRole",),
    }
    assert len(scenario.agents) == 2
    tasks = {task.id: task.concept for task in scenario.tasks}
    assert set(tasks.values()) == {"DataCollectionTask", "ConflictResolutionTask", "ExplanationTask"}
    assert {tasks[task_id] for task_id in scenario.goal.required_tasks or ()} == {
        "DataCollectionTask", "ConflictResolutionTask",
    }
    assert scenario.context is not None
    assert scenario.context.concept == "HealthMonitoringContext"
    assert scenario.context.phenomena == ("SensorNoisePhenomenon",)
    assert scenario.context.constraints == ("PrivacyConstraint",)
    assert scenario.team_constraints == ("TransparencyConstraint",)
    agents = {agent.id: agent.kind for agent in scenario.agents}
    assert [(capability.concept, tuple(agents[key] for key in capability.agents),
             tuple(tasks[key] for key in capability.tasks)) for capability in scenario.capabilities] == [
        ("SensingCapability", ("artificial",), ("DataCollectionTask",)),
    ]
    assert {(item.concept, tasks[item.task], agents[item.agent], item.method) for item in scenario.executions} == {
        ("DataCollectionTaskExecution", "DataCollectionTask", "human", None),
        ("ConflictResolutionTaskExecution", "ConflictResolutionTask", "artificial", "ArgumentationReasoningMethod"),
    }
    assert len(scenario.executions) == 2
    assert not (scenario.interactions or scenario.experiments or scenario.evaluations)
    conforms, _, report = validate_rdf(to_rdf(scenario))
    assert conforms, report


def test_live_s4_keeps_known_partial_facts_without_inventing_an_artificial_member_or_task_link():
    candidate, findings = _interpret("S4 incomplete", {
        "use_case": "An early autonomous tutoring study in education.",
        "goal": "The study aims to support effective learning. Required tasks for that goal have not been decided.",
        "tasks": "We have identified one possible task: reconstruct the learner's study trajectory from self-reported history and logs.",
        "agents": "The only identified participant is a human learner. We have not identified any artificial team member.",
    })
    assert findings.status == "incomplete"
    assert candidate["use_case"]["concept"] == "AutonomousTutoringUseCase"
    assert candidate["goal"]["concept"] == "EffectiveLearningGoal"
    assert not candidate["goal"].get("required_tasks")
    assert [task["concept"] for task in candidate["tasks"]] == ["ReconstructTrajectoryTask"]
    assert [(agent["kind"], agent["roles"]) for agent in candidate["agents"]] == [("human", ["LearnerRole"])]
    assert not candidate.get("executions")
    missing = {item.path for item in findings.diagnostics if item.kind == "missing_information"}
    assert "agents" in missing and "goal.required_tasks" in missing


@pytest.mark.parametrize("run", range(1, S2_REPEATS + 1))
def test_live_s2_reports_unrepresentable_direct_interaction_goal_link_and_assignment(run):
    candidate, findings = _interpret(f"S2 unsupported relationships, run {run}/{S2_REPEATS}", {
        "use_case": "Collaborative manipulation in industrial robotics.",
        "goal": "The team aims to retrieve a tool safely.",
        "tasks": (
            "There are three distinct tasks: unlock the cabinet, open the cabinet, and retrieve the tool. "
            "All three are required by the safe retrieval goal."
        ),
        "agents": "The team is a human technician in the fine manipulator role and a robot manipulator in the risk operator role.",
        "executions": (
            "The researchers want to capture the formal task assignment: the technician was assigned to unlock "
            "the cabinet. The assignment itself is a documented staffing relationship. No task execution was recorded."
        ),
        "interactions": (
            "The robot and technician engage in a verbal dialogue to explain the risk. The researchers want to assert "
            "that the explanatory interaction itself is directly directed toward the safe retrieval goal. The dialogue "
            "is independent of task executions."
        ),
    })
    assert findings.status == "incomplete"
    assert candidate["use_case"]["concept"] == "CollaborativeManipulationUseCase"
    assert candidate["goal"]["concept"] == "SafeRetrievalGoal"
    assert not candidate.get("executions")
    assert not candidate.get("capabilities")
    (interaction,) = candidate["interactions"]
    assert interaction["intent"] == "ExplanationIntent"
    assert interaction["modality"] == "VerbalDialogueModality"
    assert set(interaction["agents"]) == {agent["id"] for agent in candidate["agents"]}
    assert not interaction.get("executions")
    messages = [item.message.casefold() for item in findings.diagnostics if item.kind == "unsupported_relationship"]
    assert any(("interaction" in message or "dialogue" in message) and "goal" in message for message in messages)
    assert any("assign" in message for message in messages), messages
    tasks = {task["id"]: task["concept"] for task in candidate["tasks"]}
    assert set(tasks.values()) == {"UnlockCabinetTask", "OpenCabinetTask", "RetrieveToolTask"}
    assert set(candidate["goal"]["required_tasks"]) == set(tasks)
    conforms, _, report = validate_rdf(to_rdf(Scenario.model_validate(candidate)))
    assert conforms, report
