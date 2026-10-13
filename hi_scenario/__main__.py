"""Run JSON -> RDF -> SHACL locally, then emit deterministic N-Triples."""

import argparse
import sys
from pathlib import Path

from .model import Scenario
from .rdf import to_ntriples, to_rdf
from .validation import validate_rdf


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path, help="Structured scenario JSON")
    parser.add_argument("--output", type=Path, help="Output .nt file (default: stdout)")
    args = parser.parse_args()
    try:
        scenario = Scenario.model_validate_json(args.scenario.read_text(encoding="utf-8"))
        graph = to_rdf(scenario)
        conforms, _, report = validate_rdf(graph)
        if not conforms:
            parser.error(report)
        output = to_ntriples(graph)
        if args.output is None:
            sys.stdout.write(output)
        else:
            args.output.write_text(output, encoding="utf-8", newline="\n")
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"SHACL conforms: {len(graph)} triples", file=sys.stderr)


if __name__ == "__main__":
    main()
