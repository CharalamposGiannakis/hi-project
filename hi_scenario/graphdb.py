"""Small GraphDB adapter: create-only scenario storage and the adapted CQ1."""

import os
from contextlib import contextmanager
from threading import Lock
from typing import Annotated

import httpx
from pydantic import (
    AnyHttpUrl, BaseModel, Field, StringConstraints, TypeAdapter, ValidationError, field_validator,
)
from rdflib import Graph
from rdflib.compare import isomorphic
from rdflib.namespace import RDF

from .model import Identifier
from .rdf import HI, to_ntriples


ONTOLOGY_GRAPH = "urn:hi-app:reference:ontology"
HINT_GRAPH = "urn:hi-app:reference:hint"
_IDENTIFIER = TypeAdapter(Identifier)
# GraphDB 10.8 only provides READ_COMMITTED: use one backend worker.
_SAVE_LOCK = Lock()


def scenario_graph_iri(scenario_id: str) -> str:
    return "urn:hi-app:graph:scenario:" + _IDENTIFIER.validate_python(scenario_id)


class GraphDBSettings(BaseModel):
    url: AnyHttpUrl = AnyHttpUrl("http://127.0.0.1:7200")
    repository: Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]+$")] = "hi"
    timeout_seconds: float = Field(default=10, gt=0, allow_inf_nan=False)

    @field_validator("url")
    @classmethod
    def check_url(cls, value: AnyHttpUrl) -> AnyHttpUrl:
        if value.username or value.password or value.query or value.fragment:
            raise ValueError("GraphDB URL must have no credentials, query, or fragment")
        return value

    @classmethod
    def from_env(cls) -> "GraphDBSettings":
        return cls(
            url=os.getenv("GRAPHDB_URL", "http://127.0.0.1:7200"),
            repository=os.getenv("GRAPHDB_REPOSITORY", "hi"),
            timeout_seconds=os.getenv("GRAPHDB_TIMEOUT_SECONDS", "10"),
        )


class GraphDBError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


def _invalid_response() -> GraphDBError:
    return GraphDBError(502, "graphdb_invalid_response", "GraphDB returned unexpected or incomplete scenario data.")


def cq1_query(graph_iri: str) -> str:
    # Adapted from TEST/HI-Ontology-Test/cqs.ipynb, CQ1. Including ?member
    # prevents DISTINCT from merging different people with the same type/role.
    return f"""
        PREFIX hi: <https://w3id.org/hi-ontology#>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        SELECT DISTINCT ?useCase ?useCaseName ?team ?member ?memberName
            ?agentType ?agentTypeLabel ?roleConcept ?roleLabel ?roleDefinition
        WHERE {{
            GRAPH <{graph_iri}> {{
                ?useCase a hi:UseCase ; hi:hasHITeam ?team .
                ?team hi:hasMember ?member .
                OPTIONAL {{ ?useCase rdfs:label ?useCaseName }}
                OPTIONAL {{ ?member rdfs:label ?memberName }}
                OPTIONAL {{
                    ?member a ?agentType .
                    OPTIONAL {{ GRAPH <{ONTOLOGY_GRAPH}> {{
                        ?agentType rdfs:label ?agentTypeLabel .
                        FILTER(LANG(?agentTypeLabel) = "" || LANGMATCHES(LANG(?agentTypeLabel), "en"))
                    }} }}
                }}
                OPTIONAL {{
                    ?member hi:hasRoleConcept ?roleConcept .
                    OPTIONAL {{ GRAPH <{HINT_GRAPH}> {{
                        ?roleConcept skos:prefLabel ?roleLabel .
                        FILTER(LANG(?roleLabel) = "" || LANGMATCHES(LANG(?roleLabel), "en"))
                    }} }}
                    OPTIONAL {{ GRAPH <{HINT_GRAPH}> {{
                        ?roleConcept skos:definition ?roleDefinition .
                        FILTER(LANG(?roleDefinition) = "" || LANGMATCHES(LANG(?roleDefinition), "en"))
                    }} }}
                }}
            }}
        }}
    """


def _value(row: dict, key: str, *, uri: bool = False, required: bool = False) -> str | None:
    binding = row.get(key)
    if binding is None and not required:
        return None
    if not isinstance(binding, dict) or not isinstance(binding.get("value"), str):
        raise ValueError("Missing or invalid SPARQL binding")
    if uri and binding.get("type") != "uri":
        raise ValueError("Expected an IRI binding")
    return binding["value"]


def _text(first: str | None, second: str | None) -> str | None:
    # Multiple RDF labels are possible; choose deterministically, never invent one.
    return min((value for value in (first, second) if value is not None), default=None)


