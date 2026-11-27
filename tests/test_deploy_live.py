"""Opt-in, loopback-only smoke test for the complete deployment Compose stack."""

import json
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
import pytest


pytestmark = pytest.mark.skipif(os.getenv("HI_DEPLOY_LIVE") != "1", reason="Set HI_DEPLOY_LIVE=1")
ROOT = Path(__file__).resolve().parent.parent
APP_URL = "http://127.0.0.1:8080"
GRAPH_IRI = "urn:hi-app:graph:scenario:"


def local_stack(context, project):
    """Refuse remote daemons and existing deployment projects before any HTTP or restart."""
    if not re.fullmatch(r"hi-deploy-test-[a-z0-9]+", project):
        raise ValueError("Use a disposable hi-deploy-test-<id> project.")
    docker = ["docker", "--context", context]
    endpoint = subprocess.check_output(
        docker + ["context", "inspect", context, "--format", "{{.Endpoints.docker.Host}}"], text=True,
    ).strip()
    if not endpoint.startswith(("unix:///", "npipe:////./pipe/")):
        raise ValueError("Deployment smoke tests require a local Docker socket.")
    container = subprocess.check_output(docker + [
        "ps", "-q", "--filter", f"label=com.docker.compose.project={project}",
        "--filter", "label=com.docker.compose.service=web",
    ], text=True).strip()
    if not container or len(container.splitlines()) != 1:
        raise ValueError("Expected one web container in the disposable test project.")
    ports = json.loads(subprocess.check_output(
        docker + ["container", "inspect", "--format", "{{json .NetworkSettings.Ports}}", container], text=True,
    ))
    bindings = [binding for group in (ports or {}).values() for binding in (group or [])]
    if not bindings or any(binding["HostIp"] != "127.0.0.1" for binding in bindings):
        raise ValueError("Test web ports must bind only to loopback.")
    if not any(binding["HostPort"] == "8080" for binding in (ports.get("80/tcp") or [])):
        raise ValueError("Test HTTP must bind 127.0.0.1:8080.")
    return docker


