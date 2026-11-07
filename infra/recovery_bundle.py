"""File formats shared by the source capture and the isolated recovery tools."""

import hashlib
from pathlib import Path
import re
import tarfile
from typing import BinaryIO


ARCHIVE = "hi.tar"
MANIFEST = "manifest.json"
DATASET = "source.nq"
CHECKSUMS = "SHA256SUMS"
IMAGE_PLATFORM_FORMAT = "{{.Os}}/{{.Architecture}}{{if .Variant}}/{{.Variant}}{{end}}"
GRAPHDB_DIGEST = re.compile(
    r"(?:(?:docker\.io|index\.docker\.io|registry-1\.docker\.io)/)?(ontotext/graphdb@sha256:[0-9a-f]{64})",
)


def graphdb_repo_digests(references):
    """Normalize Docker Hub aliases for immutable Ontotext repository references."""
    if not isinstance(references, list):
        return set()
    digests = set()
    for reference in references:
        match = GRAPHDB_DIGEST.fullmatch(reference) if isinstance(reference, str) else None
        if match:
            digests.add(match.group(1))
    return digests


def verify_graphdb_image(source, platform, references):
    expected_platform = source.get("graphdb_platform")
    if not expected_platform or expected_platform != platform:
        raise ValueError(f"GraphDB platform differs from the recorded source ({expected_platform!r} vs {platform!r}).")
    expected = graphdb_repo_digests(source.get("graphdb_repo_digests"))
    actual = graphdb_repo_digests(references)
    if not expected or not actual:
        raise ValueError("A portable Ontotext GraphDB repository digest is required on both source and target.")
    if expected.isdisjoint(actual):
        raise ValueError(f"GraphDB repository digest differs (source {sorted(expected)}, target {sorted(actual)}).")


def archive_digest(stream: BinaryIO) -> str:
    # Require a populated tar and both end blocks, which tarfile can otherwise accept as missing.
    with tarfile.open(fileobj=stream, mode="r:") as archive:
        if not any(member.isfile() and member.size for member in archive.getmembers()):
            raise ValueError("Backup archive has no file data.")
        stream.seek(archive.offset)
        end_size = 2 * tarfile.BLOCKSIZE
        if stream.read(end_size) != bytes(end_size):
            raise ValueError("Backup archive is incomplete (missing tar end blocks).")
    stream.seek(0)
    digest = hashlib.file_digest(stream, "sha256").hexdigest()
    stream.seek(0)
    return digest


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checksum_text(bundle: Path, archive_sha256: str, rdf_sha256: str) -> str:
    return (
        f"{archive_sha256}  {ARCHIVE}\n"
        f"{rdf_sha256}  {DATASET}\n"
        f"{file_digest(bundle / MANIFEST)}  {MANIFEST}\n"
    )
