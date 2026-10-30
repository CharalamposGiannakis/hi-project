"""Export the HINT concepts the scenario model accepts, for the frontend's choice lists."""

import argparse
import json
from pathlib import Path

from rdflib import URIRef
from rdflib.namespace import RDF, SKOS

from .rdf import HINT, _thesaurus


# Category used by each JSON field; agent concepts are derived from `kind`.
CATEGORIES = (
    "UseCase", "Domain", "Goal", "Task", "Role", "Context", "Phenomenon", "Constraint",
    "Capability", "TaskExecution", "Method", "Experiment", "Evaluation", "Metric",
)


def _text(term: URIRef, predicate: URIRef) -> str:
    values = sorted(str(value) for value in _thesaurus().objects(term, predicate))
    return values[0] if values else ""


def concepts(category: str) -> list[dict[str, str]]:
    """List concepts below `category`, mirroring the check in `rdf._concept`."""
    vocabulary = _thesaurus()
    root = HINT[category]
    found = []
    for term in vocabulary.subjects(RDF.type, SKOS.Concept):
        if term == root or root not in set(vocabulary.transitive_objects(term, SKOS.broader)):
            continue
        found.append({
            "id": str(term).removeprefix(str(HINT)),
            "label": _text(term, SKOS.prefLabel),
            "definition": _text(term, SKOS.definition),
        })
    return sorted(found, key=lambda concept: (concept["label"].lower(), concept["id"]))


def export_vocabulary() -> str:
    """Return a stable JSON document so regenerated output diffs cleanly."""
    data = {category: concepts(category) for category in CATEGORIES}
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Output JSON file")
    args = parser.parse_args()
    args.output.write_text(export_vocabulary(), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
