"""Manually rehearse native GraphDB recovery on disposable local Compose projects."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import tarfile

import httpx

from hi_scenario.graphdb import GraphDBError, GraphDBSettings, GraphDBStore
from infra import canonical
from infra.graphdb import ENDPOINT, REPOSITORY, ROOT, setup_repository
from infra.recovery_bundle import ARCHIVE, IMAGE_PLATFORM_FORMAT, MANIFEST, archive_digest, verify_graphdb_image


VERSION = "10.8.14"
IMAGE = f"ontotext/graphdb:{VERSION}"
PROJECT = re.compile(r"hi-recovery-[a-z0-9]+(?:-[a-z0-9]+)*-(source|restore)")
REPOSITORIES = "/rest/repositories"


def docker(context: str, *args: str) -> str:
    return subprocess.check_output(["docker", "--context", context, *args], text=True).strip()


def local_url(context: str, project: str, role: str, *, source_image: dict | None = None) -> str:
    if not PROJECT.fullmatch(project) or not project.endswith(f"-{role}"):
        raise ValueError(f"Use a disposable project named hi-recovery-<id>-{role}.")
    endpoint = docker(context, "context", "inspect", "--format", "{{.Endpoints.docker.Host}}", "--", context)
    if not endpoint.startswith(("unix:///", "npipe:////./pipe/")):
        raise ValueError("Recovery requires a local Docker socket context.")
    containers = docker(
        context, "ps", "-q", "--filter", f"label=com.docker.compose.project={project}",
        "--filter", "label=com.docker.compose.service=graphdb",
    ).splitlines()
    if len(containers) != 1:
        raise ValueError(f"Expected one running GraphDB container in {project}.")
    template = "\n".join((
        "{{json .Config.Labels}}", "{{.Config.Image}}", "{{json .Mounts}}", "{{json .NetworkSettings.Ports}}",
    ))
    labels, image, mounts, ports = docker(context, "container", "inspect", "--format", template, containers[0]).splitlines()
    if json.loads(labels).get("org.hi-project.recovery") != "true" or image != IMAGE:
        raise ValueError("Container must use the recovery Compose file and the pinned image.")
    mounts = json.loads(mounts)
    volume = f"{project}_graphdb-data"
    if len(mounts) != 1 or (mounts[0].get("Type"), mounts[0].get("Name"), mounts[0].get("Destination")) != (
        "volume", volume, "/opt/graphdb/home",
    ):
        raise ValueError("Container must mount only its own recovery volume at /opt/graphdb/home.")
    volume_template = "{{.Driver}}\n{{json .Options}}\n{{json .Labels}}"
    driver, options, volume_labels = docker(context, "volume", "inspect", "--format", volume_template, volume).splitlines()
    if driver != "local" or json.loads(options):
        raise ValueError("Recovery requires a standard local Docker volume.")
    volume_labels = json.loads(volume_labels) or {}
    if (volume_labels.get("com.docker.compose.project"), volume_labels.get("com.docker.compose.volume")) != (project, "graphdb-data"):
        raise ValueError("Volume is not owned by the named recovery Compose project.")
    published = {port: bindings for port, bindings in (json.loads(ports) or {}).items() if bindings}
    bindings = published.get("7200/tcp", [])
    if len(published) != 1 or len(bindings) != 1 or bindings[0].get("HostIp") != "127.0.0.1":
        raise ValueError("Recovery GraphDB must publish only one loopback port.")
    port = int(bindings[0]["HostPort"])
    if not 1 <= port <= 65535 or port == 7200:
        raise ValueError("Recovery GraphDB must use a separate loopback port from development.")
    if source_image is not None:
        image_id = docker(context, "container", "inspect", "--format", "{{.Image}}", containers[0])
        platform, digests = docker(
            context, "image", "inspect", "--format", IMAGE_PLATFORM_FORMAT + "\n{{json .RepoDigests}}", image_id,
        ).splitlines()
        verify_graphdb_image(source_image, platform, json.loads(digests))
        print(f"Verified GraphDB repository digest and platform {platform}.", flush=True)
    url = f"http://127.0.0.1:{port}"
    print(f"Verified Docker target {project} ({containers[0]}), volume {volume}, URL {url}", flush=True)
    return url


def check_version(client: httpx.Client) -> None:
    info = client.get("/rest/info/version").raise_for_status().json()
    if (info["productVersion"], info["productType"]) != (VERSION, "free"):
        raise ValueError(f"Expected GraphDB {VERSION} in its default Free mode.")


def list_repositories(client: httpx.Client) -> list[str]:
    return [repo["id"] for repo in client.get(REPOSITORIES).raise_for_status().json()]


def select(client: httpx.Client, query: str) -> list[dict]:
    response = client.post(
        ENDPOINT, data={"query": query, "infer": "false"},
        headers={"Accept": "application/sparql-results+json"},
    )
    return response.raise_for_status().json()["results"]["bindings"]


def snapshot(client: httpx.Client) -> dict:
    settings = client.get(f"{REPOSITORIES}/{REPOSITORY}").raise_for_status().json()["params"]
    named = select(client, "SELECT ?g (COUNT(*) AS ?n) WHERE { GRAPH ?g { ?s ?p ?o } } GROUP BY ?g")
    if any(row["g"]["type"] != "uri" for row in named):
        raise ValueError("Inventory requires IRI-named graphs.")
    # RDF4J's null context selects only stored default statements. GraphDB's SPARQL default can include named graphs.
    default = client.get(f"{ENDPOINT}/size", params={"context": "null"}).raise_for_status()
    return {
        "settings": settings,
        "named_graphs": {row["g"]["value"]: int(row["n"]["value"]) for row in named},
        "default_triples": int(default.text),
    }


def backup(client: httpx.Client, bundle: Path) -> None:
    before = snapshot(client)
    bundle.mkdir(mode=0o700)
    partial = bundle / f"{ARCHIVE}.partial"
    with client.stream("POST", "/rest/recovery/backup", json={
        "repositories": [REPOSITORY], "backupSystemData": False,
    }) as response:
        response.raise_for_status()
        if response.headers.get("Content-Type", "").split(";", 1)[0] != "application/x-tar":
            raise ValueError("GraphDB did not return a native backup archive.")
        with partial.open("xb") as stream:
            for chunk in response.iter_bytes():
                stream.write(chunk)
    with partial.open("rb") as stream:
        digest = archive_digest(stream)
    if snapshot(client) != before:
        raise ValueError("Source configuration or inventory changed during backup. Pause writers and retry with a new directory.")
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(), "graphdb_version": VERSION,
        "repository": REPOSITORY, "sha256": digest, "snapshot": before,
    }
    (bundle / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    partial.rename(bundle / ARCHIVE)
    print(f"Backed up {REPOSITORY} to {bundle / ARCHIVE} ({(bundle / ARCHIVE).stat().st_size} bytes, SHA-256 {digest}).")


def restore_or_verify(client: httpx.Client, bundle: Path, *, restore: bool, verify_canonical: bool = False) -> None:
    manifest = json.loads((bundle / MANIFEST).read_text(encoding="utf-8"))
    if (manifest["repository"], manifest["graphdb_version"]) != (REPOSITORY, VERSION):
        raise ValueError("Manifest does not describe repository hi on the pinned GraphDB version.")
    expected = manifest["snapshot"]
    if not isinstance(expected, dict) or expected.keys() != {"settings", "named_graphs", "default_triples"}:
        raise ValueError("Manifest is missing repository settings or graph counts.")
    with (bundle / ARCHIVE).open("rb") as stream:
        digest = archive_digest(stream)
        if digest != manifest["sha256"]:
            raise ValueError("Backup SHA-256 does not match the manifest.")
        print(f"Verified archive SHA-256 {digest}.", flush=True)
        if restore and list_repositories(client):
            raise ValueError("Restore target already contains repositories. Use a fresh recovery volume.")
        try:
            if restore:
                params = {"repositories": [REPOSITORY], "restoreSystemData": False, "removeStaleRepositories": False}
                client.post("/rest/recovery/restore", files={
                    "params": (None, json.dumps(params), "application/json"),
                    "file": (ARCHIVE, stream, "application/x-tar"),
                }).raise_for_status()
            if list_repositories(client) != [REPOSITORY]:
                raise ValueError("Recovery target must contain exactly repository hi.")
            actual = snapshot(client)
            for key, value in actual.items():
                if value != expected[key]:
                    raise ValueError(f"Restored repository differs from the manifest in {key}.")
            print("Verified repository settings and explicit triple counts:")
            for iri, count in sorted(actual["named_graphs"].items()):
                print(f"  <{iri}> {count}")
            print(f"  Default context: {actual['default_triples']}")
            if verify_canonical:
                run_canonical(client, "verify")
        except (GraphDBError, httpx.HTTPError, OSError, RuntimeError, ValueError, KeyError, TypeError,
                KeyboardInterrupt) as exc:
            if restore:
                raise RuntimeError(
                    f"{str(exc) or 'Restore interrupted.'}\n"
                    "Discard the disposable restore target and retry in a fresh recovery environment."
                ) from exc
            raise


def run_canonical(client: httpx.Client, command: str) -> None:
    # The Docker identity check authorizes this ephemeral loopback URL. The standalone canonical CLI keeps its port guard.
    store = GraphDBStore(client, GraphDBSettings(url=str(client.base_url)))
    if canonical.run(command, store, canonical.load_corpus()):
        raise ValueError(f"Canonical {command} failed.")


def seed(client: httpx.Client) -> None:
    if list_repositories(client):
        raise ValueError("Seed requires a fresh recovery source with no repositories.")
    setup_repository(client)
    run_canonical(client, "apply")
    # Synthetic data makes omissions outside the canonical verifier visible in the rehearsal.
    client.post(ENDPOINT + "/statements", data={"update": """
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        INSERT DATA {
            GRAPH <urn:hi-app:recovery-test:extra> {
                <urn:hi-app:recovery-test:extra> rdfs:label "Recovery rehearsal named graph" .
            }
            <urn:hi-app:recovery-test:default> rdfs:label "Recovery rehearsal default context" .
        }
    """}).raise_for_status()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True, help="local Docker socket context")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("seed", help="load canonical and synthetic data into a fresh source").add_argument("project")
    for name in ("backup", "restore", "verify"):
        command = commands.add_parser(name)
        command.add_argument("project")
        command.add_argument("bundle", type=Path, help="backup directory outside the checkout")
        if name != "backup":
            command.add_argument("--canonical", action="store_true", help="also verify references, S1–S7 and CQ1")
    args = parser.parse_args()
    try:
        role = "source" if args.command in ("seed", "backup") else "restore"
        source_image = None
        if args.command != "seed":
            args.bundle = args.bundle.resolve()
            if args.bundle.is_relative_to(ROOT.resolve()):
                raise ValueError("Keep backup bundles outside the Git checkout.")
        if role == "restore":
            manifest = json.loads((args.bundle / MANIFEST).read_text(encoding="utf-8"))
            if "source" in manifest or "rdf_sha256" in manifest:
                source_image = manifest.get("source")
                if not isinstance(source_image, dict):
                    raise ValueError("Production backup manifest is missing source image identity.")
        url = local_url(args.context, args.project, role, source_image=source_image)
        with httpx.Client(base_url=url, timeout=120, trust_env=False, follow_redirects=False) as client:
            check_version(client)
            if args.command == "seed":
                seed(client)
            elif args.command == "backup":
                backup(client, args.bundle)
            else:
                restore_or_verify(
                    client, args.bundle, restore=args.command == "restore", verify_canonical=args.canonical,
                )
    except (GraphDBError, httpx.HTTPError, OSError, RuntimeError, ValueError, KeyError, TypeError,
            subprocess.CalledProcessError, tarfile.TarError) as exc:
        parser.exit(1, f"Recovery {args.command} failed: {exc}\n")


if __name__ == "__main__":
    main()
