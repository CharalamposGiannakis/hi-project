"""Select named-graph scopes and answer predefined competency questions."""

import os
from functools import cache
from pathlib import Path
from typing import Literal, Self
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from rdflib import Graph

from .explorer_concepts import CONCEPT_COLUMNS, build_concept_query, parse_concept_rows
from .explorer_queries import EXPLORER_QUESTIONS, build_explorer_query, parse_explorer_rows
from .graphdb import GraphDBError, GraphDBStore, _invalid_response, _text, _value, scenario_graph_iri
from .model import Concept, Identifier, Scenario
from .rdf import to_rdf
from .vocabulary import concepts


Scope = Literal["draft", "shared", "combined"]
SharedSource = Literal["approved", "reference"]
QuestionId = Literal["cq1", "cq2", "cq5", "cq8", "cq11"]
_EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class ScopeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: Scope
    scenario: Scenario | None = None
    shared_scenario_id: Identifier | None = None

    @model_validator(mode="after")
    def check_scope(self) -> Self:
        if self.scope == "shared" and self.scenario is not None:
            raise ValueError("Only include a current scenario when querying it.")
        if self.scope != "shared" and self.scenario is None:
            raise ValueError("A current scenario is required for this scope.")
        if self.scope == "draft" and self.shared_scenario_id is not None:
            raise ValueError("A shared scenario requires a shared or combined scope.")
        return self


class ExplorerRequest(ScopeRequest):
    question_id: QuestionId
    parameters: dict[str, Concept] = Field(default_factory=dict)


class ConceptExplorationRequest(ScopeRequest):
    category: Literal["Capability", "Constraint", "Method", "Metric"] | None = None
    concept: Concept | None = None
    compare: bool = False

    @model_validator(mode="after")
    def check_comparison(self) -> Self:
        if self.compare and (self.scope != "combined" or self.shared_scenario_id is None):
            raise ValueError("Choose your current scenario and one shared scenario for comparison.")
        if self.concept is not None and self.category is None:
            raise ValueError("Choose a category when filtering by a HINT concept.")
        return self


class ScenarioSource(BaseModel):
    id: str
    scenario_id: str
    name: str
    description: str | None
    publication_status: Literal["approved", "reference", "provisional"]
    graph_iri: str


class QuestionOption(BaseModel):
    id: QuestionId
    label: str
    description: str
    parameters: list[dict[str, str]]


class ExplorerCatalog(BaseModel):
    shared_source: SharedSource
    scenarios: list[ScenarioSource]
    questions: list[QuestionOption]
    warnings: list[str] = Field(default_factory=list)


class ExplorerRow(BaseModel):
    source_id: str
    values: dict[str, str | None]
    evidence: list[dict[str, str]]


class ExplorerNotice(BaseModel):
    code: str
    message: str
    source_id: str | None = None


class ExplorerResult(BaseModel):
    sources: list[ScenarioSource]
    columns: list[dict[str, str]]
    rows: list[ExplorerRow]
    truncated: bool
    notices: list[ExplorerNotice] = Field(default_factory=list)


def validate_parameters(request: ExplorerRequest) -> None:
    allowed = {item["id"]: item["category"] for item in EXPLORER_QUESTIONS[request.question_id]["parameters"]}
    for name, value in request.parameters.items():
        if name not in allowed or not any(concept["id"] == value for concept in concepts(allowed[name])):
            raise GraphDBError(422, "invalid_request", "Choose a supported HINT concept for this question.")


def _local_source(
    scenario: Scenario, status: Literal["reference", "provisional"], graph_iri: str,
) -> ScenarioSource:
    return ScenarioSource(
        id=f"{status}:{scenario.id}", scenario_id=scenario.id, name=scenario.use_case.name,
        description=scenario.goal.description or (scenario.context and scenario.context.description),
        publication_status=status, graph_iri=graph_iri,
    )


@cache
def _reference_scenarios() -> dict[str, Scenario]:
    scenarios = {}
    for number in range(1, 8):
        scenario = Scenario.model_validate_json((_EXAMPLES / f"s{number}.json").read_bytes())
        scenarios[scenario.id] = scenario
    return scenarios


