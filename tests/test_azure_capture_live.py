"""Opt-in production transport rehearsal against a fresh, disposable local source."""

import json
import os
import re
import subprocess
from urllib.parse import urlsplit

import httpx
import pytest

from infra import azure_backup, recovery, recovery_rdf
from infra.recovery_bundle import ARCHIVE, CHECKSUMS, DATASET, IMAGE_PLATFORM_FORMAT, graphdb_repo_digests


@pytest.mark.skipif(not os.getenv("HI_AZURE_CAPTURE_TEST_PROJECT"), reason="Requires a fresh disposable recovery source")
def test_azure_capture_transport(tmp_path, monkeypatch):
    project = os.environ["HI_AZURE_CAPTURE_TEST_PROJECT"]
    context = os.environ.get("HI_AZURE_CAPTURE_TEST_CONTEXT", "default")
    url = recovery.local_url(context, project, "source")
    endpoint = recovery.docker(context, "context", "inspect", "--format", "{{.Endpoints.docker.Host}}", "--", context)
    container = recovery.docker(
        context, "ps", "-q", "--no-trunc", "--filter", f"label=com.docker.compose.project={project}",
        "--filter", "label=com.docker.compose.service=graphdb",
    )
    assert re.fullmatch(r"[0-9a-f]{64}", container)
    image_id = recovery.docker(context, "container", "inspect", "--format", "{{.Image}}", container)
    platform, references = recovery.docker(
        context, "image", "inspect", "--format", IMAGE_PLATFORM_FORMAT + "\n{{json .RepoDigests}}", image_id,
    ).splitlines()
    digests = sorted(graphdb_repo_digests(json.loads(references)))
    assert digests

    if endpoint != "unix:///var/run/docker.sock":
        # Docker Desktop exposes a named pipe. Keep the same real exec/curl command and adapt only the socket selector.
        def local_docker(*args, stdout=subprocess.PIPE):
            assert args[:2] == ("exec", container)
            return subprocess.run(["docker", "--context", context, *args], stdout=stdout, stderr=subprocess.PIPE,
                                  timeout=135, check=True)

        monkeypatch.setattr(azure_backup, "docker", local_docker)
        print(f"Using real Docker CLI through local context {context} in place of the production Unix socket.")

    def fixture_identity(*_):
        # This seam substitutes the deployment topology only. Version and repository checks still run against GraphDB.
        azure_backup.check_graphdb(container)
        return {
            "host": "local-rehearsal", "graphdb_platform": platform, "graphdb_repo_digests": digests,
            "services": {"graphdb": {"container": container}, "web": {"container": "fixture-web", "paused": True},
                         "backend": {"container": "fixture-backend", "paused": True}},
        }

    monkeypatch.setattr(azure_backup, "inspect_source", fixture_identity)
    with httpx.Client(base_url=url, trust_env=False, timeout=30) as client:
        assert recovery.list_repositories(client) == [], "Use a fresh disposable volume."
        recovery.seed(client)
        transaction = client.post("/repositories/hi/transactions").raise_for_status()
        path = urlsplit(transaction.headers["Location"]).path
        assert re.fullmatch(r"/repositories/hi/transactions/[^/]+", path)
        try:
            metrics = azure_backup.request(container, "/rest/monitor/repository/hi").decode()
            for line in metrics.splitlines():
                if line.startswith(("graphdb_open_connections ", "graphdb_active_transactions ")):
                    print(line)
            with pytest.raises(ValueError, match="zero open connections and active transactions"):
                azure_backup.require_idle(container)
        finally:
            client.delete(path).raise_for_status()

    bundle = tmp_path / "capture"
    azure_backup.capture("local-rehearsal", tmp_path, "", "fixture-web", "fixture-backend", bundle)
    snapshot, _ = recovery_rdf.check_bundle(bundle)
    assert len(snapshot["named_graphs"]) == 10 and snapshot["default_triples"] == 1
    print(f"Captured {bundle}: {(bundle / ARCHIVE).stat().st_size} archive bytes, "
          f"{(bundle / DATASET).stat().st_size} RDF bytes, SHA-256 verified.")
    print((bundle / CHECKSUMS).read_text(encoding="ascii"), end="")
