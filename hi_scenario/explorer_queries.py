"""Scoped adaptations of the original HI competency queries for the Explorer."""

import re
from dataclasses import dataclass

from .graphdb import HINT_GRAPH, ONTOLOGY_GRAPH
from .rdf import HI, HINT


ROW_LIMIT = 200
_IRI = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:[^\x00-\x20<>\"{}|\\^`]+")
_USE_CASE = "?use_case_iri a hi:UseCase ; hi:hasHITeam ?team_iri ."


@dataclass(frozen=True)
class _Query:
    label: str
    description: str
    columns: tuple[tuple[str, str, str], ...]
    evidence: tuple[tuple[str, str], ...]
    facts: str
    parameters: tuple[tuple[str, str, str, str], ...] = ()


def _reference_text(iri: str, *, definition: bool = False, ontology: bool = False) -> str:
    graph = ONTOLOGY_GRAPH if ontology else HINT_GRAPH
    label = "rdfs:label" if ontology else "skos:prefLabel"
    fields = ((label, "label"), ("skos:definition", "definition")) if definition else ((label, "label"),)
    return " ".join(f"""OPTIONAL {{ GRAPH <{graph}> {{
        ?{iri}_iri {predicate} ?{iri}_{field} .
        FILTER(LANG(?{iri}_{field}) = "" || LANGMATCHES(LANG(?{iri}_{field}), "en"))
    }} }}""" for predicate, field in fields)