def configured_approved_graphs() -> dict[str, str]:
    approved = {}
    try:
        for entry in os.getenv("GRAPHDB_APPROVED_SCENARIO_IDS", "").split(","):
            if scenario_id := entry.strip():
                approved[scenario_graph_iri(scenario_id)] = scenario_id
    except ValidationError as exc:
        raise GraphDBError(503, "graphdb_configuration", "The approved scenario list is invalid.") from exc
    return approved


def _approved_sources(store: GraphDBStore) -> list[ScenarioSource]:
    approved = configured_approved_graphs()
    if not approved:
        return []

    graphs = " ".join(f"<{iri}>" for iri in approved)
    result = store.explore(f"""
        PREFIX hi: <https://w3id.org/hi-ontology#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        SELECT DISTINCT ?graph ?name ?description ?goalDescription ?contextDescription WHERE {{
            VALUES ?graph {{ {graphs} }}
            GRAPH ?graph {{
                ?useCase a hi:UseCase ; hi:hasHITeam ?team .
                OPTIONAL {{ ?useCase rdfs:label ?name }}
                OPTIONAL {{ ?useCase rdfs:comment ?description }}
                OPTIONAL {{ ?team hi:hasGoal/rdfs:comment ?goalDescription }}
                OPTIONAL {{ ?team hi:operatesInContext/rdfs:comment ?contextDescription }}
            }}
        }}
    """)
    fields = ("name", "description", "goalDescription", "contextDescription")
    metadata: dict[str, dict[str, str | None]] = {}
    try:
        bindings = result["results"]["bindings"]
        if not isinstance(bindings, list):
            raise ValueError("Expected SPARQL bindings")
        for row in bindings:
            iri = _value(row, "graph", uri=True, required=True)
            if iri not in approved:
                raise ValueError("Result is outside the approved graph scope")
            values = metadata.setdefault(iri, dict.fromkeys(fields))
            for field in fields:
                values[field] = _text(values[field], _value(row, field))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise _invalid_response() from exc
    return [
        ScenarioSource(
            id=f"approved:{approved[iri]}", scenario_id=approved[iri], name=values["name"] or approved[iri],
            description=values["description"] or values["goalDescription"] or values["contextDescription"],
            publication_status="approved", graph_iri=iri,
        )
        for iri, values in sorted(metadata.items())
    ]


def shared_sources(store: GraphDBStore) -> tuple[SharedSource, list[ScenarioSource], list[str]]:
    approved = _approved_sources(store)
    if approved:
        return "approved", approved, []
    warnings = []
    if configured_approved_graphs():
        warnings.append(
            "Configured approved scenario IDs resolve to no available scenario graphs. "
            "Experimental reference scenarios are being shown. "
            "The operator should verify the configuration and scientific approval."
        )
    return "reference", [
        _local_source(scenario, "reference", f"urn:hi-app:explorer:reference:{scenario.id}")
        for scenario in _reference_scenarios().values()
    ], warnings


def catalog(store: GraphDBStore) -> ExplorerCatalog:
    shared_source, scenarios, warnings = shared_sources(store)
    return ExplorerCatalog(
        shared_source=shared_source, scenarios=scenarios, warnings=warnings,
        questions=[QuestionOption(**question) for question in EXPLORER_QUESTIONS.values()],
    )


def _unlinked_interaction_notices(
    store: GraphDBStore, sources: list[ScenarioSource], staged: dict[str, Graph],
) -> list[ExplorerNotice]:
    # Query the selected graphs only. Missing links are reported without creating them.
    scopes = "\nUNION\n".join(f"""{{
        GRAPH <{source.graph_iri}> {{
            ?interaction a hi:Interaction .
            FILTER NOT EXISTS {{ ?execution hi:hasInteractionEpisode ?interaction }}
        }}
        BIND(<{source.graph_iri}> AS ?graph)
    }}""" for source in sources)
    result = store.explore(f"""
        PREFIX hi: <https://w3id.org/hi-ontology#>
        SELECT ?graph (COUNT(DISTINCT ?interaction) AS ?count)
        WHERE {{ {scopes} }}
        GROUP BY ?graph
        ORDER BY ?graph
    """, staged)
    source_ids = {source.graph_iri: source.id for source in sources}
    notices = []
    try:
        bindings = result["results"]["bindings"]
        if not isinstance(bindings, list):
            raise ValueError("Expected SPARQL bindings")
        for row in bindings:
            source_id = source_ids[_value(row, "graph", uri=True, required=True)]
            count = int(_value(row, "count", required=True))
            if count < 1:
                raise ValueError("Expected a positive interaction count")
            notices.append(ExplorerNotice(
                code="interactions_without_execution_links", source_id=source_id,
                message=(
                    f"{count} recorded interaction{'s have' if count != 1 else ' has'} no recorded link "
                    "to a task execution. CQ5 requires execution–interaction links for goal-required tasks."
                ),
            ))
    except (KeyError, TypeError, ValueError) as exc:
        raise _invalid_response() from exc
    return notices


