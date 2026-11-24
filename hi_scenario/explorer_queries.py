"""Scoped adaptations of the original HI competency queries for the Explorer."""

import re
from dataclasses import dataclass

from .graphdb import HINT_GRAPH, ONTOLOGY_GRAPH
from .rdf import HI, HINT


ROW_LIMIT = 200
_IRI = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*:[^\x00-\x20<>\"{}|\\^`]+")
_USE_CASE = "?use_case_iri a hi:UseCase ; hi:hasHITeam ?team_iri ."
_CONTEXT_ASSOCIATION = """
    { ?team_iri hi:operatesInContext ?context_iri }
    UNION
    { ?context_iri hi:hasInfluenceOn ?team_iri }
"""
_CONSTRAINT_ATTACHMENTS = """
    {
        ?team_iri hi:hasConstraintConcept ?constraint_iri .
        BIND(?team_iri AS ?constraint_owner_iri)
        BIND("Team constraint" AS ?attachment_text)
    }
    UNION
    {
        ?context_iri a hi:Context ; hi:hasConstraintConcept ?constraint_iri .
        { ?team_iri hi:operatesInContext ?context_iri }
        UNION
        { ?context_iri hi:hasInfluenceOn ?team_iri }
        BIND(?context_iri AS ?constraint_owner_iri)
        BIND("Context constraint" AS ?attachment_text)
    }
"""


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
        description="Which tasks have all their recorded capability requirements covered across the HI team, and which members supply them? Coverage is derived from recorded capabilities. Actual task performance requires execution records.",
        columns=(
            ("member", "Team member", "COALESCE(?member_name, STR(?member_iri))"),
            ("task", "Task", "COALESCE(?task_name, ?task_concept_label, STR(?task_iri))"),
            ("capability", "Supporting capability", "COALESCE(?capability_concept_label, STR(?capability_concept_iri))"),
            ("task_definition", "Task definition", "?task_concept_definition"),
        ),
        evidence=(("use_case_iri", "Use case"), ("team_iri", "HI team"), ("member_iri", "Team member"), ("task_iri", "Task"),
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
                    ?team_iri hi:hasMember/hi:hasCapability/hi:hasCapabilityConcept ?required_concept .
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
        description="Which participants, intents, and modalities are recorded for interactions explicitly linked to executions of goal-required tasks? Interactions without those links do not appear.",
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
    "cq6": _Query(
        label="CQ6 · Goals and tasks associated with a method",
        description="Follow recorded method, task, and goal links on executions. The canonical RDF generator assigns towardsGoal links to executions as an application representation convention. These links provide no proof that a method achieves the goal.",
        columns=(
            ("method", "Method", "COALESCE(?method_label, STR(?method_iri))"),
            ("goal", "Goal", "COALESCE(?goal_name, ?goal_concept_label, STR(?goal_iri))"),
            ("task", "Task", "COALESCE(?task_name, ?task_concept_label, STR(?task_iri))"),
        ),
        evidence=(("use_case_iri", "Use case"), ("team_iri", "HI team"), ("execution_iri", "Task execution"),
                  ("method_iri", "Method concept"), ("goal_iri", "Goal"), ("task_iri", "Task")),
        facts=f"""
            ?team_iri hi:hasGoal ?goal_iri .
            ?execution_iri hi:hasMethodConcept ?method_iri ;
                hi:realizesTask ?task_iri ; hi:towardsGoal ?goal_iri .
            OPTIONAL {{ ?goal_iri rdfs:label ?goal_name }}
            OPTIONAL {{ ?task_iri rdfs:label ?task_name }}
            OPTIONAL {{
                ?goal_iri hi:hasGoalConcept ?goal_concept_iri .
                {_reference_text('goal_concept')}
            }}
            OPTIONAL {{
                ?task_iri hi:hasTaskConcept ?task_concept_iri .
                {_reference_text('task_concept')}
            }}
            {_reference_text('method')}
        """,
        parameters=(("method", "Method", "Method", "method_iri"),),
    ),
    "cq7": _Query(
        label="CQ7 · Tasks assessed using a metric",
        description="Follow recorded evaluation and experiment metrics to evaluated executions and their tasks. The metric source identifies which relationship was recorded.",
        columns=(
            ("metric", "Metric", "COALESCE(?metric_label, STR(?metric_iri))"),
            ("metric_source", "Metric source", "?metric_source_text"),
            ("task", "Task", "COALESCE(?task_name, ?task_concept_label, STR(?task_iri))"),
        ),
        evidence=(("use_case_iri", "Use case"), ("execution_iri", "Task execution"), ("task_iri", "Task"),
                  ("evaluation_iri", "Evaluation"), ("experiment_iri", "Experiment"),
                  ("metric_iri", "Metric concept"), ("metric_owner_iri", "Metric owner"),
                  ("metric_predicate_iri", "Metric relationship")),
        facts=f"""
            ?execution_iri hi:evaluatedBy ?evaluation_iri ; hi:realizesTask ?task_iri .
            {{
                ?evaluation_iri hi:hasMetricConcept ?metric_iri .
                BIND(?evaluation_iri AS ?metric_owner_iri)
                BIND(hi:hasMetricConcept AS ?metric_predicate_iri)
                BIND("Evaluation" AS ?metric_source_text)
                OPTIONAL {{ ?evaluation_iri hi:hasExperiment ?experiment_iri }}
            }}
            UNION
            {{
                ?evaluation_iri hi:hasExperiment ?experiment_iri .
                ?experiment_iri hi:hasMetricTested ?metric_iri .
                BIND(?experiment_iri AS ?metric_owner_iri)
                BIND(hi:hasMetricTested AS ?metric_predicate_iri)
                BIND("Experiment" AS ?metric_source_text)
            }}
            OPTIONAL {{ ?task_iri rdfs:label ?task_name }}
            OPTIONAL {{
                ?task_iri hi:hasTaskConcept ?task_concept_iri .
                {_reference_text('task_concept')}
            }}
            {_reference_text('metric')}
        """,
        parameters=(("metric", "Evaluation metric", "Metric", "metric_iri"),),
    ),
    "cq8": _Query(
        label="CQ8 · Experiments, metrics, and hypotheses",
        description="Which experiments and metrics are linked to executions of required tasks or executions recorded as contributing to the goal? Metric sources distinguish evaluation records from experiment records.",
        columns=(
            ("goal", "Team goal", "COALESCE(?goal_name, ?goal_concept_label, STR(?goal_iri))"),
            ("experiment", "Experiment", "COALESCE(?experiment_concept_label, STR(?experiment_concept_iri), STR(?experiment_iri))"),
            ("metric", "Metric", "COALESCE(?metric_label, STR(?metric_iri))"),
            ("metric_source", "Metric source", "?metric_source_text"),
            ("null_hypothesis", "Null hypothesis", "?null_hypothesis_text"),
            ("alternative_hypothesis", "Alternative hypothesis", "?alternative_hypothesis_text"),
        ),
        evidence=(("use_case_iri", "Use case"), ("goal_iri", "Goal"), ("evaluation_iri", "Evaluation"),
                  ("experiment_iri", "Experiment"), ("experiment_concept_iri", "Experiment concept"),
                  ("metric_iri", "Metric concept"), ("metric_owner_iri", "Metric owner"),
                  ("metric_predicate_iri", "Metric relationship")),
        facts=f"""
            ?team_iri hi:hasGoal ?goal_iri .
            ?evaluation_iri hi:hasExperiment ?experiment_iri .
            FILTER EXISTS {{
                ?execution hi:evaluatedBy ?evaluation_iri .
                {{
                    ?goal_iri hi:requiresTask ?task .
                    ?execution hi:realizesTask ?task .
                }}
                UNION
                {{ ?execution hi:towardsGoal ?goal_iri . }}
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
                {{
                    ?evaluation_iri hi:hasMetricConcept ?metric_iri .
                    BIND(?evaluation_iri AS ?metric_owner_iri)
                    BIND(hi:hasMetricConcept AS ?metric_predicate_iri)
                    BIND("Evaluation" AS ?metric_source_text)
                }}
                UNION
                {{
                    ?experiment_iri hi:hasMetricTested ?metric_iri .
                    BIND(?experiment_iri AS ?metric_owner_iri)
                    BIND(hi:hasMetricTested AS ?metric_predicate_iri)
                    BIND("Experiment" AS ?metric_source_text)
                }}
                {_reference_text('metric')}
            }}
        """,
        parameters=(("goal", "Goal type", "Goal", "goal_concept_iri"),),
    ),
    "cq9": _Query(
        label="CQ9 · Contextual constraints and recorded influence",
        description="Find use cases associated with contextual constraints and show any recorded context-to-team influence link. The canonical RDF generator automatically adds hasInfluenceOn when a scenario contains a context as an application representation convention. Independent evidence is required to establish scientific influence or a causal effect.",
        columns=(
            ("constraint", "Contextual constraint", "COALESCE(?constraint_label, STR(?constraint_iri))"),
            ("use_case", "Use case", "COALESCE(?use_case_name, STR(?use_case_iri))"),
            ("context", "Context", "COALESCE(?context_concept_label, STR(?context_iri))"),
            ("influence", "Recorded influence", 'IF(BOUND(?influence_target_iri), "Context hasInfluenceOn HI team", "Not recorded")'),
        ),
        evidence=(("use_case_iri", "Use case"), ("team_iri", "HI team"), ("context_iri", "Context"),
                  ("constraint_iri", "Constraint concept"), ("influence_target_iri", "Recorded influence target"),
                  ("influence_predicate_iri", "Recorded influence relationship")),
        facts=f"""
            ?context_iri a hi:Context ; hi:hasConstraintConcept ?constraint_iri .
            {{ {_CONTEXT_ASSOCIATION} }}
            OPTIONAL {{
                ?context_iri hi:hasInfluenceOn ?team_iri .
                BIND(?team_iri AS ?influence_target_iri)
                BIND(hi:hasInfluenceOn AS ?influence_predicate_iri)
            }}
            OPTIONAL {{ ?use_case_iri rdfs:label ?use_case_name }}
            OPTIONAL {{
                ?context_iri hi:hasContextConcept ?context_concept_iri .
                {_reference_text('context_concept')}
            }}
            {_reference_text('constraint')}
        """,
        parameters=(("constraint", "Contextual constraint", "Constraint", "constraint_iri"),),
    ),
    "cq10": _Query(
        label="CQ10 · Constraints shared across distinct use cases",
        description="Find exact recorded constraint concepts associated with at least two distinct use-case identifiers. Distinctness is determined by identifiers without comparing scenario content. Different identifiers may represent identical scientific content. Members are shown through team membership, with team and context attachments distinguished.",
        columns=(
            ("constraint", "Shared constraint", "COALESCE(?constraint_label, STR(?constraint_iri))"),
            ("attachment", "Recorded attachment", "?attachment_text"),
            ("use_case", "Use case", "COALESCE(?use_case_name, STR(?use_case_iri))"),
            ("member", "Team member", "COALESCE(?member_name, STR(?member_iri))"),
            ("role", "Member role", "COALESCE(?role_concept_label, STR(?role_concept_iri))"),
            ("other_use_case", "Other use case", "COALESCE(?peer_use_case_name, STR(?peer_use_case_iri))"),
        ),
        evidence=(("use_case_iri", "Use case"), ("team_iri", "HI team"), ("member_iri", "Team member"),
                  ("role_concept_iri", "Role concept"), ("constraint_owner_iri", "Constraint owner"),
                  ("constraint_iri", "Constraint concept"), ("peer_use_case_iri", "Other use case"),
                  ("peer_graph_iri", "Other scenario graph")),
        facts=f"""
            {{ {_CONSTRAINT_ATTACHMENTS} }}
            OPTIONAL {{ ?use_case_iri rdfs:label ?use_case_name }}
            OPTIONAL {{
                ?team_iri hi:hasMember ?member_iri .
                OPTIONAL {{ ?member_iri rdfs:label ?member_name }}
                OPTIONAL {{
                    ?member_iri hi:hasRoleConcept ?role_concept_iri .
                    {_reference_text('role_concept')}
                }}
            }}
            {_reference_text('constraint')}
        """,
        parameters=(("constraint", "Shared constraint", "Constraint", "constraint_iri"),),
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


_ORIGINAL_QUESTIONS = (
    "Given a use case, how is the hybrid intelligence team composed, and what roles do its agents assume?",
    "Given an agent's capabilities, which tasks can it perform, and in which use cases can it participate?",
    "What candidate team compositions satisfy all capability requirements for achieving a specific goal?",
    "How can we infer team eligibility, task assignment, or contextual influences?",
    "What types of interactions occur between agents during the execution of a specific task?",
    "Given a method, which goals and tasks can be achieved with it?",
    "Given an evaluation metric, which task can be assessed with it?",
    "Given a goal, which experiments test which metrics, and what hypotheses do these experiments address?",
    "Given a contextual constraint, which use cases are associated with it, and how does it affect the team?",
    "Which constraints are shared across different use cases and agents?",
    "Given a use case, which contextual phenomena are associated with it?",
    "Under what conditions does an agent's behaviour comply with or violate a contextual constraint associated with a use case?",
)
_PENDING = {
    "cq3": (
        "CQ3 · Candidate team compositions",
        "Reliable candidate-team answers require scientific clarification of capability requirements and team eligibility.",
    ),
    "cq4": (
        "CQ4 · Inferred eligibility, assignment, and influence",
        "Reliable inferred answers require scientific clarification of the ontology's eligibility, assignment, and influence rules.",
    ),
    "cq12": (
        "CQ12 · Contextual compliance and violations",
        "Reliable compliance answers require further scientific clarification and ontology development for conditions, behaviour, and violations.",
    ),
}


def _question_catalog() -> dict:
    catalog = {}
    for number, original in enumerate(_ORIGINAL_QUESTIONS, start=1):
        question_id = f"cq{number}"
        query = _QUERIES.get(question_id)
        if query is None:
            label, reason = _PENDING[question_id]
            catalog[question_id] = {
                "id": question_id, "question": original, "label": label, "description": reason,
                "status": "scientific_review_pending", "pending_reason": reason, "columns": [], "parameters": [],
            }
        else:
            catalog[question_id] = {
                "id": question_id, "question": original, "label": query.label, "description": query.description,
                "status": "available", "pending_reason": None,
                "columns": [{"id": name, "label": label} for name, label, _ in query.columns],
                "parameters": [{"id": name, "label": label, "category": category}
                               for name, label, category, _ in query.parameters],
            }
    return catalog


EXPLORER_QUESTIONS = _question_catalog()


def _iri(value: str) -> str:
    if _IRI.fullmatch(value) is None:
        raise ValueError("Invalid IRI in Explorer scope or parameter.")
    return f"<{value}>"


def _cq10_peer_scope(graph_iris: list[str]) -> str:
    # Keep the shared concept correlated while all peer entity identities stay local.
    peer_attachments = _CONSTRAINT_ATTACHMENTS
    for local, peer in (
        ("?team_iri", "?peer_team_iri"), ("?context_iri", "?peer_context_iri"),
        ("?constraint_owner_iri", "?peer_constraint_owner_iri"), ("?attachment_text", "?peer_attachment_text"),
    ):
        peer_attachments = peer_attachments.replace(local, peer)
    branches = []
    for graph in sorted(set(graph_iris)):
        iri = _iri(graph)
        branches.append(f"""{{
            GRAPH {iri} {{
                ?peer_use_case_iri a hi:UseCase ; hi:hasHITeam ?peer_team_iri .
                {{ {peer_attachments} }}
                OPTIONAL {{ ?peer_use_case_iri rdfs:label ?peer_use_case_name }}
            }}
            BIND({iri} AS ?peer_graph_iri)
        }}""")
    return "{ " + "\nUNION\n".join(branches) + " } FILTER(?peer_use_case_iri != ?use_case_iri)"


def build_explorer_query(question_id: str, graph_iris: list[str], parameters: dict[str, str]) -> str:
    """Render a fixed read-only query over application-chosen named graphs."""
    if question_id in _PENDING:
        raise ValueError("Scientific review pending.")
    question = _QUERIES[question_id]
    if not graph_iris:
        raise ValueError("Explorer requires at least one named graph.")
    selectors = {name: variable for name, _, _, variable in question.parameters}
    filters = "\n".join(f"FILTER(?{selectors[name]} = {_iri(str(HINT[value]))})"
                        for name, value in sorted(parameters.items()))
    evidence = " ".join(f"?{name}" for name, _ in question.evidence)
    values = " ".join(f"({expr} AS ?{name})" for name, _, expr in question.columns)
    order = " ".join(f"?{name}" for name, _, _ in question.columns)
    peers = _cq10_peer_scope(graph_iris) if question_id == "cq10" else ""
    # GraphDB 10.8 can read staged graphs by IRI but misses them with VALUES + GRAPH ?graph.
    scopes = "\nUNION\n".join(f"""{{
        GRAPH {iri} {{
            {_USE_CASE}
            {question.facts}
            {filters}
        }}
        BIND({iri} AS ?graph)
        {peers}
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
