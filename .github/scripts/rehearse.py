"""Exercise existing recovery tools on disposable local Docker projects, without cloud access."""

import argparse
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
from uuid import uuid4

import httpx


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from infra import recovery_rdf  # noqa: E402


def run(arguments, *, env=None, capture=False, check=True):
    return subprocess.run(arguments, cwd=ROOT, env=env, text=True, capture_output=capture,
                          check=check, timeout=600)


def docker(context, *arguments, **options):
    return run(["docker", "--context", context, *arguments], **options)


def require_local(context):
    endpoint = docker(context, "context", "inspect", context, "--format",
                      "{{.Endpoints.docker.Host}}", capture=True).stdout.strip()
    if not endpoint.startswith(("unix:///", "npipe:////./pipe/")):
        raise ValueError("The rehearsal requires a local Docker socket, never a remote context or tunnel.")


def require_fresh(context, projects):
    volumes = set(docker(context, "volume", "ls", "--format", "{{.Name}}", capture=True).stdout.splitlines())
    for project in projects:
        containers = docker(context, "ps", "-aq", "--filter", f"label=com.docker.compose.project={project}",
                            capture=True).stdout.strip()
        if containers or any(volume.startswith(project + "_") for volume in volumes):
            raise ValueError("Rehearsal projects must be fresh; existing resources will not be changed.")


def find_captured_bundle(capture_root):
    root = capture_root.resolve(strict=True)
    # Pytest's numbered directory and its "current" link can both match the glob.
    bundles = {path.resolve(strict=True) for path in root.glob("test_azure_capture_transport*/capture")}
    if any(not path.is_relative_to(root) or not path.is_dir() for path in bundles):
        raise RuntimeError("Synthetic captured bundles must be directories inside the capture root.")
    if len(bundles) != 1:
        raise RuntimeError(f"Expected one synthetic captured bundle; found {len(bundles)} distinct locations.")
    return bundles.pop()


def test_settings(context, path, volume):
    passwords = [secrets.token_urlsafe(24), secrets.token_urlsafe(24)]
    hashes = []
    for password in passwords:
        if os.getenv("GITHUB_ACTIONS") == "true":
            print(f"::add-mask::{password}", flush=True)
        try:
            # Test-only passwords, never production credentials. Keep this image aligned with frontend/Dockerfile.
            hashed = docker(context, "run", "--rm", "caddy:2.11.6-alpine", "caddy", "hash-password",
                            "--plaintext", password, capture=True).stdout.strip()
        except subprocess.SubprocessError:
            raise RuntimeError("Could not hash the synthetic test password.") from None
        if os.getenv("GITHUB_ACTIONS") == "true":
            print(f"::add-mask::{hashed}", flush=True)
        hashes.append(hashed)
    settings = {
        "APP_SITE_ADDRESS": "http://app.localhost", "WORKBENCH_SITE_ADDRESS": "http://workbench.localhost",
        "WORKBENCH_PUBLIC_URL": "http://workbench.localhost:8080",
        "APP_AUTH_USER": "researcher", "APP_AUTH_PASSWORD_HASH": hashes[0],
        "WORKBENCH_AUTH_USER": "graphadmin", "WORKBENCH_AUTH_PASSWORD_HASH": hashes[1],
        "HTTP_BIND": "127.0.0.1:8080", "HTTPS_BIND": "127.0.0.1:8443",
        "RESTORED_GRAPHDB_VOLUME": volume, "NEBULA_API_KEY": "", "GRAPHDB_APPROVED_SCENARIO_IDS": "",
    }
    with path.open("x", encoding="utf-8") as stream:
        os.chmod(path, 0o600)
        stream.write("".join(f"{name}='{value}'\n" for name, value in settings.items()))
    return passwords, settings


def verify_application(bundle, passwords):
    expected, source = recovery_rdf.check_bundle(bundle)
    with httpx.Client(base_url="http://127.0.0.1:8080", headers={"Host": "app.localhost"},
                      auth=("researcher", passwords[0]), trust_env=False, timeout=30) as app:
        for index in range(1, 8):
            team = app.get(f"/api/scenarios/s{index}/team").raise_for_status().json()
            scenario = json.loads((ROOT / f"examples/s{index}.json").read_text(encoding="utf-8"))
            assert {member["name"] for member in team["members"]} == {agent["name"] for agent in scenario["agents"]}
        scenario = json.loads((ROOT / "examples/s2.json").read_text(encoding="utf-8"))
        result = app.post("/api/explorer/query", json={
            "scope": "combined", "question_id": "cq1",
            "uploads": [{"id": "ci-snapshot", "file_name": "synthetic-s2.json", "scenario": scenario}],
        }).raise_for_status().json()
        assert len(result["sources"]) == 8 and result["rows"]
        assert {item["publication_status"] for item in result["sources"]} == {"provisional", "reference"}
    with httpx.Client(base_url="http://127.0.0.1:8080", headers={"Host": "workbench.localhost"},
                      auth=("graphadmin", passwords[1]), trust_env=False, timeout=30) as workbench:
        recovery_rdf.verify_restored(workbench, expected, source)
    print("Verified restored S1–S7, Explorer provenance/rollback, and complete explicit RDF after restart.", flush=True)