# Adapted from TEST/HI-Ontology-Test/cqs.ipynb. Keep a graph with every row
# and retain entity IRIs so matching labels never combine different individuals.
_QUERIES = {
    "cq1": _Query(
        label="CQ1 · Team members and roles",
        description="Which agents are members of each HI team, and what roles do they hold?",
        columns=(
            ("member", "Team member", "COALESCE(?member_name, STR(?member_iri))"),
            ("agent_type", "Agent type", "COALESCE(?agent_type_label, STR(?agent_type_iri))"),
            ("role", "Role", "COALESCE(?role_concept_label, STR(?role_concept_iri))"),
            ("role_definition", "Role definition", "?role_concept_definition"),
        ),
        evidence=(("use_case_iri", "Use case"), ("team_iri", "HI team"), ("member_iri", "Team member"),
                  ("agent_type_iri", "Agent type"), ("role_concept_iri", "Role concept")),
        facts=f"""
            ?team_iri hi:hasMember ?member_iri .
            OPTIONAL {{ ?member_iri rdfs:label ?member_name . }}
            OPTIONAL {{
                ?member_iri a ?agent_type_iri .
                {_reference_text('agent_type', ontology=True)}
            }}
            OPTIONAL {{
                ?member_iri hi:hasRoleConcept ?role_concept_iri .
                {_reference_text('role_concept', definition=True)}
            }}
        """,
    ),
    "cq2": _Query(
        label="CQ2 · Tasks supported by capabilities",
        description="Which tasks have all their recorded capability requirements covered by a team member?",
        columns=(
            ("member", "Team member", "COALESCE(?member_name, STR(?member_iri))"),
            ("task", "Task", "COALESCE(?task_name, ?task_concept_label, STR(?task_iri))"),
            ("capability", "Supporting capability", "COALESCE(?capability_concept_label, STR(?capability_concept_iri))"),
            ("task_definition", "Task definition", "?task_concept_definition"),
        ),
        evidence=(("use_case_iri", "Use case"), ("member_iri", "Team member"), ("task_iri", "Task"),
                  ("capability_iri", "Member capability"), ("required_capability_iri", "Task requirement"),
                  ("task_concept_iri", "Task concept"), ("capability_concept_iri", "Capability concept")),
        facts=f"""
            ?team_iri hi:hasMember ?member_iri .
            ?member_iri hi:hasCapability ?capability_iri .
            ?capability_iri hi:hasCapabilityConcept ?capability_concept_iri .
            ?task_iri hi:requiresCapability ?required_capability_iri .
            ?required_capability_iri hi:hasCapabilityConcept ?capability_concept_iri .
            FILTER NOT EXISTS {{
                ?task_iri hi:requiresCapability ?uncovered_capability .
                FILTER NOT EXISTS {{
                    ?uncovered_capability hi:hasCapabilityConcept ?required_concept .
                    ?member_iri hi:hasCapability/hi:hasCapabilityConcept ?required_concept .
                }}
            }}
            OPTIONAL {{ ?member_iri rdfs:label ?member_name . }}
            OPTIONAL {{ ?task_iri rdfs:label ?task_name . }}
            OPTIONAL {{
                ?task_iri hi:hasTaskConcept ?task_concept_iri .
                {_reference_text('task_concept', definition=True)}
            }}
            {_reference_text('capability_concept')}
        """,
        parameters=(("capability", "Supporting capability", "Capability", "capability_concept_iri"),),
    ),
    "cq5": _Query(
        label="CQ5 · Interactions during task execution",
        description="Which participants, intents, and modalities are recorded for interactions during task executions?",
        columns=(
            ("task", "Required task", "COALESCE(?task_name, ?task_concept_label, STR(?task_iri))"),
            ("participant", "Participant", "COALESCE(?participant_name, STR(?participant_iri))"),
            ("intent", "Intent", "COALESCE(?intent_label, STR(?intent_iri))"),
            ("modality", "Modality", "COALESCE(?modality_label, STR(?modality_iri))"),
            ("method", "Execution method", "COALESCE(?method_label, STR(?method_iri))"),
            ("interaction_description", "Interaction description", "?interaction_comment"),
        ),
        evidence=(("use_case_iri", "Use case"), ("goal_iri", "Goal"), ("task_iri", "Task"),
                  ("execution_iri", "Task execution"), ("interaction_iri", "Interaction"),
                  ("participant_iri", "Participant"), ("intent_iri", "Intent concept"),
                  ("modality_iri", "Modality concept"), ("method_iri", "Method concept")),
        facts=f"""
            ?team_iri hi:hasGoal ?goal_iri .
            ?goal_iri hi:requiresTask ?task_iri .
            ?execution_iri hi:realizesTask ?task_iri ; hi:hasInteractionEpisode ?interaction_iri .
            ?interaction_iri a hi:Interaction ; hi:hasAgentInvolved ?participant_iri .
            OPTIONAL {{ ?task_iri rdfs:label ?task_name . }}
            OPTIONAL {{ ?participant_iri rdfs:label ?participant_name . }}
            OPTIONAL {{ ?interaction_iri rdfs:comment ?interaction_comment . }}
            OPTIONAL {{
                ?task_iri hi:hasTaskConcept ?task_concept_iri .
                {_reference_text('task_concept')}
            }}
            OPTIONAL {{
                ?interaction_iri hi:hasInteractionIntentConcept ?intent_iri .
                {_reference_text('intent')}
            }}
            OPTIONAL {{
                ?interaction_iri hi:hasInteractionModalityConcept ?modality_iri .
                {_reference_text('modality')}
            }}
            OPTIONAL {{
                ?execution_iri hi:hasMethodConcept ?method_iri .
                {_reference_text('method')}
            }}
        """,
        parameters=(("task", "Task type", "Task", "task_concept_iri"),
                    ("method", "Execution method", "Method", "method_iri")),
    ),
    "cq8": _Query(
        label="CQ8 · Experiments, metrics, and hypotheses",
        description="Which experiments and evaluation metrics are linked to a goal’s required tasks, and what hypotheses are stated?",
        columns=(
            ("goal", "Team goal", "COALESCE(?goal_name, ?goal_concept_label, STR(?goal_iri))"),
            ("experiment", "Experiment", "COALESCE(?experiment_concept_label, STR(?experiment_concept_iri), STR(?experiment_iri))"),
            ("metric", "Evaluation metric", "COALESCE(?metric_label, STR(?metric_iri))"),
            ("null_hypothesis", "Null hypothesis", "?null_hypothesis_text"),
            ("alternative_hypothesis", "Alternative hypothesis", "?alternative_hypothesis_text"),
        ),
        evidence=(("use_case_iri", "Use case"), ("goal_iri", "Goal"), ("evaluation_iri", "Evaluation"),
                  ("experiment_iri", "Experiment"), ("experiment_concept_iri", "Experiment concept"),
                  ("metric_iri", "Metric concept")),
        facts=f"""
            ?team_iri hi:hasGoal ?goal_iri .
            ?evaluation_iri hi:hasExperiment ?experiment_iri .
            FILTER EXISTS {{
                ?goal_iri hi:requiresTask ?task .
                ?execution hi:realizesTask ?task ; hi:evaluatedBy ?evaluation_iri .
            }}
            OPTIONAL {{ ?goal_iri rdfs:label ?goal_name . }}
            OPTIONAL {{ ?experiment_iri hi:hasNullHypothesis ?null_hypothesis_text . }}
            OPTIONAL {{ ?experiment_iri hi:hasAlternativeHypothesis ?alternative_hypothesis_text . }}
            OPTIONAL {{
                ?goal_iri hi:hasGoalConcept ?goal_concept_iri .
                {_reference_text('goal_concept')}
            }}
            OPTIONAL {{
                ?experiment_iri hi:hasExperimentConcept ?experiment_concept_iri .
                {_reference_text('experiment_concept')}
            }}
            OPTIONAL {{
                ?evaluation_iri hi:hasMetricConcept ?metric_iri .
                {_reference_text('metric')}
            }}
        """,
        parameters=(("goal", "Goal type", "Goal", "goal_concept_iri"),),
    ),
    "cq11": _Query(
        label="CQ11 · Contextual phenomena",
        description="Which phenomena are recorded in contexts that influence a use case’s HI team?",
        columns=(
            ("phenomenon", "Phenomenon", "COALESCE(?phenomenon_label, STR(?phenomenon_iri))"),
            ("definition", "Phenomenon definition", "?phenomenon_definition"),
            ("context", "Context type", "COALESCE(?context_concept_label, STR(?context_concept_iri), STR(?context_iri))"),
        ),
        evidence=(("use_case_iri", "Use case"), ("team_iri", "HI team"), ("context_iri", "Context"),
                  ("context_concept_iri", "Context concept"), ("phenomenon_iri", "Phenomenon concept")),
        facts=f"""
            ?context_iri hi:hasInfluenceOn ?team_iri ; hi:hasPhenomenonConcept ?phenomenon_iri .
            OPTIONAL {{
                ?context_iri hi:hasContextConcept ?context_concept_iri .
                {_reference_text('context_concept')}
            }}
            {_reference_text('phenomenon', definition=True)}
        """,
    ),
}


