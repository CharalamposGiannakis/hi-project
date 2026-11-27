"""Private feedback persistence, API isolation, and operator recovery."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

from fastapi.testclient import TestClient
import pytest

from hi_scenario import feedback
from hi_scenario.api import app


@pytest.fixture
def private_store(tmp_path, monkeypatch):
    directory = tmp_path / "feedback"
    monkeypatch.setenv("FEEDBACK_DIR", str(directory))
    return directory


def submission(message="Synthetic researcher observation."):
    return {"category": "scientific_observation", "area": "explorer", "message": message}


def test_submission_persists_only_explicit_fields_and_survives_new_client(private_store, caplog):
    with TestClient(app) as client:
        result = client.post("/feedback", json=submission("  Synthetic observation.  "),
                             headers={"User-Agent": "do-not-collect", "X-Researcher": "not-stored"})
    assert result.status_code == 201
    receipt = result.json()
    assert set(receipt) == {"id", "created_at"}
    saved = feedback.records(private_store)
    assert len(saved) == 1
    assert saved[0].message == "Synthetic observation."
    assert saved[0].id.hex == receipt["id"].replace("-", "")
    assert saved[0].created_at.utcoffset().total_seconds() == 0
    assert set(saved[0].model_dump()) == {"id", "created_at", "category", "area", "message"}
    if os.name != "nt":
        assert stat.S_IMODE(private_store.stat().st_mode) == 0o700
        assert stat.S_IMODE(next(private_store.glob("*.json")).stat().st_mode) == 0o600
    # A fresh client cannot list or retrieve any researcher's feedback, even by receipt.
    with TestClient(app) as other:
        assert other.get("/feedback").status_code == 405
        assert other.get(f"/feedback/{receipt['id']}").status_code == 404
    assert feedback.records(private_store) == saved
    assert "Synthetic observation" not in caplog.text


@pytest.mark.parametrize("payload", [
    submission(""), submission(" \n\t "), submission("x" * 6001),
    {**submission(), "category": "unsupported"}, {**submission(), "area": "unsupported"},
    {**submission(), "scenario": {"private": "must-not-be-stored"}},
    {**submission(), "email": "private@example.invalid"}, {},
])
def test_invalid_or_extra_fields_are_rejected_without_storage_or_echo(private_store, payload, caplog):
    with TestClient(app) as client:
        response = client.post("/feedback", json=payload)
    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert "must-not-be-stored" not in response.text + caplog.text
    assert "private@example.invalid" not in response.text + caplog.text
    assert feedback.records(private_store) == []


def test_concurrent_submissions_remain_distinct_and_complete(private_store):
    def send(index):
        with TestClient(app) as client:
            response = client.post("/feedback", json=submission(f"Synthetic record {index}"))
            assert response.status_code == 201
            return response.json()["id"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        identifiers = list(pool.map(send, range(12)))
    assert len(set(identifiers)) == len(feedback.records(private_store)) == 12
    assert not list(private_store.glob(".pending-*"))


def test_storage_failure_returns_actionable_error_without_private_details(private_store, monkeypatch, caplog):
    def unavailable(*_):
        raise OSError("private-path-and-research-content")

    monkeypatch.setattr(feedback, "_write", unavailable)
    with TestClient(app) as client:
        response = client.post("/feedback", json=submission("do-not-log-this-message"))
    assert response.status_code == 503
    assert response.json()["code"] == "feedback_unavailable"
    assert "private-path-and-research-content" not in response.text + caplog.text
    assert "do-not-log-this-message" not in response.text + caplog.text


def test_backup_restore_preserves_full_records_and_is_retryable(private_store, tmp_path):
    for message in ("Synthetic line one\nline two: café", "Synthetic scientific observation"):
        feedback.submit(feedback.FeedbackSubmission(**submission(message)))
    bundle = feedback.backup(private_store)
    target = tmp_path / "restored"
    assert feedback.restore(target, bundle.model_dump_json()) == 2
    assert feedback.records(target) == feedback.records(private_store)
    assert feedback.restore(target, bundle.model_dump_json()) == 2
    assert feedback.backup(target) == bundle


@pytest.mark.parametrize("change", ["message", "checksum", "duplicate", "extra"])
def test_restore_rejects_corrupt_or_invalid_backup_before_writing(private_store, tmp_path, change):
    feedback.submit(feedback.FeedbackSubmission(**submission()))
    bundle = feedback.backup(private_store).model_dump(mode="json")
    if change == "message":
        bundle["records"][0]["message"] = "tampered"
    elif change == "checksum":
        bundle["sha256"] = "incorrect"
    elif change == "duplicate":
        bundle["records"].append(bundle["records"][0])
        bundle["sha256"] = feedback._digest([feedback.FeedbackRecord.model_validate(record) for record in bundle["records"]])
    else:
        bundle["records"][0]["scenario"] = "must not be restored"
    target = tmp_path / "invalid-restore"
    with pytest.raises(ValueError):
        feedback.restore(target, json.dumps(bundle))
    assert not target.exists()


def test_restore_refuses_existing_unrelated_records(private_store, tmp_path):
    feedback.submit(feedback.FeedbackSubmission(**submission()))
    bundle = feedback.backup(private_store)
    assert feedback.restore(private_store, bundle.model_dump_json()) == 1
    feedback.submit(feedback.FeedbackSubmission(**submission("later record")))
    before = feedback.records(private_store)
    with pytest.raises(ValueError, match="empty destination"):
        feedback.restore(private_store, bundle.model_dump_json())
    assert feedback.records(private_store) == before


def test_interrupted_restore_can_resume_without_replacing_records(private_store, tmp_path, monkeypatch):
    for index in range(2):
        feedback.submit(feedback.FeedbackSubmission(**submission(f"Synthetic record {index}")))
    bundle = feedback.backup(private_store)
    target = tmp_path / "partial"
    original_write = feedback._write

    def interrupt(directory, record):
        if feedback.records(directory):
            raise OSError("interrupted restore")
        original_write(directory, record)

    monkeypatch.setattr(feedback, "_write", interrupt)
    with pytest.raises(OSError):
        feedback.restore(target, bundle.model_dump_json())
    assert len(feedback.records(target)) == 1
    monkeypatch.setattr(feedback, "_write", original_write)
    assert feedback.restore(target, bundle.model_dump_json()) == 2
    assert feedback.records(target) == feedback.records(private_store)


def test_export_does_not_silently_ignore_unreadable_storage(private_store, monkeypatch):
    def denied(_directory):
        raise PermissionError("private-storage")

    monkeypatch.setattr(Path, "iterdir", denied)
    with pytest.raises(PermissionError):
        feedback.backup(private_store)


def test_failed_atomic_write_leaves_no_visible_record_or_temporary_file(private_store, monkeypatch):
    def fail(*_):
        raise OSError("disk failure")

    monkeypatch.setattr(feedback.os, "link", fail)
    with pytest.raises(OSError):
        feedback.submit(feedback.FeedbackSubmission(**submission()))
    assert list(private_store.iterdir()) == []


def test_operator_cli_review_export_restore_and_corruption_are_private(private_store, tmp_path):
    feedback.submit(feedback.FeedbackSubmission(**submission("Synthetic \x1b[31m terminal control\nsecond line")))

    def operator(action, directory=private_store, payload=None):
        return subprocess.run([sys.executable, "-m", "infra.feedback", action],
                              cwd=Path(__file__).resolve().parents[1],
                              env={**os.environ, "FEEDBACK_DIR": str(directory)},
                              input=payload, capture_output=True, text=True, encoding="utf-8", timeout=20)

    review = operator("review")
    assert review.returncode == 0 and len(review.stdout.splitlines()) == 1
    assert "\x1b" not in review.stdout
    exported = operator("export")
    assert exported.returncode == 0
    target = tmp_path / "operator-restore"
    restored = operator("restore", target, exported.stdout)
    assert restored.returncode == 0 and "Verified 1" in restored.stderr
    assert feedback.records(target) == feedback.records(private_store)
    failed = operator("restore", tmp_path / "bad-target", "private invalid input")
    assert failed.returncode == 1
    assert "private invalid input" not in failed.stdout + failed.stderr
