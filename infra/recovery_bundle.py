"""File formats shared by the source capture and the isolated recovery tools."""

import hashlib
from pathlib import Path
import tarfile
from typing import BinaryIO


ARCHIVE = "hi.tar"
MANIFEST = "manifest.json"
DATASET = "source.nq"
CHECKSUMS = "SHA256SUMS"


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
