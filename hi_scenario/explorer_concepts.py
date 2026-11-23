"""Recorded HINT concepts and their source-local RDF relationships."""

from dataclasses import dataclass

from .explorer_queries import ROW_LIMIT, _binding, _iri
from .graphdb import HINT_GRAPH, ONTOLOGY_GRAPH
from .rdf import HI, HINT


CONCEPT_COLUMNS = [
    {"id": key, "label": label}
    for key, label in (
        ("category", "Category"), ("concept", "HINT concept"), ("entity", "Concept owner"),
        ("connection", "Recorded connection"), ("related", "Related entity"), ("overlap", "Concept overlap"),
    )
]
_EVIDENCE = (
    ("entity_iri", "Concept owner"), ("assertion_iri", "Concept relationship"), ("concept_iri", "HINT concept"),
    ("related_iri", "Related entity"), ("relation_iri", "Connection relationship"),
)


@dataclass(frozen=True)
class _Assertion:
    category: str
    entity_type: str
    predicate: str
    label: str
    relations: str = ""


_ASSERTIONS = (
    _Assertion("Capability", "Capability", "hasCapabilityConcept", "Capability concept", """
        {
            ?related_iri hi:hasCapability ?entity_iri .
            BIND(hi:hasCapability AS ?relation_iri)
            BIND("Agent has capability" AS ?connection_text)
        } UNION {
            ?related_iri hi:requiresCapability ?entity_iri .
            BIND(hi:requiresCapability AS ?relation_iri)
            BIND("Task requires capability" AS ?connection_text)
        } UNION {
            ?entity_iri hi:allowsTask ?related_iri .
            BIND(hi:allowsTask AS ?relation_iri)
            BIND("Capability allows task" AS ?connection_text)
        }
    """),
    _Assertion("Constraint", "HITeam", "hasConstraintConcept", "Team constraint"),
    _Assertion("Constraint", "Context", "hasConstraintConcept", "Context constraint"),
    _Assertion("Method", "TaskExecution", "hasMethodConcept", "Execution method", """
        {
            ?entity_iri hi:realizesTask ?related_iri .
            BIND(hi:realizesTask AS ?relation_iri)
            BIND("Execution method for task" AS ?connection_text)
        } UNION {
            ?entity_iri hi:performedBy ?related_iri .
            BIND(hi:performedBy AS ?relation_iri)
            BIND("Execution method performed by agent" AS ?connection_text)
        }
    """),
    _Assertion("Metric", "Evaluation", "hasMetricConcept", "Evaluation metric", """
        {
            ?related_iri hi:evaluatedBy ?entity_iri .
            BIND(hi:evaluatedBy AS ?relation_iri)
            BIND("Evaluation metric linked from execution" AS ?connection_text)
        } UNION {
            ?entity_iri hi:hasExperiment ?related_iri .
            BIND(hi:hasExperiment AS ?relation_iri)
            BIND("Evaluation metric linked to experiment" AS ?connection_text)
        }
    """),
    _Assertion("Metric", "Experiment", "hasMetricTested", "Experiment metric", """
        ?related_iri hi:hasExperiment ?entity_iri .
        BIND(hi:hasExperiment AS ?relation_iri)
        BIND("Experiment metric linked from evaluation" AS ?connection_text)
    """),
)


def _assertion_pattern(assertion: _Assertion, entity: str = "?entity_iri") -> str:
    return f"{entity} a hi:{assertion.entity_type} ; hi:{assertion.predicate} ?concept_iri ."


