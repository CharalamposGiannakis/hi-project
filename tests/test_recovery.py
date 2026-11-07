import io
import json
import tarfile

import httpx
import pytest

from infra import recovery


TARGET = "hi-recovery-test-restore"
EXTRA_GRAPH = "urn:hi-app:recovery-test:extra"
SNAPSHOT = {"settings": {"ruleset": {"value": "empty"}}, "named_graphs": {EXTRA_GRAPH: 1}, "default_triples": 1}


@pytest.mark.parametrize("project", ["hi-project", "hi-project-deploy", "hi-recovery-test-source"])
def test_restore_project_guard_runs_before_docker(monkeypatch, project):
    monkeypatch.setattr(recovery, "docker", lambda *_: pytest.fail("Docker should not be called"))
    with pytest.raises(ValueError, match="disposable project"):
        recovery.local_url("default", project, "restore")


@pytest.mark.parametrize("problem", [None, "remote", "wrong volume", "bind volume", "public", "dev port"])
def test_disposable_docker_identity(monkeypatch, problem):
    def docker(_context, command, *args):
        if command == "context":
            return "ssh://other-host" if problem == "remote" else "unix:///var/run/docker.sock"
        assert problem != "remote"
        if command == "ps":
            return "fixture-container"
        if command == "container":
            volume = "hi-project_graphdb-data" if problem == "wrong volume" else f"{TARGET}_graphdb-data"
            port = "7200" if problem == "dev port" else "49000"
            host = "0.0.0.0" if problem == "public" else "127.0.0.1"
            return "\n".join((
                json.dumps({"org.hi-project.recovery": "true"}), recovery.IMAGE,
                json.dumps([{"Type": "volume", "Name": volume, "Destination": "/opt/graphdb/home"}]),
                json.dumps({"7200/tcp": [{"HostIp": host, "HostPort": port}]}),
            ))
        assert command == "volume"
        options = {"o": "bind"} if problem == "bind volume" else None
        return "\n".join(("local", json.dumps(options), json.dumps({
            "com.docker.compose.project": TARGET, "com.docker.compose.volume": "graphdb-data",
        })))

    monkeypatch.setattr(recovery, "docker", docker)
    if problem:
        with pytest.raises(ValueError):
            recovery.local_url("default", TARGET, "restore")
    else:
        assert recovery.local_url("default", TARGET, "restore") == "http://127.0.0.1:49000"


def test_inventory_counts_the_stored_default_context_separately():
    def respond(request):
        if request.url.path == "/rest/repositories/hi":
            return httpx.Response(200, json={"params": SNAPSHOT["settings"]})
        if request.url.path == "/repositories/hi/size":
            assert request.url.params["context"] == "null"
            return httpx.Response(200, text="1")
        assert request.url.path == "/repositories/hi"
        assert b"infer=false" in request.content and b"GROUP+BY" in request.content
        row = {"g": {"type": "uri", "value": EXTRA_GRAPH}, "n": {"value": "1"}}
        return httpx.Response(200, json={"results": {"bindings": [row]}})

    with httpx.Client(transport=httpx.MockTransport(respond), base_url="http://test") as client:
        assert recovery.snapshot(client) == SNAPSHOT


@pytest.fixture
def archive_bytes():
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:") as archive:
        member = tarfile.TarInfo("hi/data")
        member.size = 4
        archive.addfile(member, io.BytesIO(b"test"))
    return stream.getvalue()


@pytest.mark.parametrize("failure", ["http", "json", "truncated", "inventory drift"])
def test_backup_failure_never_publishes_archive(tmp_path, monkeypatch, archive_bytes, failure):
    changed = {**SNAPSHOT, "named_graphs": {}} if failure == "inventory drift" else SNAPSHOT
    snapshots = iter((SNAPSHOT, changed))
    monkeypatch.setattr(recovery, "snapshot", lambda _: next(snapshots))

    def respond(request):
        assert request.url.path == "/rest/recovery/backup"
        assert json.loads(request.content) == {"repositories": ["hi"], "backupSystemData": False}
        if failure == "http":
            return httpx.Response(503)
        if failure == "json":
            return httpx.Response(200, json={"status": "error"})
        body = archive_bytes[:1024] if failure == "truncated" else archive_bytes
        return httpx.Response(200, content=body, headers={"Content-Type": "application/x-tar"})

    bundle = tmp_path / "bundle"
    with httpx.Client(transport=httpx.MockTransport(respond), base_url="http://test") as client:
        with pytest.raises((ValueError, httpx.HTTPStatusError)):
            recovery.backup(client, bundle)
    assert not (bundle / recovery.ARCHIVE).exists()
    assert not (bundle / recovery.MANIFEST).exists()


@pytest.mark.parametrize("problem, message", [
    ("digest", "SHA-256"), ("nonempty", "already contains"),
    ("extra graph lost", "named_graphs"), ("default lost", "default_triples"),
])
def test_recovery_checks_checksum_target_and_inventory(tmp_path, monkeypatch, archive_bytes, problem, message):
    digest = recovery.archive_digest(io.BytesIO(archive_bytes))
    (tmp_path / recovery.ARCHIVE).write_bytes(archive_bytes)
    (tmp_path / recovery.MANIFEST).write_text(json.dumps({
        "repository": "hi", "graphdb_version": recovery.VERSION, "snapshot": SNAPSHOT,
        "sha256": "0" * 64 if problem == "digest" else digest,
    }), encoding="utf-8")
    repository = {**SNAPSHOT, "named_graphs": {}} if problem == "extra graph lost" else {**SNAPSHOT, "default_triples": 0}
    monkeypatch.setattr(recovery, "snapshot", lambda _: repository)

    def respond(request):
        assert problem != "digest", "checksum must be checked before restore"
        assert request.method == "GET", "target must be empty before restore"
        assert request.url.path == recovery.REPOSITORIES
        return httpx.Response(200, json=[{"id": "hi"}])

    with httpx.Client(transport=httpx.MockTransport(respond), base_url="http://test") as client:
        with pytest.raises(ValueError, match=message):
            recovery.restore_or_verify(client, tmp_path, restore=problem in ("digest", "nonempty"))
