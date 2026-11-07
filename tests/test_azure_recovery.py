import io
import json
from pathlib import Path
import subprocess
import tarfile

import httpx
import pytest

from infra import azure_backup, recovery, recovery_rdf
from infra.recovery_bundle import ARCHIVE, CHECKSUMS, DATASET, MANIFEST


GRAPH = "urn:research:extra"
SOURCE = b'''_:source <urn:research:role> "participant" <urn:research:extra> .
_:source <urn:research:label> "Caf\\u00e9"@EN .
<urn:research:case> <urn:research:count> "01"^^<http://www.w3.org/2001/XMLSchema#integer> <urn:x-rdflib:default> .
'''
REORDERED = '''<urn:research:case> <urn:research:count> "01"^^<http://www.w3.org/2001/XMLSchema#integer> <urn:x-rdflib:default> .
_:renamed <urn:research:label> "Café"@en .
_:renamed <urn:research:role> "participant"^^<http://www.w3.org/2001/XMLSchema#string> <urn:research:extra> .
'''.encode()
SNAPSHOT = {
    "settings": {"ruleset": {"value": "empty"}, "disableSameAs": {"value": "true"}},
    "named_graphs": {GRAPH: 1, "urn:x-rdflib:default": 1}, "default_triples": 1,
}
IDENTITY = {"services": {
    "graphdb": {"container": "graphdb-id"}, "web": {"container": "web-id", "paused": True},
    "backend": {"container": "backend-id", "paused": True},
}}


@pytest.fixture
def native_tar():
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:") as archive:
        member = tarfile.TarInfo("hi/data")
        member.size = 4
        archive.addfile(member, io.BytesIO(b"test"))
    return stream.getvalue()


def mock_capture(monkeypatch, native_tar, *, after=SNAPSHOT, identity=IDENTITY):
    monkeypatch.setattr(azure_backup, "inspect_source", lambda *_: identity)
    monkeypatch.setattr(azure_backup, "require_idle", lambda _: None)
    monkeypatch.setattr(azure_backup.time, "sleep", lambda _: None)
    snapshots = iter((SNAPSHOT, after))
    monkeypatch.setattr(azure_backup, "snapshot", lambda _: next(snapshots))
    requests = []

    def request(container, path, *options, stream, media_type):
        assert container == "graphdb-id"
        requests.append(path)
        if path == "/repositories/hi/statements?infer=false":
            assert options == ("--header", "Accept: application/n-quads")
            assert media_type == "application/n-quads"
            stream.write(SOURCE)
        else:
            assert path == "/rest/recovery/backup"
            assert json.loads(options[-1]) == {"repositories": ["hi"], "backupSystemData": False}
            assert media_type == "application/x-tar"
            stream.write(native_tar)

    monkeypatch.setattr(azure_backup, "request", request)
    return requests


@pytest.fixture
def captured_bundle(tmp_path, monkeypatch, native_tar):
    requests = mock_capture(monkeypatch, native_tar)
    bundle = tmp_path / "bundle"
    azure_backup.capture("fixture", tmp_path, "a" * 40, "web-id", "backend-id", bundle)
    assert requests == ["/repositories/hi/statements?infer=false", "/rest/recovery/backup"]
    assert {path.name for path in bundle.iterdir()} == {ARCHIVE, DATASET, MANIFEST, CHECKSUMS}
    return bundle


@pytest.mark.parametrize("service", ["web", "backend"])
def test_capture_requires_approved_paused_writers(tmp_path, monkeypatch, native_tar, service):
    identity = {"services": {**IDENTITY["services"], service: {"container": f"{service}-id", "paused": False}}}
    requests = mock_capture(monkeypatch, native_tar, identity=identity)
    bundle = tmp_path / "bundle"
    with pytest.raises(ValueError, match="must be paused"):
        azure_backup.capture("fixture", tmp_path, "a" * 40, "web-id", "backend-id", bundle)
    assert requests == [] and not bundle.exists()


