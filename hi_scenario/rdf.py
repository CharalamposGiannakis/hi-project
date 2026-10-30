"""Map only supplied scenario facts to the checked-in HI/HINT vocabulary."""

from functools import cache
from pathlib import Path

from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, SKOS

from .model import Scenario


HI = Namespace("https://w3id.org/hi-ontology#")
# Use the actual concept IRIs, despite the thesaurus metadata mentioning '#'.
HINT = Namespace("https://w3id.org/hi-thesaurus/")
ONTOLOGY_DIR = Path(__file__).resolve().parent.parent / "ontology"


@cache
def _thesaurus() -> Graph:
    return Graph().parse(ONTOLOGY_DIR / "hi-thesaurus.ttl", format="turtle")


def _concept(name: str, category: str) -> URIRef:
    """Reject undefined terms and terms outside the selected HINT category."""
    term = HINT[name]
    vocabulary = _thesaurus()
    if (term, RDF.type, SKOS.Concept) not in vocabulary:
        raise ValueError(f"Unknown HINT concept: {name}")
    if term != HINT[category] and HINT[category] not in set(
        vocabulary.transitive_objects(term, SKOS.broader)
    ):
        raise ValueError(f"HINT concept {name} is not a {category} concept")
    return term


def to_rdf(scenario: Scenario) -> Graph:
    """Return an ABox with identities scoped by scenario, entity kind, and ID."""
    graph = Graph()
    graph.bind("hi", HI)
    graph.bind("hint", HINT)
    base = f"urn:hi-app:scenario:{scenario.id}:"
    use_case = URIRef(f"{base}use-case:{scenario.use_case.id}")
    team = URIRef(f"{base}team")
    goal = URIRef(f"{base}goal:{scenario.goal.id}")

    graph.add((use_case, RDF.type, HI.UseCase))
    graph.add((use_case, RDFS.label, Literal(scenario.use_case.name)))
    graph.add((use_case, HI.hasUseCaseConcept, _concept(scenario.use_case.concept, "UseCase")))
    if scenario.use_case.domain is not None:
        graph.add((use_case, HI.hasDomainConcept, _concept(scenario.use_case.domain, "Domain")))
    graph.add((use_case, HI.hasHITeam, team))
    graph.add((team, RDF.type, HI.HITeam))
    graph.add((team, HI.hasGoal, goal))
    graph.add((goal, RDF.type, HI.Goal))
    graph.add((goal, RDFS.label, Literal(scenario.goal.name)))
    graph.add((goal, HI.hasGoalConcept, _concept(scenario.goal.concept, "Goal")))

    if scenario.context is not None:
        # Like the implicit team, the single context has a scenario-scoped identity.
        context = scenario.context
        context_node = URIRef(f"{base}context")
        graph.add((context_node, RDF.type, HI.Context))
        graph.add((context_node, HI.hasContextConcept, _concept(context.concept, "Context")))
        graph.add((team, HI.operatesInContext, context_node))
        graph.add((context_node, HI.hasInfluenceOn, team))
        for phenomenon in context.phenomena:
            graph.add((context_node, HI.hasPhenomenonConcept, _concept(phenomenon, "Phenomenon")))
        for constraint in context.constraints:
            graph.add((context_node, HI.hasConstraintConcept, _concept(constraint, "Constraint")))
        if context.description is not None:
            graph.add((context_node, RDFS.comment, Literal(context.description, lang="en")))

    for task in scenario.tasks:
        task_node = URIRef(f"{base}task:{task.id}")
        graph.add((goal, HI.requiresTask, task_node))
        graph.add((task_node, RDF.type, HI.Task))
        graph.add((task_node, RDFS.label, Literal(task.name)))
        graph.add((task_node, HI.hasTaskConcept, _concept(task.concept, "Task")))

    for agent in scenario.agents:
        agent_node = URIRef(f"{base}agent:{agent.id}")
        agent_type = "HumanAgent" if agent.kind == "human" else "ArtificialAgent"
        graph.add((team, HI.hasMember, agent_node))
        graph.add((agent_node, RDF.type, HI[agent_type]))
        graph.add((agent_node, RDFS.label, Literal(agent.name)))
        graph.add((agent_node, HI.hasAgentConcept, _concept(agent_type, "Agent")))
        for role in agent.roles:
            graph.add((agent_node, HI.hasRoleConcept, _concept(role, "Role")))

    for capability in scenario.capabilities:
        capability_node = URIRef(f"{base}capability:{capability.id}")
        graph.add((capability_node, RDF.type, HI.Capability))
        graph.add((capability_node, HI.hasCapabilityConcept, _concept(capability.concept, "Capability")))
        for agent_id in capability.agents:
            graph.add((URIRef(f"{base}agent:{agent_id}"), HI.hasCapability, capability_node))
        for task_id in capability.tasks:
            task_node = URIRef(f"{base}task:{task_id}")
            # Both directions are explicit because application queries disable inference.
            graph.add((capability_node, HI.allowsTask, task_node))
            graph.add((task_node, HI.requiresCapability, capability_node))

    for execution in scenario.executions:
        execution_node = URIRef(f"{base}execution:{execution.id}")
        agent_node = URIRef(f"{base}agent:{execution.agent}")
        graph.add((execution_node, RDF.type, HI.TaskExecution))
        graph.add((execution_node, HI.hasExecutionConcept, _concept(execution.concept, "TaskExecution")))
        graph.add((execution_node, HI.realizesTask, URIRef(f"{base}task:{execution.task}")))
        graph.add((execution_node, HI.performedBy, agent_node))
        graph.add((agent_node, HI.performsExecution, execution_node))
        graph.add((execution_node, HI.towardsGoal, goal))
        if execution.method is not None:
            graph.add((execution_node, HI.hasMethodConcept, _concept(execution.method, "Method")))

    return graph


def to_ntriples(graph: Graph) -> str:
    """Serialize generated RDF in a stable order, with proper literal escaping."""
    # splitlines() also splits Unicode separators that may occur inside names.
    lines = graph.serialize(format="nt").split("\n")
    return "\n".join(sorted(line for line in lines if line)) + "\n"