def rehearse(context, work):
    identifier = uuid4().hex[:12]
    source = f"hi-recovery-ci-{identifier}-source"
    target = f"hi-recovery-ci-{identifier}-restore"
    project = f"hi-deploy-test-{identifier}"
    require_fresh(context, [source, target, project])  # Before cleanup is authorized for these names.
    env_file = work / "deployment.env"
    # Do not inherit real deployment settings when the helper is run on a developer's machine.
    excluded = {"APP_SITE_ADDRESS", "WORKBENCH_SITE_ADDRESS", "WORKBENCH_PUBLIC_URL", "APP_AUTH_USER",
                "APP_AUTH_PASSWORD_HASH", "WORKBENCH_AUTH_USER", "WORKBENCH_AUTH_PASSWORD_HASH", "HTTP_BIND",
                "HTTPS_BIND", "RESTORED_GRAPHDB_VOLUME", "GRAPHDB_APPROVED_SCENARIO_IDS"}
    env = {key: value for key, value in os.environ.items() if key not in excluded and not key.startswith("COMPOSE_")}
    env.update(HI_NEBULA_LIVE="0", NEBULA_API_KEY="")

    def recovery(project_name, *arguments, **options):
        return docker(context, "compose", "-f", "compose.recovery.yaml", "-p", project_name,
                      *arguments, env=env, **options)

    def deployment(*arguments, **options):
        return docker(context, "compose", "--env-file", str(env_file), "-f", "compose.deploy.yaml",
                      "-f", "compose.restored.yaml", "-p", project, *arguments, env=env, **options)

    def python(*arguments, extra_env=None):
        run([sys.executable, *arguments], env={**env, **(extra_env or {})})

    try:
        recovery(source, "up", "-d", "--wait", "--wait-timeout", "180")
        python("-m", "pytest", "-q", "-s", "tests/test_azure_capture_live.py", "--basetemp", str(work / "capture"),
               extra_env={"HI_AZURE_CAPTURE_TEST_PROJECT": source, "HI_AZURE_CAPTURE_TEST_CONTEXT": context})
        captured = find_captured_bundle(work / "capture")
        bundle = work / "retrieved"
        shutil.copytree(captured, bundle)
        if (captured / "SHA256SUMS").read_bytes() != (bundle / "SHA256SUMS").read_bytes():
            raise RuntimeError("Checksum list changed during synthetic retrieval.")
        python("-m", "infra.recovery_rdf", "check", str(bundle))
        recovery(source, "stop")
        recovery(target, "up", "-d", "--pull", "never", "--wait", "--wait-timeout", "180")
        python("-m", "infra.recovery", "--context", context, "restore", target, str(bundle), "--canonical")
        python("-m", "infra.recovery_rdf", "verify", "--context", context, target, str(bundle))
        recovery(target, "down")  # Retain the verified volume; never run two GraphDB processes against it.

        passwords, _ = test_settings(context, env_file, target + "_graphdb-data")
        deployment("build")
        deployment("up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "180")
        python("-m", "pytest", "-q", "tests/test_deploy_live.py", extra_env={
            "HI_DEPLOY_LIVE": "1", "HI_DEPLOY_TEST_CONTEXT": context, "HI_DEPLOY_TEST_PROJECT": project,
            "HI_DEPLOY_ENV_FILE": str(env_file), "HI_DEPLOY_TEST_PASSWORD": passwords[0],
            "HI_DEPLOY_WORKBENCH_TEST_PASSWORD": passwords[1], "HI_DEPLOY_TEST_RESTORED": "1",
        })
        verify_application(bundle, passwords)
    except BaseException:
        if env_file.exists():
            deployment("logs", "--tail", "100", check=False)
        raise
    finally:
        # Only names proven absent before this run, on the verified local daemon.
        results = []
        if env_file.exists():
            results.append(deployment("down", "--volumes", "--rmi", "local", check=False))
        results.extend(recovery(name, "down", "--volumes", check=False) for name in (source, target))
        if any(result.returncode for result in results):
            raise RuntimeError("Disposable rehearsal cleanup failed; inspect the printed project names.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", default="default", help="local Docker context; e.g. desktop-linux on Windows")
    args = parser.parse_args()
    require_local(args.context)
    with tempfile.TemporaryDirectory(prefix="hi-ci-recovery-") as directory:
        rehearse(args.context, Path(directory))


if __name__ == "__main__":
    main()