EXPLORER_QUESTIONS = {
    question_id: {
        "id": question_id,
        "label": question.label,
        "description": question.description,
        "columns": [{"id": name, "label": label} for name, label, _ in question.columns],
        "parameters": [{"id": name, "label": label, "category": category}
                       for name, label, category, _ in question.parameters],
    }
    for question_id, question in _QUERIES.items()
}


def _iri(value: str) -> str:
    if _IRI.fullmatch(value) is None:
        raise ValueError("Invalid IRI in Explorer scope or parameter.")
    return f"<{value}>"


def build_explorer_query(question_id: str, graph_iris: list[str], parameters: dict[str, str]) -> str:
    """Render a fixed read-only query over application-chosen named graphs."""
    question = _QUERIES[question_id]
    if not graph_iris:
        raise ValueError("Explorer requires at least one named graph.")
    selectors = {name: variable for name, _, _, variable in question.parameters}
    filters = "\n".join(f"FILTER(?{selectors[name]} = {_iri(str(HINT[value]))})"
                        for name, value in sorted(parameters.items()))
    evidence = " ".join(f"?{name}" for name, _ in question.evidence)
    values = " ".join(f"({expr} AS ?{name})" for name, _, expr in question.columns)
    order = " ".join(f"?{name}" for name, _, _ in question.columns)
    # GraphDB 10.8 can read staged graphs by IRI but misses them with VALUES + GRAPH ?graph.
    scopes = "\nUNION\n".join(f"""{{
        GRAPH {iri} {{
            {_USE_CASE}
            {question.facts}
            {filters}
        }}
        BIND({iri} AS ?graph)
    }}""" for iri in map(_iri, sorted(set(graph_iris))))
    return f"""
        PREFIX hi: <{HI}>
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        SELECT DISTINCT ?graph {evidence} {values}
        WHERE {{
            {scopes}
        }}
        ORDER BY ?graph {evidence} {order}
        LIMIT {ROW_LIMIT + 1}
    """


def _binding(row: dict, name: str, *, uri: bool = False) -> str | None:
    if name not in row:
        return None
    term = row[name]
    if not isinstance(term, dict) or not isinstance(term.get("value"), str):
        raise ValueError("Invalid Explorer result binding.")
    if term.get("type") not in (("uri",) if uri else ("literal", "typed-literal")):
        raise ValueError("Unexpected Explorer result binding type.")
    if uri:
        _iri(term["value"])
    return term["value"]


def parse_explorer_rows(question_id: str, result: dict, graph_iris: list[str]) -> tuple[list[dict], bool]:
    """Decode only selected columns and named-scope evidence for the response."""
    question = _QUERIES[question_id]
    bindings = result["results"]["bindings"]
    if not isinstance(bindings, list) or len(bindings) > ROW_LIMIT + 1:
        raise ValueError("Invalid Explorer bindings list.")
    scopes = set(graph_iris)
    rows = []
    for row in bindings:
        if not isinstance(row, dict):
            raise ValueError("Invalid Explorer result row.")
        graph = _binding(row, "graph", uri=True)
        if graph not in scopes:
            raise ValueError("Explorer response includes a graph outside the selection.")
        values = {name: _binding(row, name) for name, _, _ in question.columns}
        evidence = [{"label": label, "iri": iri} for name, label in question.evidence
                    if (iri := _binding(row, name, uri=True)) is not None]
        if not evidence:
            raise ValueError("Explorer response row has no evidence.")
        rows.append({"graph_iri": graph, "values": values, "evidence": evidence})
    return rows[:ROW_LIMIT], len(rows) > ROW_LIMIT
