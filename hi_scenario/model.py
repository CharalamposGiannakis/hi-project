"""The shared JSON representation for one use case, team, and goal."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


Identifier = Annotated[str, StringConstraints(strict=True, pattern=r"^[a-z0-9][a-z0-9_-]*$")]
Name = Annotated[str, StringConstraints(strict=True, pattern=r"\S")]
Concept = Annotated[str, StringConstraints(strict=True, pattern=r"^[A-Za-z][A-Za-z0-9]*$")]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NamedEntity(Record):
    id: Identifier
    name: Name


class UseCase(NamedEntity):
    concept: Concept
    domain: Concept | None = None


class Goal(NamedEntity):
    concept: Concept
    description: Name | None = None


class Task(NamedEntity):
    concept: Concept
    description: Name | None = None


class Agent(NamedEntity):
    kind: Literal["human", "artificial"]
    roles: tuple[Concept, ...] = Field(min_length=1)


class Context(Record):
    concept: Concept
    phenomena: tuple[Concept, ...] = ()
    constraints: tuple[Concept, ...] = ()
    description: Name | None = None


class Capability(Record):
    id: Identifier
    concept: Concept
    agents: tuple[Identifier, ...] = ()
    tasks: tuple[Identifier, ...] = ()


class Execution(Record):
    id: Identifier
    concept: Concept
    task: Identifier
    agent: Identifier
    method: Concept | None = None


class Experiment(Record):
    id: Identifier
    concept: Concept
    metrics: tuple[Concept, ...] = ()
    null_hypothesis: Name
    alternative_hypothesis: Name
    hypothesis_language: Literal["en"] | None = None
    description: Name | None = None


class Evaluation(Record):
    id: Identifier
    concept: Concept
    metrics: tuple[Concept, ...] = ()
    experiment: Identifier
    executions: tuple[Identifier, ...] = ()
    description: Name | None = None


class Interaction(Record):
    id: Identifier
    intent: Concept
    modality: Concept
    agents: tuple[Identifier, ...] = Field(min_length=2)
    executions: tuple[Identifier, ...] = ()
    description: Name | None = None

    @model_validator(mode="after")
    def check_distinct_references(self) -> Self:
        for label, references in (("agent", self.agents), ("execution", self.executions)):
            if len(references) != len(set(references)):
                raise ValueError(f"Duplicate interaction {label} references are not allowed")
        return self


class Scenario(Record):
    # IDs are assigned by the application and retained across edits.
    id: Identifier
    use_case: UseCase
    goal: Goal
    tasks: tuple[Task, ...] = Field(min_length=1)
    agents: tuple[Agent, ...] = Field(min_length=2)
    context: Context | None = None
    capabilities: tuple[Capability, ...] = ()
    executions: tuple[Execution, ...] = ()
    experiments: tuple[Experiment, ...] = ()
    evaluations: tuple[Evaluation, ...] = ()
    interactions: tuple[Interaction, ...] = ()

    @model_validator(mode="after")
    def check_team_and_identities(self) -> Self:
        for label, entities in (
            ("task", self.tasks), ("agent", self.agents),
            ("capability", self.capabilities), ("execution", self.executions),
            ("experiment", self.experiments), ("evaluation", self.evaluations),
            ("interaction", self.interactions),
        ):
            ids = [entity.id for entity in entities]
            if len(ids) != len(set(ids)):
                raise ValueError(f"Duplicate {label} IDs are not allowed")
        if {agent.kind for agent in self.agents} != {"human", "artificial"}:
            raise ValueError("A team must include a human and an artificial agent")
        for capability in self.capabilities:
            for label, references, entities in (
                ("agent", capability.agents, self.agents),
                ("task", capability.tasks, self.tasks),
            ):
                unknown = set(references) - {entity.id for entity in entities}
                if unknown:
                    raise ValueError(f"Capability {capability.id} references unknown {label} IDs: {', '.join(sorted(unknown))}")
        for execution in self.executions:
            for label, reference, entities in (
                ("agent", execution.agent, self.agents), ("task", execution.task, self.tasks),
            ):
                if reference not in {entity.id for entity in entities}:
                    raise ValueError(f"Execution {execution.id} references unknown {label} ID: {reference}")
        for evaluation in self.evaluations:
            if evaluation.experiment not in {experiment.id for experiment in self.experiments}:
                raise ValueError(f"Evaluation {evaluation.id} references unknown experiment ID: {evaluation.experiment}")
            unknown = set(evaluation.executions) - {execution.id for execution in self.executions}
            if unknown:
                raise ValueError(f"Evaluation {evaluation.id} references unknown execution IDs: {', '.join(sorted(unknown))}")
        for interaction in self.interactions:
            for label, references, entities in (
                ("agent", interaction.agents, self.agents),
                ("execution", interaction.executions, self.executions),
            ):
                unknown = set(references) - {entity.id for entity in entities}
                if unknown:
                    raise ValueError(f"Interaction {interaction.id} references unknown {label} IDs: {', '.join(sorted(unknown))}")
        return self
