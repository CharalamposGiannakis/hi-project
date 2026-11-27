"""Private, immutable feedback records; deliberately independent of scenario RDF."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Literal
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, UUID4


class FeedbackSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: Literal["problem", "improvement", "scientific_observation"]
    area: Literal["general", "home", "builder", "management", "explorer"] = "general"
    message: str = Field(min_length=1, max_length=6000)


class FeedbackReceipt(BaseModel):
    id: UUID4
    created_at: AwareDatetime


class FeedbackRecord(FeedbackSubmission, FeedbackReceipt):
    pass


class FeedbackBackup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    format_version: Literal[1] = 1
    records: list[FeedbackRecord]
    sha256: str


def feedback_directory() -> Path:
    configured = os.getenv("FEEDBACK_DIR")
    if configured is not None and not configured.strip():
        raise ValueError("Feedback directory is empty.")
    return Path(configured) if configured is not None else Path(__file__).resolve().parents[1] / ".local" / "feedback"


def _write(directory: Path, record: FeedbackRecord) -> None:
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    # A complete fsynced file becomes visible at once. Hard linking is create-only,
    # including on Windows, so neither submissions nor restores replace records.
    descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
            output.write(record.model_dump_json() + "\n")
            output.flush()
            os.fsync(output.fileno())
        os.link(temporary, directory / f"{record.id}.json")
        if os.name != "nt":
            directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        Path(temporary).unlink(missing_ok=True)


def submit(submission: FeedbackSubmission) -> FeedbackReceipt:
    record = FeedbackRecord(**submission.model_dump(), id=uuid4(), created_at=datetime.now(timezone.utc))
    _write(feedback_directory(), record)
    return FeedbackReceipt(id=record.id, created_at=record.created_at)


def records(directory: Path) -> list[FeedbackRecord]:
    try:
        paths = list(directory.iterdir())
    except FileNotFoundError:
        return []
    result = []
    for path in paths:
        if path.suffix != ".json":
            continue
        record = FeedbackRecord.model_validate_json(path.read_bytes())
        if path.name != f"{record.id}.json":
            raise ValueError("Feedback record identity mismatch.")
        result.append(record)
    return sorted(result, key=lambda record: (record.created_at, str(record.id)))


def _digest(entries: list[FeedbackRecord]) -> str:
    payload = [entry.model_dump(mode="json") for entry in entries]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def backup(directory: Path) -> FeedbackBackup:
    # Records are immutable and published atomically; a snapshot includes files
    # enumerated here, without requiring a GraphDB or application outage.
    entries = records(directory)
    return FeedbackBackup(records=entries, sha256=_digest(entries))


def restore(directory: Path, payload: str) -> int:
    bundle = FeedbackBackup.model_validate_json(payload)
    if bundle.sha256 != _digest(bundle.records):
        raise ValueError("Feedback backup checksum mismatch.")
    expected = {record.id: record for record in bundle.records}
    if len(expected) != len(bundle.records):
        raise ValueError("Duplicate feedback identities in backup.")
    existing = {record.id: record for record in records(directory)}
    if any(identifier not in expected or record != expected[identifier] for identifier, record in existing.items()):
        raise ValueError("Restore requires an empty destination or an identical partial restore.")
    for identifier, record in expected.items():
        if identifier not in existing:
            _write(directory, record)
    # Confirm the complete restored content, not just its record count.
    if {record.id: record for record in records(directory)} != expected:
        raise ValueError("Feedback restore verification failed.")
    return len(expected)