def _query_sources(
    store: GraphDBStore, request: ScopeRequest, draft_graph: Graph | None,
) -> tuple[list[ScenarioSource], dict[str, Graph], list[ExplorerNotice]]:
    nonce = uuid4().hex
    staged: dict[str, Graph] = {}
    sources = []
    notices = []
    if request.scenario is not None and draft_graph is not None:
        iri = f"urn:hi-app:explorer:draft:{nonce}"
        sources.append(_local_source(request.scenario, "provisional", iri))
        staged[iri] = draft_graph
    if request.scope != "draft":
        kind, shared, warnings = shared_sources(store)
        notices.extend(ExplorerNotice(code="approved_graphs_unavailable", message=warning) for warning in warnings)
        if request.shared_scenario_id is not None:
            shared = [source for source in shared if source.scenario_id == request.shared_scenario_id]
            if not shared:
                raise GraphDBError(404, "scenario_not_found", "That scenario is unavailable in the shared source.")
        for source in shared:
            if kind == "reference":
                iri = f"{source.graph_iri}:{nonce}"
                source = source.model_copy(update={"graph_iri": iri})
                staged[iri] = to_rdf(_reference_scenarios()[source.scenario_id])
            sources.append(source)
    return sources, staged, notices


def answer(
    store: GraphDBStore, request: ExplorerRequest, draft_graph: Graph | None,
) -> ExplorerResult:
    sources, staged, notices = _query_sources(store, request, draft_graph)
    source_ids = {source.graph_iri: source.id for source in sources}
    query = build_explorer_query(request.question_id, list(source_ids), request.parameters)
    try:
        rows, truncated = parse_explorer_rows(request.question_id, store.explore(query, staged), list(source_ids))
        for row in rows:
            row["source_id"] = source_ids[row.pop("graph_iri")]
    except (KeyError, TypeError, ValueError) as exc:
        raise _invalid_response() from exc
    if request.question_id == "cq5":
        notices.extend(_unlinked_interaction_notices(store, sources, staged))
    return ExplorerResult(
        sources=sources, columns=EXPLORER_QUESTIONS[request.question_id]["columns"],
        rows=[ExplorerRow(**row) for row in rows], truncated=truncated, notices=notices,
    )


def explore_concepts(
    store: GraphDBStore, request: ConceptExplorationRequest, draft_graph: Graph | None,
) -> ExplorerResult:
    if request.concept is not None and not any(
        concept["id"] == request.concept for concept in concepts(request.category)
    ):
        raise GraphDBError(422, "invalid_request", "Choose a supported HINT concept for this category.")
    sources, staged, notices = _query_sources(store, request, draft_graph)
    source_ids = {source.graph_iri: source.id for source in sources}
    comparison = (sources[0].graph_iri, sources[1].graph_iri) if request.compare else None
    query = build_concept_query(list(source_ids), request.category, request.concept, comparison)
    try:
        rows, truncated = parse_concept_rows(store.explore(query, staged), list(source_ids))
        for row in rows:
            row["source_id"] = source_ids[row.pop("graph_iri")]
    except (KeyError, TypeError, ValueError) as exc:
        raise _invalid_response() from exc
    return ExplorerResult(
        sources=sources, columns=CONCEPT_COLUMNS, rows=[ExplorerRow(**row) for row in rows],
        truncated=truncated, notices=notices,
    )
