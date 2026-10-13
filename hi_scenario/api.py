"""A local, stateless HTTP interface to the existing scenario pipeline."""

import logging
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .model import Scenario
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
    code: Literal["invalid_request", "invalid_vocabulary", "shacl_failed", "internal_error"]
    message: str
    issues: list[InputIssue] = Field(default_factory=list)
    shacl_report: str | None = None


def _error(status_code: int, error: SubmissionError) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=error.model_dump(mode="json"))


app = FastAPI(title="HI scenario preview", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["POST"],
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
        try:
            graph = to_rdf(scenario)
        except ValueError as exc:
            return _error(422, SubmissionError(code="invalid_vocabulary", message=str(exc)))

        conforms, _, report = validate_rdf(graph)
        if not conforms:
            return _error(422, SubmissionError(
                code="shacl_failed", message="Generated RDF failed SHACL validation.", shacl_report=report,
            ))
        return ScenarioPreview(
            scenario_id=scenario.id,
            rdf=to_ntriples(graph),
            triple_count=len(graph),
            validation=ShaclResult(report=report),
        )
    except Exception:
        # Return server failures inside the route so CORS also applies to them.
        logger.exception("Scenario preview failed")
        return _error(500, SubmissionError(
            code="internal_error", message="Scenario processing failed on the server.",
        ))