def test_authenticated_container_workflow_and_restart():
    project = os.environ.get("HI_DEPLOY_TEST_PROJECT", "")
    docker = local_stack(os.environ.get("HI_DEPLOY_TEST_CONTEXT", "default"), project)
    password = os.environ["HI_DEPLOY_TEST_PASSWORD"]
    env_file = os.environ["HI_DEPLOY_ENV_FILE"]
    scenario_id = "deploy-test-" + uuid4().hex
    graph_iri = GRAPH_IRI + scenario_id
    auth = ("researcher", password)
    workbench_auth = ("graphadmin", os.environ["HI_DEPLOY_WORKBENCH_TEST_PASSWORD"])
    app_headers = {"Host": "app.localhost"}
    workbench_headers = {"Host": "workbench.localhost"}

    with (
        httpx.Client(base_url=APP_URL, headers=app_headers, auth=auth, trust_env=False, timeout=30) as app,
        httpx.Client(base_url=APP_URL, headers=workbench_headers, auth=workbench_auth, trust_env=False, timeout=30) as workbench,
    ):
        assert httpx.get(APP_URL + "/", headers=app_headers, trust_env=False).status_code == 401
        assert httpx.post(APP_URL + "/api/scenarios", headers=app_headers, trust_env=False).status_code == 401
        assert httpx.post(APP_URL + "/api/feedback", headers=app_headers, trust_env=False).status_code == 401
        assert httpx.get(APP_URL + "/repositories/hi", headers=workbench_headers, trust_env=False).status_code == 401
        assert httpx.get(APP_URL + "/repositories/hi", headers=workbench_headers, auth=auth, trust_env=False).status_code == 401
        assert httpx.get(APP_URL + "/", headers=app_headers, auth=workbench_auth, trust_env=False).status_code == 401

        page = app.get("/")
        assert page.status_code == 200 and "<div id=\"app\"" in page.text
        # Vite can place API code in a module-preloaded shared chunk.
        scripts = set(re.findall(r'(?:src|href)="(/assets/[^"<>]+\.js)"', page.text))
        assert scripts
        bundles = [app.get(script) for script in scripts]
        assert all(bundle.status_code == 200 for bundle in bundles)
        javascript = "\n".join(bundle.text for bundle in bundles)
        assert '"/api"' in javascript or '`/api`' in javascript
        assert "/scenarios/preview" in javascript
        assert "http://127.0.0.1:8000" not in javascript
        assert workbench.get("/", headers={**workbench_headers, "Accept": "text/html"}).status_code == 200

        scenario = json.loads((ROOT / "examples" / "s1.json").read_text(encoding="utf-8"))
        scenario["id"] = scenario_id
        assert app.post("/api/scenarios/preview", json={"id": scenario_id}).status_code == 422
        preview = app.post("/api/scenarios/preview", json=scenario)
        assert preview.status_code == 200 and preview.json()["triple_count"] == 127

        saved = app.post("/api/scenarios", json=scenario)
        assert saved.status_code == 201, saved.text
        try:
            location = saved.json()
            assert location["graph_iri"] == graph_iri
            assert location["workbench_url"] == "http://workbench.localhost:8080/"
            assert "graphdb:7200" not in saved.text
            assert app.post("/api/scenarios", json=scenario).status_code == 409

            def query_count():
                response = workbench.post(
                    "/repositories/hi", data={"query": f"SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{graph_iri}> {{ ?s ?p ?o }} }}", "infer": "false"},
                    headers={**workbench_headers, "Accept": "application/sparql-results+json"},
                )
                response.raise_for_status()
                return int(response.json()["results"]["bindings"][0]["n"]["value"])

            assert query_count() == 127
            team = app.get(f"/api/scenarios/{scenario_id}/team")
            assert team.status_code == 200, team.text
            before = team.json()
            assert len(before["members"]) == 2
            assert {member["name"] for member in before["members"]} == {"Human user", "AI assistant"}
            assert all(member["roles"][0]["label"] for member in before["members"])
            graph_link = urlsplit(location["workbench_graph_url"])
            assert workbench.get(graph_link.path + "?" + graph_link.query, headers={**workbench_headers, "Accept": "text/html"}).status_code == 200

            compose = docker + ["compose", "--env-file", env_file, "-f", "compose.deploy.yaml"]
            if os.environ.get("HI_DEPLOY_TEST_RESTORED") == "1":
                compose += ["-f", "compose.restored.yaml"]
            subprocess.run(
                compose + ["-p", project, "restart", "graphdb"],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                try:
                    if query_count() == 127:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(2)
            else:
                pytest.fail("Saved graph was unavailable after GraphDB restart")
            assert app.get(f"/api/scenarios/{scenario_id}/team").json() == before

            # Private feedback is stored outside GraphDB and survives replacing the
            # backend container. Only this verified disposable project is touched.
            sent = app.post("/api/feedback", json={"category": "improvement", "area": "builder", "message": "Synthetic deployment feedback."})
            assert sent.status_code == 201
            receipt = sent.json()
            assert app.get("/api/feedback").status_code == 405
            assert app.get(f"/api/feedback/{receipt['id']}").status_code == 404
            operator = compose + ["-p", project, "exec", "-T"]
            export = subprocess.run(operator + ["backend", "python", "-m", "infra.feedback", "export"],
                                    cwd=ROOT, check=True, capture_output=True, text=True)
            bundle = json.loads(export.stdout)
            assert any(record["id"] == receipt["id"] and record["message"] == "Synthetic deployment feedback."
                       for record in bundle["records"])
            subprocess.run(compose + ["-p", project, "up", "-d", "--no-deps", "--force-recreate", "backend"],
                           cwd=ROOT, check=True, capture_output=True, text=True)
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                try:
                    if app.get("/api/feedback").status_code == 405:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(1)
            else:
                pytest.fail("Backend unavailable after recreation")
            after = subprocess.run(operator + ["backend", "python", "-m", "infra.feedback", "export"],
                                   cwd=ROOT, check=True, capture_output=True, text=True)
            assert json.loads(after.stdout) == bundle
            target = "/tmp/feedback-restore-" + uuid4().hex
            subprocess.run(operator + ["-e", f"FEEDBACK_DIR={target}", "backend", "python", "-m", "infra.feedback", "restore"],
                           cwd=ROOT, input=export.stdout, check=True, capture_output=True, text=True)
            restored = subprocess.run(operator + ["-e", f"FEEDBACK_DIR={target}", "backend", "python", "-m", "infra.feedback", "export"],
                                      cwd=ROOT, check=True, capture_output=True, text=True)
            assert json.loads(restored.stdout) == bundle
            assert app.get(f"/api/scenarios/{scenario_id}/team").json() == before
        finally:
            # This test owns only this random graph. Never remove reference or user data.
            response = workbench.post(
                "/repositories/hi/statements", data={"update": f"DROP SILENT GRAPH <{graph_iri}>"},
            )
            response.raise_for_status()
