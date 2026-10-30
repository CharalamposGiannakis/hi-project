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


class Task(NamedEntity):
    concept: Concept


class Agent(NamedEntity):
    kind: Literal["human", "artificial"]
    roles: tuple[Concept, ...] = Field(min_length=1)


class Context(Record):
    concept: Concept
    phenomena: tuple[Concept, ...] = ()
    constraints: tuple[Concept, ...] = ()
    description: Name | None = None


class Scenario(Record):
    # IDs are assigned by the application and retained across edits.
    id: Identifier
    use_case: UseCase
    goal: Goal
    tasks: tuple[Task, ...] = Field(min_length=1)
    agents: tuple[Agent, ...] = Field(min_length=2)
    context: Context | None = None

    @model_validator(mode="after")
    def check_team_and_identities(self) -> Self:
        for label, entities in (("task", self.tasks), ("agent", self.agents)):
            ids = [entity.id for entity in entities]
            if len(ids) != len(set(ids)):
                raise ValueError(f"Duplicate {label} IDs are not allowed")
        if {agent.kind for agent in self.agents} != {"human", "artificial"}:
            raise ValueError("A team must include a human and an artificial agent")
        return self