def build_concept_query(
    graph_iris: list[str], category: str | None, concept: str | None,
    comparison_graphs: tuple[str, str] | None = None,
) -> str:
    """Query recorded assertions, with comparison evaluated before row limiting."""
    if not graph_iris:
        raise ValueError("Concept exploration requires a named graph.")
    if category is not None and category not in {"Capability", "Constraint", "Method", "Metric"}:
        raise ValueError("Unsupported concept category.")
    if comparison_graphs is not None and (
        len(set(comparison_graphs)) != 2 or set(comparison_graphs) != set(graph_iris)
    ):
        raise ValueError("A comparison requires exactly two distinct named graphs.")
    concept_filter = f"FILTER(?concept_iri = {_iri(str(HINT[concept]))})" if concept is not None else ""
    assertions = [item for item in _ASSERTIONS if category is None or item.category == category]
    branches = []
    for graph in sorted(set(graph_iris)):
        for assertion in assertions:
            overlap = 'BIND("" AS ?overlap)'
            if comparison_graphs is not None:
                draft, shared = comparison_graphs
                other = shared if graph == draft else draft
                other_patterns = " UNION ".join(
                    "{ " + _assertion_pattern(item, "?comparison_entity") + " }"
                    for item in _ASSERTIONS if item.category == assertion.category
                )
                only = "Recorded only in draft" if graph == draft else "Recorded only in shared"
                overlap = f"""BIND(IF(EXISTS {{ GRAPH {_iri(other)} {{ {other_patterns} }} }},
                    "Recorded in both", "{only}") AS ?overlap)"""
            relations = f"""OPTIONAL {{
                {assertion.relations}
                OPTIONAL {{ ?related_iri rdfs:label ?related_name }}
            }}""" if assertion.relations else ""
            branches.append(f"""{{
                GRAPH {_iri(graph)} {{
                    {_assertion_pattern(assertion)}
                    {concept_filter}
                    {relations}
                    OPTIONAL {{ ?entity_iri rdfs:label ?entity_name }}
                    OPTIONAL {{
                        ?entity_iri (hi:hasContextConcept|hi:hasExecutionConcept|hi:hasEvaluationConcept|hi:hasExperimentConcept) ?entity_concept_iri .
                        OPTIONAL {{ GRAPH <{HINT_GRAPH}> {{
                            ?entity_concept_iri skos:prefLabel ?entity_concept_label .
                            FILTER(LANG(?entity_concept_label) = "" || LANGMATCHES(LANG(?entity_concept_label), "en"))
                        }} }}
                    }}
                }}
                BIND({_iri(graph)} AS ?graph)
                BIND("{assertion.category}" AS ?category)
                BIND(hi:{assertion.entity_type} AS ?entity_type_iri)
                BIND(hi:{assertion.predicate} AS ?assertion_iri)
                BIND(COALESCE(?connection_text, "{assertion.label}") AS ?connection)
                {overlap}
            }}""")
    scopes = "\nUNION\n".join(branches)
    evidence = " ".join("?" + key for key, _ in _EVIDENCE)
    return f"""
        PREFIX hi: <{HI}>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        SELECT DISTINCT ?graph {evidence} ?category ?connection ?overlap
            (COALESCE(?concept_label, STR(?concept_iri)) AS ?concept)
            (COALESCE(?entity_name, ?entity_concept_label, ?entity_type_label, STR(?entity_iri)) AS ?entity)
            (COALESCE(?related_name, STR(?related_iri)) AS ?related)
        WHERE {{
            {{ {scopes} }}
            GRAPH <{HINT_GRAPH}> {{
                ?concept_iri a skos:Concept .
                OPTIONAL {{
                    ?concept_iri skos:prefLabel ?concept_label .
                    FILTER(LANG(?concept_label) = "" || LANGMATCHES(LANG(?concept_label), "en"))
                }}
            }}
            OPTIONAL {{ GRAPH <{ONTOLOGY_GRAPH}> {{
                ?entity_type_iri rdfs:label ?entity_type_label .
                FILTER(LANG(?entity_type_label) = "" || LANGMATCHES(LANG(?entity_type_label), "en"))
            }} }}
        }}
        ORDER BY ?category ?concept ?graph ?entity_iri ?connection ?related_iri
        LIMIT {ROW_LIMIT + 1}
    """


def parse_concept_rows(result: dict, graph_iris: list[str]) -> tuple[list[dict], bool]:
    """Retain each assertion's graph, predicates, and resource identifiers."""
    bindings = result["results"]["bindings"]
    if not isinstance(bindings, list) or len(bindings) > ROW_LIMIT + 1:
        raise ValueError("Invalid concept bindings list.")
    rows = []
    for row in bindings:
        if not isinstance(row, dict):
            raise ValueError("Invalid concept result row.")
        graph = _binding(row, "graph", uri=True)
        if graph not in graph_iris:
            raise ValueError("Concept response includes a graph outside the selection.")
        values = {column["id"]: _binding(row, column["id"]) for column in CONCEPT_COLUMNS}
        evidence = [
            {"label": label, "iri": iri} for key, label in _EVIDENCE
            if (iri := _binding(row, key, uri=True)) is not None
        ]
        if any(_binding(row, name, uri=True) is None for name in ("entity_iri", "assertion_iri", "concept_iri")):
            raise ValueError("A concept row requires its recorded assertion.")
        rows.append({"graph_iri": graph, "values": values, "evidence": evidence})
    return rows[:ROW_LIMIT], len(rows) > ROW_LIMIT
