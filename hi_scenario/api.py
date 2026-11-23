"""Preview, save, and query HI scenarios through the existing semantic pipeline."""

import logging
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from rdflib import Graph

from . import explorer, nebula
from .graphdb import GraphDBError, connect_graphdb, scenario_graph_iri
from .interpretation import InterpretationRequest, InterpretationResult, assemble_interpretation
from .model import Identifier, Scenario
from .rdf import to_ntriples, to_rdf
from .validation import validate_rdf


logger = logging.getLogger(__name__)


class ShaclResult(BaseModel):
    conforms: Literal[True] = True
    report: str


class ScenarioPreview(BaseModel):
    scenario_id: str
    rdf_format: Literal["nt"] = "nt"
    rdf: str
    triple_count: int
    validation: ShaclResult


class InputIssue(BaseModel):
    location: list[str | int]
    message: str
    type: str


class SubmissionError(BaseModel):
    code: Literal[
        "invalid_request", "invalid_vocabulary", "shacl_failed", "internal_error",
        "scenario_exists", "scenario_id_reserved", "scenario_not_found", "graphdb_unavailable",
        "graphdb_invalid_response", "graphdb_configuration", "interpretation_unavailable", "interpretation_failed",
    ]
    message: str
    issues: list[InputIssue] = Field(default_factory=list)
    shacl_report: str | None = None


class ScenarioLocation(BaseModel):
    scenario_id: str
    repository_id: str
    graph_iri: str
    workbench_url: str
    workbench_graph_url: str
    use_case_iri: str
    team_iri: str


class SavedScenario(ScenarioLocation):
    triple_count: int
    validation: ShaclResult


class AgentType(BaseModel):
    iri: str
    label: str | None


class AgentRole(AgentType):
    definition: str | None


class TeamMember(BaseModel):
    iri: str
    name: str | None
    types: list[AgentType]
    roles: list[AgentRole]


class TeamComposition(ScenarioLocation):
    use_case_name: str | None
    members: list[TeamMember]


def _error(status_code: int, error: SubmissionError) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=error.model_dump(mode="json"))