def test_capture_inventory_drift_never_finalizes_bundle(tmp_path, monkeypatch, native_tar):
    mock_capture(monkeypatch, native_tar, after={**SNAPSHOT, "default_triples": 0})
    bundle = tmp_path / "bundle"
    with pytest.raises(ValueError, match="inventory changed"):
        azure_backup.capture("fixture", tmp_path, "a" * 40, "web-id", "backend-id", bundle)
    assert {path.name for path in bundle.iterdir()} == {f"{ARCHIVE}.partial", f"{DATASET}.partial"}


@pytest.mark.parametrize("change", [None, ARCHIVE, DATASET, MANIFEST])
def test_bundle_validates_all_transferred_files(captured_bundle, change):
    if change is None:
        snapshot, rdf = recovery_rdf.check_bundle(captured_bundle)
        assert snapshot == SNAPSHOT and dict(rdf.named_graphs) == SNAPSHOT["named_graphs"]
        assert rdf.default_triples == 1
    else:
        with (captured_bundle / change).open("ab") as stream:
            stream.write(b"\n")
        with pytest.raises(ValueError, match="SHA-256"):
            recovery_rdf.check_bundle(captured_bundle)


@pytest.mark.parametrize("change", [None, "blank node split", "literal lexical form", "moved graph", "changed extra"])
def test_compare_complete_restored_dataset(captured_bundle, monkeypatch, change):
    expected, source = recovery_rdf.check_bundle(captured_bundle)
    restored = REORDERED
    if change == "blank node split":
        restored = restored.replace(b"_:renamed", b"_:other", 1)
    elif change == "literal lexical form":
        restored = restored.replace(b'"01"', b'"1"')
    elif change == "moved graph":
        restored = restored.replace(b"<urn:x-rdflib:default>", b"<urn:swap>")
        restored = restored.replace(b"<urn:research:extra>", b"<urn:x-rdflib:default>")
        restored = restored.replace(b"<urn:swap>", b"<urn:research:extra>")
    elif change == "changed extra":
        restored = restored.replace(b'"participant"', b'"operator"')

    monkeypatch.setattr(recovery, "check_version", lambda _: None)
    monkeypatch.setattr(recovery, "list_repositories", lambda _: ["hi"])
    monkeypatch.setattr(recovery, "snapshot", lambda _: SNAPSHOT)

    def respond(request):
        assert request.method == "GET" and request.url.path == "/repositories/hi/statements"
        assert dict(request.url.params) == {"infer": "false"}
        assert request.headers["Accept"] == "application/n-quads"
        return httpx.Response(200, content=restored, headers={"Content-Type": "application/n-quads;charset=UTF-8"})

    with httpx.Client(base_url="http://test", transport=httpx.MockTransport(respond)) as client:
        if change is None:
            recovery_rdf.verify_restored(client, expected, source)
        else:
            with pytest.raises(ValueError, match="explicit RDF differs"):
                recovery_rdf.verify_restored(client, expected, source)


def test_incomplete_export_fails_inventory_check():
    content = recovery_rdf.read_dataset(io.BytesIO(SOURCE.splitlines(keepends=True)[0]))
    with pytest.raises(ValueError, match="disagrees with.*inventory"):
        recovery_rdf.check_inventory(content, SNAPSHOT)


def test_source_transport_uses_container_loopback_and_checks_media(monkeypatch):
    def docker(*args, stdout):
        assert args[:5] == ("exec", "graphdb-id", "curl", "--disable", "--noproxy")
        assert args[-1] == "http://127.0.0.1:7200/rest/recovery/backup"
        return subprocess.CompletedProcess(args, 0, None, b"200 text/html")

    monkeypatch.setattr(azure_backup, "docker", docker)
    with pytest.raises(ValueError, match="Unexpected GraphDB response"):
        azure_backup.request("graphdb-id", "/rest/recovery/backup", stream=io.BytesIO(), media_type="application/x-tar")