class GraphDBStore:
    def __init__(self, client: httpx.Client, settings: GraphDBSettings):
        self.client = client
        self.settings = settings
        self.endpoint = f"/repositories/{settings.repository}"

    def _request(self, path: str, **kwargs) -> httpx.Response:
        try:
            response = self.client.post(path, **kwargs)
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            raise GraphDBError(
                503, "graphdb_unavailable", "GraphDB is unavailable or the repository is not ready."
            ) from exc

    def _query(self, query: str) -> dict:
        response = self._request(
            self.endpoint, data={"query": query, "infer": "false"},
            headers={"Accept": "application/sparql-results+json"},
        )
        try:
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("Expected a SPARQL result object")
            return result
        except ValueError as exc:
            raise _invalid_response() from exc

    def exists(self, iri: str) -> bool:
        result = self._query(f"ASK {{ GRAPH <{iri}> {{ ?s ?p ?o }} }}")
        if not isinstance(result.get("boolean"), bool):
            raise _invalid_response()
        return result["boolean"]

    def location(self, scenario_id: str, use_case: str, team: str) -> dict:
        return {
            "scenario_id": scenario_id,
            "repository_id": self.settings.repository,
            "graph_iri": scenario_graph_iri(scenario_id),
            "workbench_url": str(self.settings.url).rstrip("/") + "/",
            "use_case_iri": use_case,
            "team_iri": team,
        }

    def save(self, scenario_id: str, graph: Graph) -> dict:
        iri = scenario_graph_iri(scenario_id)
        with _SAVE_LOCK:
            if self.exists(iri):
                raise GraphDBError(
                    409, "scenario_exists", "This scenario ID is already saved. Use a new ID to save another version."
                )
            # One update, no DELETE/PUT: existing data is never replaced. The
            # server-side guard also avoids adding to an already populated graph.
            update = f"""
                INSERT {{ GRAPH <{iri}> {{ {to_ntriples(graph)} }} }}
                WHERE {{ FILTER NOT EXISTS {{ GRAPH <{iri}> {{ ?s ?p ?o }} }} }}
            """
            self._request(self.endpoint + "/statements", data={"update": update})
            response = self._request(
                self.endpoint,
                data={"query": f"CONSTRUCT {{ ?s ?p ?o }} WHERE {{ GRAPH <{iri}> {{ ?s ?p ?o }} }}", "infer": "false"},
                headers={"Accept": "text/turtle"},
            )
            try:
                stored = Graph().parse(data=response.content, format="turtle")
            except (ValueError, SyntaxError) as exc:
                raise _invalid_response() from exc
            if not isomorphic(graph, stored):
                raise GraphDBError(409, "scenario_exists", "The scenario graph contains different data. Nothing was overwritten.")
        use_case = next(graph.subjects(RDF.type, HI.UseCase))
        team = next(graph.objects(use_case, HI.hasHITeam))
        return self.location(scenario_id, str(use_case), str(team))

    def team(self, scenario_id: str) -> dict:
        iri = scenario_graph_iri(scenario_id)
        result = self._query(cq1_query(iri))
        try:
            rows = result["results"]["bindings"]
            if not isinstance(rows, list):
                raise ValueError("Expected SPARQL bindings")
            if not rows:
                if not self.exists(iri):
                    raise GraphDBError(404, "scenario_not_found", "No saved scenario has this ID.")
                raise _invalid_response()
            use_case = _value(rows[0], "useCase", uri=True, required=True)
            team = _value(rows[0], "team", uri=True, required=True)
            name = None
            members = {}
            for row in rows:
                if (
                    _value(row, "useCase", uri=True, required=True) != use_case
                    or _value(row, "team", uri=True, required=True) != team
                ):
                    raise ValueError("Expected one use case and one team")
                name = _text(name, _value(row, "useCaseName"))
                member_iri = _value(row, "member", uri=True, required=True)
                member = members.setdefault(member_iri, {
                    "iri": member_iri, "name": None, "types": {}, "roles": {},
                })
                member["name"] = _text(member["name"], _value(row, "memberName"))
                type_iri = _value(row, "agentType", uri=True)
                if type_iri is not None:
                    agent_type = member["types"].setdefault(type_iri, {"iri": type_iri, "label": None})
                    agent_type["label"] = _text(agent_type["label"], _value(row, "agentTypeLabel"))
                role_iri = _value(row, "roleConcept", uri=True)
                if role_iri is not None:
                    role = member["roles"].setdefault(role_iri, {
                        "iri": role_iri, "label": None, "definition": None,
                    })
                    role["label"] = _text(role["label"], _value(row, "roleLabel"))
                    role["definition"] = _text(role["definition"], _value(row, "roleDefinition"))
            for member in members.values():
                for field in ("types", "roles"):
                    member[field] = [member[field][key] for key in sorted(member[field])]
            return {
                **self.location(scenario_id, use_case, team), "use_case_name": name,
                "members": [members[key] for key in sorted(members)],
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise _invalid_response() from exc


@contextmanager
def connect_graphdb():
    try:
        settings = GraphDBSettings.from_env()
    except ValidationError as exc:
        raise GraphDBError(503, "graphdb_configuration", "GraphDB connection settings are invalid.") from exc
    with httpx.Client(base_url=str(settings.url), timeout=settings.timeout_seconds, trust_env=False) as client:
        yield GraphDBStore(client, settings)