app = FastAPI(title="HI scenario API", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Keep field locations and messages, without echoing payloads or exception contexts.
    issues = [
        InputIssue(location=list(error["loc"]), message=error["msg"], type=error["type"])
        for error in exc.errors()
    ]
    endpoint = request.scope.get("endpoint")
    if endpoint is interpret_scenario:
        message = "The description could not be submitted for interpretation."
    elif endpoint in (query_explorer, query_concepts):
        message = "The Explorer query is incomplete or the current scenario failed structural validation."
    else:
        message = "Scenario JSON failed structural validation."
    return _error(422, SubmissionError(code="invalid_request", message=message, issues=issues))


@app.exception_handler(GraphDBError)
async def graphdb_error(_request: Request, exc: GraphDBError) -> JSONResponse:
    return _error(exc.status_code, SubmissionError(code=exc.code, message=str(exc)))


@app.post(
    "/scenarios/interpret",
    response_model=InterpretationResult,
    responses={422: {"model": SubmissionError}, 502: {"model": SubmissionError},
               503: {"model": SubmissionError}, 504: {"model": SubmissionError}, 500: {"model": SubmissionError}},
    summary="Propose a scenario from a natural-language description",
    description="Sends the description to Nebula and returns an editable candidate and interpretation diagnostics.",
)
def interpret_scenario(request: InterpretationRequest) -> InterpretationResult | JSONResponse:
    try:
        model, output = nebula.request_interpretation(request.description)
        return assemble_interpretation(output, model, nebula.PROMPT_VERSION, prompt_sha256=nebula.system_prompt_sha256())
    except nebula.NebulaError as exc:
        code = "interpretation_unavailable" if exc.status_code == 503 else "interpretation_failed"
        return _error(exc.status_code, SubmissionError(code=code, message=str(exc)))
    except Exception:
        # Provider output and source descriptions must never be copied into server logs.
        logger.error("Scenario interpretation failed during backend processing")
        return _error(500, SubmissionError(code="internal_error", message="Interpretation failed on the server."))


def _validated_graph(scenario: Scenario) -> tuple[Graph, ShaclResult] | JSONResponse:
    try:
        try:
            graph = to_rdf(scenario)
        except ValueError as exc:
            return _error(422, SubmissionError(code="invalid_vocabulary", message=str(exc)))
        conforms, _, report = validate_rdf(graph)
        if not conforms:
            return _error(422, SubmissionError(
                code="shacl_failed", message="Generated RDF failed SHACL validation.", shacl_report=report,
            ))
        return graph, ShaclResult(report=report)
    except Exception:
        logger.exception("Scenario validation failed")
        return _error(500, SubmissionError(code="internal_error", message="Scenario processing failed on the server."))


@app.post(
    "/scenarios/preview",
    response_model=ScenarioPreview,
    responses={422: {"model": SubmissionError}, 500: {"model": SubmissionError}},
    summary="Validate a scenario and preview its RDF",
    description="Uses the existing Python model, HINT checks, and local SHACL shapes. Nothing is stored.",
)
def preview_scenario(scenario: Scenario) -> ScenarioPreview | JSONResponse:
    # A sync endpoint keeps RDF/SHACL work off the asynchronous event loop.
    try:
        prepared = _validated_graph(scenario)
        if isinstance(prepared, JSONResponse):
            return prepared
        graph, validation = prepared
        return ScenarioPreview(
            scenario_id=scenario.id,
            rdf=to_ntriples(graph),
            triple_count=len(graph),
            validation=validation,
        )
    except Exception:
        # Return server failures inside the route so CORS also applies to them.
        logger.exception("Scenario preview failed")
        return _error(500, SubmissionError(
            code="internal_error", message="Scenario processing failed on the server.",
        ))


@app.post(
    "/scenarios", status_code=201, response_model=SavedScenario,
    responses={409: {"model": SubmissionError}, 422: {"model": SubmissionError},
               502: {"model": SubmissionError}, 503: {"model": SubmissionError}, 500: {"model": SubmissionError}},
    summary="Validate and save a new scenario",
    description="Create-only. Existing IDs are rejected; no scenario or reference graph is overwritten.",
)
def save_scenario(scenario: Scenario) -> SavedScenario | JSONResponse:
    # Application writes cannot fill an empty graph reserved for approved content.
    if scenario_graph_iri(scenario.id) in explorer.configured_approved_graphs():
        return _error(409, SubmissionError(
            code="scenario_id_reserved", message="This scenario ID is reserved for the approved corpus. Use a new ID.",
        ))
    prepared = _validated_graph(scenario)
    if isinstance(prepared, JSONResponse):
        return prepared
    graph, validation = prepared
    try:
        with connect_graphdb() as store:
            location = store.save(scenario.id, graph)
        return SavedScenario(**location, triple_count=len(graph), validation=validation)
    except GraphDBError:
        raise
    except Exception:
        logger.exception("Scenario saving failed")
        return _error(500, SubmissionError(code="internal_error", message="Scenario processing failed on the server."))


@app.get(
    "/scenarios/{scenario_id}/team", response_model=TeamComposition,
    responses={404: {"model": SubmissionError}, 422: {"model": SubmissionError},
               502: {"model": SubmissionError}, 503: {"model": SubmissionError}, 500: {"model": SubmissionError}},
    summary="Retrieve team members and roles (CQ1)",
)
def scenario_team(scenario_id: Identifier) -> TeamComposition | JSONResponse:
    try:
        with connect_graphdb() as store:
            return TeamComposition(**store.team(scenario_id))
    except GraphDBError:
        raise
    except Exception:
        logger.exception("Scenario team retrieval failed")
        return _error(500, SubmissionError(code="internal_error", message="Scenario processing failed on the server."))


@app.get("/explorer/catalog", summary="List available shared scenarios and competency questions")
def explorer_catalog() -> explorer.ExplorerCatalog:
    with connect_graphdb() as store:
        return explorer.catalog(store)


@app.post(
    "/explorer/query", response_model=explorer.ExplorerResult,
    summary="Run a predefined competency question in selected named graphs",
)
def query_explorer(request: explorer.ExplorerRequest) -> explorer.ExplorerResult | JSONResponse:
    explorer.validate_parameters(request)
    graph = None
    if request.scenario is not None:
        prepared = _validated_graph(request.scenario)
        if isinstance(prepared, JSONResponse):
            return prepared
        graph, _ = prepared
    with connect_graphdb() as store:
        return explorer.answer(store, request, graph)


@app.post(
    "/explorer/concepts", response_model=explorer.ExplorerResult,
    summary="Find recorded HINT concepts and compare a draft with a shared scenario",
)
def query_concepts(request: explorer.ConceptExplorationRequest) -> explorer.ExplorerResult | JSONResponse:
    graph = None
    if request.scenario is not None:
        prepared = _validated_graph(request.scenario)
        if isinstance(prepared, JSONResponse):
            return prepared
        graph, _ = prepared
    with connect_graphdb() as store:
        return explorer.explore_concepts(store, request, graph)
