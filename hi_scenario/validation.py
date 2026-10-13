"""Validate locally against the existing shapes without inferring new facts."""

from pyshacl import validate
from rdflib import Graph

from .rdf import ONTOLOGY_DIR


def validate_rdf(graph: Graph) -> tuple[bool, Graph, str]:
    """Return conformance, the SHACL report graph, and the readable report."""
    return validate(
        data_graph=graph,
        shacl_graph=Graph().parse(ONTOLOGY_DIR / "hi-shacl.ttl", format="turtle"),
        ont_graph=Graph().parse(ONTOLOGY_DIR / "hi-ontology.ttl", format="turtle"),
        inference="none",
        do_owl_imports=False,
        inplace=False,
    )
