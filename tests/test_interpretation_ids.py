from uuid import UUID

from hi_scenario.interpretation import assemble_interpretation
from hi_scenario.model import Scenario


def proposal(scenario, diagnostics=()):
    return assemble_interpretation(
        {"scenario": scenario, "diagnostics": list(diagnostics)}, "test-model", "test-version",
        prompt_sha256="0" * 64,
    )


def test_generated_ids_preserve_explicit_references_to_unique_names_and_concepts():
    scenario = {
        "use_case": {"name": "Care assistant", "concept": "PersonalAssistantUseCase"},
        "goal": {"name": "Maintain wellbeing", "concept": "UserWellbeingGoal", "required_tasks": ["collect-data"]},
        "tasks": [{"name": "Collect data", "concept": "DataCollectionTask"}],
        "agents": [
            {"name": "Human user", "kind": "human", "roles": ["HumanUserRole"]},
            {"name": "AI assistant", "kind": "artificial", "roles": ["AIAssistantRole"]},
        ],
        "capabilities": [{"concept": "SelfReportingCapability", "agents": ["Human user"], "tasks": ["DataCollectionTask"]}],
        "executions": [{"concept": "DataCollectionTaskExecution", "task": "Collect Data", "agent": "human_user"}],
        "experiments": [{
            "concept": "TransparencyTrustExperiment",
            "null_hypothesis": "Transparency does not affect trust.",
            "alternative_hypothesis": "Transparency increases trust.",
        }],
        "evaluations": [{
            "concept": "TransparencyEvaluation", "experiment": "TransparencyTrustExperiment",
            "executions": ["DataCollectionTaskExecution"],
        }],
        "interactions": [{
            "intent": "ExplanationIntent", "modality": "VerbalDialogueModality",
            "agents": ["human user", "ai-assistant"], "executions": ["DataCollectionTaskExecution"],
        }],
    }
    findings = [{"kind": "missing_information", "path": path, "message": "ID not supplied."}
                for path in ("scenario.id", "goal.id", "scenario.agents[0].id", "tasks.0.id")]
    result = proposal(scenario, findings)
    candidate = Scenario.model_validate(result.scenario)

    assert result.interpretation.status == "complete"
    assert result.interpretation.diagnostics == []
    task, = candidate.tasks
    human, assistant = candidate.agents
    execution, = candidate.executions
    experiment, = candidate.experiments
    capability, = candidate.capabilities
    evaluation, = candidate.evaluations
    interaction, = candidate.interactions
    assert all(UUID(identifier).version == 4 for identifier in (
        candidate.id, candidate.use_case.id, candidate.goal.id, task.id, human.id, assistant.id,
        execution.id, experiment.id, capability.id, evaluation.id, interaction.id,
    ))
    assert candidate.goal.required_tasks == capability.tasks == (task.id,)
    assert capability.agents == (human.id,)
    assert (execution.task, execution.agent) == (task.id, human.id)
    assert evaluation.experiment == experiment.id
    assert evaluation.executions == interaction.executions == (execution.id,)
    assert interaction.agents == (human.id, assistant.id)


def test_ambiguous_references_remain_unresolved_and_explicit_ids_take_precedence():
    result = proposal({
        "goal": {"required_tasks": ["ambiguous", "same_label", "verbatim", "DataCollectionTask"]},
        "tasks": [
            {"id": "ambiguous", "name": "Ambiguous", "concept": "DataCollectionTask"},
            {"id": "ambiguous", "name": "Another task", "concept": "ConflictResolutionTask"},
            {"name": "Same label", "concept": "ExplanationTask"},
            {"id": "existing", "name": "Same-label", "concept": "DataCollectionTask"},
            {"id": "verbatim", "name": "Unique existing", "concept": "DataCollectionTask"},
            {"name": "Verbatim", "concept": "DataCollectionTask"},
        ],
    })
    draft = result.scenario
    assert len({task["id"] for task in draft["tasks"]}) == 6
    assert draft["goal"]["required_tasks"] == ["ambiguous", "same_label", "verbatim", "DataCollectionTask"]
    unresolved = [item.message for item in result.interpretation.diagnostics
                  if item.kind == "technical_validation" and item.path == "goal.required_tasks"]
    assert len(unresolved) == 3
    assert all(any(repr(alias) in message for message in unresolved)
               for alias in ("ambiguous", "same_label", "DataCollectionTask"))


def test_a_sole_target_without_a_matching_name_or_concept_is_never_guessed():
    result = proposal({
        "goal": {"required_tasks": ["missing-target"]},
        "tasks": [{"description": "Missing target"}],
    }, [{"kind": "missing_information", "path": "goal.required_tasks", "message": "The goal link is unresolved."}])
    draft = result.scenario
    assert draft["goal"]["required_tasks"] == ["missing-target"]
    assert draft["tasks"][0]["id"] != "missing-target"
    diagnostics = result.interpretation.diagnostics
    assert any(note.kind == "missing_information" and note.path == "goal.required_tasks" for note in diagnostics)
    assert any(note.kind == "technical_validation" and note.path == "goal.required_tasks" for note in diagnostics)
