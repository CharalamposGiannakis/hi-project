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

    return graph


def to_ntriples(graph: Graph) -> str:
    """Serialize generated RDF in a stable order, with proper literal escaping."""
    # splitlines() also splits Unicode separators that may occur inside names.
    lines = graph.serialize(format="nt").split("\n")
    return "\n".join(sorted(line for line in lines if line)) + "\n"
