"""Check a captured Azure backup bundle and compare it with an isolated restore."""

import argparse
from collections import Counter
from dataclasses import dataclass, field
import io
import json
from pathlib import Path
import subprocess
import tarfile

import httpx
from rdflib import BNode, Dataset, Graph, Literal, Namespace, RDF, URIRef, XSD
from rdflib.compare import isomorphic
from rdflib.exceptions import ParserError
from rdflib.parser import InputSource
from rdflib.plugins.parsers.nquads import NQuadsParser
from rdflib.plugins.parsers.ntriples import r_literal, unquote

from infra import recovery
from infra.recovery_bundle import ARCHIVE, CHECKSUMS, DATASET, MANIFEST, archive_digest, checksum_text, file_digest


QUAD = Namespace("urn:hi-app:recovery:quad:")


class LexicalNQuadsParser(NQuadsParser):
    def literal(self):
        if not self.peek('"'):
            return False
        # Use the pinned RDFLib parser's tokenization but avoid its XSD value normalization.
        lexical, language, datatype = self.eat(r_literal).groups()
        language = language.lower() if language else None
        datatype = unquote(datatype) if datatype else str(RDF.langString if language else XSD.string)
        return Literal(json.dumps([unquote(lexical), language, datatype]))


@dataclass
class DatasetContent:
    named_graphs: Counter = field(default_factory=Counter)
    default_triples: int = 0
    ground_quads: set = field(default_factory=set)
    blank_quads: Graph = field(default_factory=Graph)


def read_dataset(stream) -> DatasetContent:
    dataset = Dataset()
    # A real named graph may have RDFLib's built-in default graph IRI.
    dataset.default_graph = dataset.get_context(BNode())
    source = InputSource()
    source.setByteStream(stream)
    try:
        LexicalNQuadsParser().parse(source, dataset)
    except (ParserError, UnicodeError):
        raise ValueError("The explicit RDF export is not valid N-Quads.") from None

    content = DatasetContent()
    default_id = dataset.default_graph.identifier
    for subject, predicate, obj, graph in dataset.quads():
        if graph is None or graph == default_id:
            graph = None
            content.default_triples += 1
        elif isinstance(graph, URIRef):
            content.named_graphs[str(graph)] += 1
        else:
            raise ValueError("Recovery requires IRI-named graphs.")

        if isinstance(subject, BNode) or isinstance(obj, BNode):
            # A row node represents one quad. Dataset blank nodes appear only as objects here,
            # so graph isomorphism can rename them jointly across all named and default graphs.
            row = BNode()
            content.blank_quads.add((row, QUAD.subject, subject))
            content.blank_quads.add((row, QUAD.predicate, predicate))
            content.blank_quads.add((row, QUAD.object, obj))
            if graph is not None:
                content.blank_quads.add((row, QUAD.graph, graph))
        else:
            content.ground_quads.add((subject, predicate, obj, graph))
    return content


def check_inventory(content: DatasetContent, snapshot: dict) -> None:
    if (dict(content.named_graphs), content.default_triples) != (snapshot["named_graphs"], snapshot["default_triples"]):
        raise ValueError("Explicit RDF export disagrees with the named or default graph inventory.")


def check_bundle(bundle: Path) -> tuple[dict, DatasetContent]:
    manifest = json.loads((bundle / MANIFEST).read_text(encoding="utf-8"))
    if (manifest["repository"], manifest["graphdb_version"]) != (recovery.REPOSITORY, recovery.VERSION):
        raise ValueError("Bundle does not describe repository hi on the pinned GraphDB version.")
    with (bundle / ARCHIVE).open("rb") as stream:
        archive_sha = archive_digest(stream)
    rdf_sha = file_digest(bundle / DATASET)
    if ((archive_sha, rdf_sha) != (manifest["sha256"], manifest["rdf_sha256"])
            or (bundle / CHECKSUMS).read_text(encoding="ascii") != checksum_text(bundle, archive_sha, rdf_sha)):
        raise ValueError("Bundle SHA-256 verification failed.")
    with (bundle / DATASET).open("rb") as stream:
        content = read_dataset(stream)
    check_inventory(content, manifest["snapshot"])
    return manifest["snapshot"], content


def verify_restored(client: httpx.Client, expected: dict, source: DatasetContent) -> None:
    recovery.check_version(client)
    if recovery.list_repositories(client) != [recovery.REPOSITORY] or recovery.snapshot(client) != expected:
        raise ValueError("Restored repository settings or graph inventory differ from the captured source.")
    response = client.get(f"{recovery.ENDPOINT}/statements", params={"infer": "false"},
                          headers={"Accept": "application/n-quads"}).raise_for_status()
    if response.headers.get("Content-Type", "").split(";", 1)[0] != "application/n-quads":
        raise ValueError("GraphDB did not return an explicit N-Quads dataset.")
    restored = read_dataset(io.BytesIO(response.content))
    check_inventory(restored, expected)
    if source.ground_quads != restored.ground_quads or not isomorphic(source.blank_quads, restored.blank_quads):
        raise ValueError("Restored explicit RDF differs from the captured dataset.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="check bundle hashes and source graph inventory offline").add_argument("bundle", type=Path)
    verify = commands.add_parser("verify", help="compare the captured RDF with an isolated recovery project")
    verify.add_argument("--context", required=True)
    verify.add_argument("project")
    verify.add_argument("bundle", type=Path)
    args = parser.parse_args()
    try:
        bundle = args.bundle.resolve()
        if bundle.is_relative_to(recovery.ROOT.resolve()):
            raise ValueError("Keep recovery bundles outside the Git checkout.")
        expected, source = check_bundle(bundle)
        print("Verified bundle SHA-256 and the captured explicit RDF inventory.", flush=True)
        if args.command == "verify":
            url = recovery.local_url(args.context, args.project, "restore")
            with httpx.Client(base_url=url, timeout=120, trust_env=False, follow_redirects=False) as client:
                verify_restored(client, expected, source)
            print("Restored settings, inventory, and complete explicit RDF match the captured source.")
    except (httpx.HTTPError, OSError, RuntimeError, ValueError, KeyError, TypeError,
            subprocess.CalledProcessError, tarfile.TarError) as exc:
        parser.exit(1, f"Recovery RDF {args.command} failed: {exc}\n")


if __name__ == "__main__":
    main()
