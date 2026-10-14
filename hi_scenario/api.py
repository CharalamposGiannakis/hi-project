"""Preview, save, and query HI scenarios through the existing semantic pipeline."""

import logging
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from rdflib import Graph

from .graphdb import GraphDBError, connect_graphdb
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
        "scenario_exists", "scenario_not_found", "graphdb_unavailable",
        "graphdb_invalid_response", "graphdb_configuration",
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
async def invalid_request(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # Keep field locations and messages, without echoing payloads or exception contexts.
    issues = [
        InputIssue(location=list(error["loc"]), message=error["msg"], type=error["type"])
        for error in exc.errors()
    ]
    return _error(422, SubmissionError(
        code="invalid_request", message="Scenario JSON failed structural validation.", issues=issues,
    ))


@app.exception_handler(GraphDBError)
async def graphdb_error(_request: Request, exc: GraphDBError) -> JSONResponse:
    return _error(exc.status_code, SubmissionError(code=exc.code, message=str(exc)))


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