def test_wrong_source_host_fails_before_docker(monkeypatch):
    monkeypatch.setattr(azure_backup.socket, "gethostname", lambda: "other-host")
    monkeypatch.setattr(azure_backup, "docker", lambda *_: pytest.fail("Docker should not be called"))
    with pytest.raises(ValueError, match="approved Azure OS hostname"):
        azure_backup.inspect_source("approved-host", Path("."), "a" * 40)


@pytest.mark.parametrize("problem", [None, "published GraphDB", "different volume", "extra network member"])
def test_source_identity_checks_the_deployment(monkeypatch, tmp_path, problem):
    ids = {service: digit * 64 for service, digit in zip(("graphdb", "backend", "web"), "123")}
    revision = "a" * 40
    monkeypatch.setattr(azure_backup.socket, "gethostname", lambda: "approved-host")
    monkeypatch.setattr(subprocess, "check_output", lambda *_, **__: revision)

    def docker(*args):
        if args[0] == "ps":
            output = ids[args[-1].split("=")[-1]]
        elif args[0] == "network":
            members = dict.fromkeys(ids.values())
            if problem == "extra network member":
                members["4" * 64] = None
            output = "true\n" + json.dumps(members)
        elif args[0] == "image":
            output = "linux/amd64\n[]"
        elif args[3] == "{{json .NetworkSettings.Networks}}":
            assert args[-1] == ids["graphdb"]
            output = json.dumps({azure_backup.NETWORK: {}})
        else:
            graphdb = args[-1] == ids["graphdb"]
            volume = "hi-project_graphdb-data" if problem == "different volume" else azure_backup.VOLUME
            mounts = [{"Type": "volume", "Name": volume, "Destination": "/opt/graphdb/home"}] if graphdb else []
            ports = {"7200/tcp": [{"HostIp": "127.0.0.1", "HostPort": "7200"}]} if graphdb and problem == "published GraphDB" else {}
            output = "\n".join((str(tmp_path), "started", "false", azure_backup.IMAGE, "image-id",
                                json.dumps(mounts), json.dumps(ports)))
        return subprocess.CompletedProcess(args, 0, output.encode(), b"")

    def request(container, path):
        assert container == ids["graphdb"]
        return {
            "/rest/info/version": b'{"productVersion":"10.8.14","productType":"free"}',
            "/rest/repositories": b'[{"id":"hi","local":true}]',
        }[path]

    monkeypatch.setattr(azure_backup, "docker", docker)
    monkeypatch.setattr(azure_backup, "request", request)
    if problem is None:
        source = azure_backup.inspect_source("approved-host", tmp_path, revision)
        assert source["deployed_revision"] == revision
        assert source["services"]["graphdb"]["container"] == ids["graphdb"]
    else:
        with pytest.raises(ValueError):
            azure_backup.inspect_source("approved-host", tmp_path, revision)


def test_source_inventory_checks_complete_explicit_count(monkeypatch):
    responses = {
        "/rest/repositories/hi": json.dumps({"params": SNAPSHOT["settings"]}).encode(),
        "/repositories/hi": json.dumps({"results": {"bindings": [
            {"g": {"type": "uri", "value": GRAPH}, "n": {"value": "1"}},
        ]}}).encode(),
        "/repositories/hi/size?context=null": b"1",
        "/repositories/hi/size": b"3",
    }
    monkeypatch.setattr(azure_backup, "request", lambda _, path, *options: responses[path])
    with pytest.raises(ValueError, match="does not account for every explicit statement"):
        azure_backup.snapshot("graphdb-id")


@pytest.mark.parametrize("active", [b"0", b"1", b""])
def test_capture_requires_idle_repository_metrics(monkeypatch, active):
    metrics = b"graphdb_open_connections 0\ngraphdb_active_transactions " + active
    monkeypatch.setattr(azure_backup, "request", lambda *_: metrics)
    if active == b"0":
        azure_backup.require_idle("graphdb-id")
    else:
        with pytest.raises(ValueError, match="zero open connections and active transactions"):
            azure_backup.require_idle("graphdb-id")
