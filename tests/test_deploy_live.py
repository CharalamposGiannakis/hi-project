"""Opt-in, loopback-only smoke test for the complete deployment Compose stack."""

import json
import os
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


def test_authenticated_container_workflow_and_restart():
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
        assert httpx.get(APP_URL + "/repositories/hi", headers=workbench_headers, trust_env=False).status_code == 401
        assert httpx.get(APP_URL + "/repositories/hi", headers=workbench_headers, auth=auth, trust_env=False).status_code == 401
        assert httpx.get(APP_URL + "/", headers=app_headers, auth=workbench_auth, trust_env=False).status_code == 401

        page = app.get("/")
        assert page.status_code == 200 and "<div id=\"app\"" in page.text
        script = page.text.split('src="')[1].split('"')[0]
        bundle = app.get(script)
        assert bundle.status_code == 200
        assert '"/api"' in bundle.text or '`/api`' in bundle.text
        assert "/scenarios/preview" in bundle.text
        assert "http://127.0.0.1:8000" not in bundle.text
        assert workbench.get("/", headers={**workbench_headers, "Accept": "text/html"}).status_code == 200

        scenario = json.loads((ROOT / "examples" / "s1.json").read_text(encoding="utf-8"))
        scenario["id"] = scenario_id
        assert app.post("/api/scenarios/preview", json={"id": scenario_id}).status_code == 422
        preview = app.post("/api/scenarios/preview", json=scenario)
        assert preview.status_code == 200 and preview.json()["triple_count"] == 117

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

            assert query_count() == 117
            team = app.get(f"/api/scenarios/{scenario_id}/team")
            assert team.status_code == 200, team.text
            before = team.json()
            assert len(before["members"]) == 2
            assert {member["name"] for member in before["members"]} == {"Human user", "AI assistant"}
            assert all(member["roles"][0]["label"] for member in before["members"])
            graph_link = urlsplit(location["workbench_graph_url"])
            assert workbench.get(graph_link.path + "?" + graph_link.query, headers={**workbench_headers, "Accept": "text/html"}).status_code == 200

            subprocess.run(
                ["docker", "compose", "--env-file", env_file, "-f", "compose.deploy.yaml", "restart", "graphdb"],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                try:
                    if query_count() == 117:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(2)
            else:
                pytest.fail("Saved graph was unavailable after GraphDB restart")
            assert app.get(f"/api/scenarios/{scenario_id}/team").json() == before
        finally:
            # This test owns only this random graph. Never remove reference or user data.
            response = workbench.post(
                "/repositories/hi/statements", data={"update": f"DROP SILENT GRAPH <{graph_iri}>"},
            )
            response.raise_for_status()
