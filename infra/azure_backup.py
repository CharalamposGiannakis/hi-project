"""Capture the approved Azure source through its local Docker socket. No restore operation."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import tarfile
import time

from infra.recovery_bundle import ARCHIVE, CHECKSUMS, DATASET, MANIFEST, archive_digest, checksum_text, file_digest


PROJECT = "hi-project-deploy"
VOLUME = f"{PROJECT}_graphdb-data"
NETWORK = f"{PROJECT}_data"
VERSION = "10.8.14"
IMAGE = f"ontotext/graphdb:{VERSION}"
ENDPOINT = "/repositories/hi"


def docker(*args, stdout=subprocess.PIPE):
    env = {key: value for key, value in os.environ.items() if key not in {"DOCKER_HOST", "DOCKER_CONTEXT"}}
    return subprocess.run(
        ["docker", "--host", "unix:///var/run/docker.sock", *args], env=env,
        stdout=stdout, stderr=subprocess.PIPE, timeout=135, check=True,
    )


def request(container, path, *args, stream=None, media_type=None):
    # Use curl already present in the GraphDB image and keep the response body off the console.
    result = docker(
        "exec", container, "curl", "--disable", "--noproxy", "*", "--fail", "--silent", "--show-error",
        "--max-time", "120", "--write-out", "%{stderr}%{http_code} %{content_type}",
        *args, f"http://127.0.0.1:7200{path}", stdout=stream if stream is not None else subprocess.PIPE,
    )
    status, _, content_type = result.stderr.decode().strip().partition(" ")
    if status != "200" or (media_type and content_type.split(";", 1)[0] != media_type):
        raise ValueError(f"Unexpected GraphDB response for {path.split('?')[0]}.")
    return result.stdout


def inspect_source(host, deployment, revision):
    if socket.gethostname() != host:
        raise ValueError("Host does not match the approved Azure OS hostname.")
    head = subprocess.check_output(["git", "-C", str(deployment), "rev-parse", "HEAD"], text=True).strip()
    if not re.fullmatch(r"[0-9a-f]{40}", revision) or head != revision:
        raise ValueError("Deployment checkout differs from the approved deployed revision.")

    services = {}
    template = "\n".join((
        '{{index .Config.Labels "com.docker.compose.project.working_dir"}}', "{{.State.StartedAt}}",
        "{{.State.Paused}}", "{{.Config.Image}}", "{{.Image}}", "{{json .Mounts}}", "{{json .NetworkSettings.Ports}}",
    ))
    for service in ("graphdb", "backend", "web"):
        container = docker(
            "ps", "-q", "--no-trunc", "--filter", f"label=com.docker.compose.project={PROJECT}",
            "--filter", f"label=com.docker.compose.service={service}",
        ).stdout.decode().strip()
        if not re.fullmatch(r"[0-9a-f]{64}", container):
            raise ValueError(f"Expected exactly one running {PROJECT}/{service} container.")
        checkout, started, paused, image, image_id, mounts, ports = docker(
            "container", "inspect", "--format", template, container,
        ).stdout.decode().splitlines()
        if Path(checkout).resolve() != deployment:
            raise ValueError(f"{service} belongs to a different deployment checkout.")
        if service in {"graphdb", "backend"} and any((json.loads(ports) or {}).values()):
            raise ValueError(f"{service} must have no published host ports.")
        if service == "graphdb":
            storage = [(m.get("Type"), m.get("Name"), m.get("Destination")) for m in json.loads(mounts)]
            if paused != "false" or image != IMAGE or storage != [("volume", VOLUME, "/opt/graphdb/home")]:
                raise ValueError("GraphDB must be unpaused with the pinned image and production volume.")
        services[service] = {
            "container": container, "started_at": started, "paused": paused == "true", "image_id": image_id,
        }

    internal, members = docker(
        "network", "inspect", "--format", "{{.Internal}}\n{{json .Containers}}", NETWORK,
    ).stdout.decode().splitlines()
    graphdb = services["graphdb"]["container"]
    networks = docker("container", "inspect", "--format", "{{json .NetworkSettings.Networks}}", graphdb).stdout
    if (internal != "true" or set(json.loads(networks)) != {NETWORK}
            or set(json.loads(members)) != {service["container"] for service in services.values()}):
        raise ValueError("Unexpected access paths on the deployment data network.")
    version = json.loads(request(graphdb, "/rest/info/version"))
    if (version.get("productVersion"), version.get("productType")) != (VERSION, "free"):
        raise ValueError(f"Expected GraphDB {VERSION} Free.")
    repositories = json.loads(request(graphdb, "/rest/repositories"))
    if not any(repo.get("id") == "hi" and repo.get("local") is True for repo in repositories):
        raise ValueError("Expected the local repository hi in the verified GraphDB container.")
    platform, repo_digests = docker(
        "image", "inspect", "--format", "{{.Os}}/{{.Architecture}}\n{{json .RepoDigests}}",
        services["graphdb"]["image_id"],
    ).stdout.decode().splitlines()
    return {
        "host": host, "deployed_revision": revision, "graphdb_version": VERSION, "graphdb_edition": "free",
        "graphdb_platform": platform, "graphdb_repo_digests": json.loads(repo_digests) or [], "services": services,
    }


def snapshot(container):
    settings = json.loads(request(container, "/rest/repositories/hi"))["params"]
    if settings["ruleset"]["value"] != "empty" or str(settings["disableSameAs"]["value"]).lower() != "true":
        raise ValueError("Repository hi does not use the expected inference settings.")
    response = request(
        container, ENDPOINT, "--header", "Accept: application/sparql-results+json", "--data", "infer=false",
        "--data-urlencode", "query=SELECT ?g (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } } GROUP BY ?g",
    )
    named = json.loads(response)["results"]["bindings"]
    if any(row["g"]["type"] != "uri" for row in named):
        raise ValueError("Production recovery requires IRI-named graphs.")
    counts = {row["g"]["value"]: int(row["n"]["value"]) for row in named}
    default = int(request(container, f"{ENDPOINT}/size?context=null"))
    if sum(counts.values()) + default != int(request(container, f"{ENDPOINT}/size")):
        raise ValueError("Graph inventory does not account for every explicit statement in repository hi.")
    return {"settings": settings, "named_graphs": counts, "default_triples": default}


def require_idle(container):
    metrics = request(container, "/rest/monitor/repository/hi").decode()
    for gauge in ("graphdb_open_connections", "graphdb_active_transactions"):
        if not re.search(rf"^{gauge}[ \t]+0(?:\.0+)?[ \t]*$", metrics, re.MULTILINE):
            raise ValueError("GraphDB has not reported zero open connections and active transactions. Check the write pause.")


def capture(host, deployment, revision, paused_web, paused_backend, bundle):
    source = inspect_source(host, deployment, revision)
    for service, expected_id in (("web", paused_web), ("backend", paused_backend)):
        state = source["services"][service]
        if state["container"] != expected_id or not state["paused"]:
            raise ValueError(f"The approved {service} container must be paused before capture.")
    container = source["services"]["graphdb"]["container"]
    require_idle(container)
    time.sleep(2)
    require_idle(container)
    created = datetime.now(timezone.utc).isoformat()
    before = snapshot(container)
    bundle.mkdir(mode=0o700)
    rdf_partial = bundle / f"{DATASET}.partial"
    archive_partial = bundle / f"{ARCHIVE}.partial"
    with rdf_partial.open("xb") as stream:
        request(container, f"{ENDPOINT}/statements?infer=false", "--header", "Accept: application/n-quads",
                stream=stream, media_type="application/n-quads")
    if not rdf_partial.stat().st_size:
        raise ValueError("The expected research repository exported no RDF.")
    with archive_partial.open("xb") as stream:
        request(container, "/rest/recovery/backup", "--header", "Content-Type: application/json",
                "--data", '{"repositories":["hi"],"backupSystemData":false}',
                stream=stream, media_type="application/x-tar")
    with archive_partial.open("rb") as stream:
        archive_sha = archive_digest(stream)
    rdf_sha = file_digest(rdf_partial)
    if snapshot(container) != before or inspect_source(host, deployment, revision) != source:
        raise ValueError("Deployment identity, write pause, repository settings, or inventory changed during capture.")
    require_idle(container)
    manifest = {
        "created_utc": created, "repository": "hi", "graphdb_version": VERSION, "source": source,
        "sha256": archive_sha, "rdf_sha256": rdf_sha, "snapshot": before,
    }
    (bundle / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rdf_partial.rename(bundle / DATASET)
    archive_partial.rename(bundle / ARCHIVE)
    checksums = bundle / f"{CHECKSUMS}.partial"
    checksums.write_text(checksum_text(bundle, archive_sha, rdf_sha), encoding="ascii")
    checksums.rename(bundle / CHECKSUMS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "capture"))
    parser.add_argument("--host", required=True, help="approved Azure OS hostname")
    parser.add_argument("--deployment", required=True, type=Path, help="active deployment checkout")
    parser.add_argument("--revision", required=True, help="full deployed SHA from the deployment record")
    parser.add_argument("--paused-web", help="full Caddy container ID from the approved preflight")
    parser.add_argument("--paused-backend", help="full backend container ID from the approved preflight")
    parser.add_argument("--bundle", type=Path, help="new directory in protected staging outside Git")
    args = parser.parse_args()
    try:
        deployment = args.deployment.resolve(strict=True)
        if args.action == "check":
            print(json.dumps(inspect_source(args.host, deployment, args.revision), indent=2))
        else:
            if args.bundle is None or not args.paused_web or not args.paused_backend:
                raise ValueError("Capture requires --bundle, --paused-web, and --paused-backend from the preflight.")
            bundle = args.bundle.resolve()
            if any(bundle.is_relative_to(root) for root in (deployment, Path(__file__).resolve().parents[1])):
                raise ValueError("Use a new staging directory outside the Git checkouts.")
            capture(args.host, deployment, args.revision, args.paused_web, args.paused_backend, bundle)
            print(f"Created production backup bundle {bundle}.")
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, tarfile.TarError) as exc:
        parser.exit(1, f"Azure backup {args.action} failed: {exc}\n")


if __name__ == "__main__":
    main()
