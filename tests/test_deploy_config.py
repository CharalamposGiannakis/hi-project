"""Render deployment configuration without a daemon, credentials, or cloud access."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from test_deploy_live import local_stack

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="Docker Compose CLI is required")


@pytest.fixture
def compose(tmp_path):
    empty_env = tmp_path / "empty.env"
    empty_env.write_text("", encoding="utf-8")
    env = {key: value for key, value in os.environ.items() if not key.startswith("COMPOSE_")}
    # Override every interpolated deployment value; never read a real environment file.
    env.update({
        "APP_SITE_ADDRESS": "https://app.example.invalid",
        "WORKBENCH_SITE_ADDRESS": "https://workbench.example.invalid",
        "WORKBENCH_PUBLIC_URL": "https://workbench.example.invalid",
        "APP_AUTH_USER": "test-researcher", "APP_AUTH_PASSWORD_HASH": "test-only-hash",
        "WORKBENCH_AUTH_USER": "test-operator", "WORKBENCH_AUTH_PASSWORD_HASH": "test-only-other-hash",
        "NEBULA_API_KEY": "", "NEBULA_MODEL": "FAST.gpt-oss:120b",
        "GRAPHDB_APPROVED_SCENARIO_IDS": "", "HTTP_BIND": "80", "HTTPS_BIND": "443",
    })
    env.pop("RESTORED_GRAPHDB_VOLUME", None)

    def render(*, restored=False, volume=None, project=None):
        command = ["docker", "compose", "--env-file", str(empty_env), "-f", "compose.deploy.yaml"]
        if restored:
            command += ["-f", "compose.restored.yaml"]
        if project:
            command += ["-p", project]
        values = dict(env)
        if volume is not None:
            values["RESTORED_GRAPHDB_VOLUME"] = volume
        result = subprocess.run(command + ["config", "--format", "json"], cwd=ROOT, env=values,
                                capture_output=True, text=True, timeout=30)
        return result

    return render


def test_default_deployment_remains_portable_and_private(compose):
    result = compose()
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    assert config["volumes"]["graphdb-data"]["name"] == "hi-project-deploy_graphdb-data"
    assert not config["volumes"]["graphdb-data"].get("external", False)
    assert config["services"]["graphdb"]["image"] == "ontotext/graphdb:10.8.14"
    assert not config["services"]["graphdb"].get("ports")
    assert not config["services"]["backend"].get("ports")
    assert config["networks"]["data"]["internal"] is True
    assert config["services"]["backend"]["environment"]["GRAPHDB_URL"] == "http://graphdb:7200"
    assert config["services"]["backend"]["environment"]["FEEDBACK_DIR"] == "/data/feedback"
    assert config["services"]["backend"]["volumes"] == [
        {"type": "volume", "source": "feedback-data", "target": "/data/feedback", "volume": {}},
    ]
    assert config["volumes"]["feedback-data"]["name"] == "hi-project-deploy_feedback-data"
    assert not any(mount.get("source") == "feedback-data" for name in ("web", "graphdb")
                   for mount in config["services"][name].get("volumes", []))
    assert config["services"]["web"]["environment"]["APP_SITE_ADDRESS"] == "https://app.example.invalid"
    assert all(mount["type"] == "volume" for service in config["services"].values()
               for mount in service.get("volumes", []))


@pytest.mark.parametrize("volume", [None, ""])
def test_restored_deployment_requires_explicit_volume(compose, volume):
    result = compose(restored=True, volume=volume)
    assert result.returncode != 0
    assert "RESTORED_GRAPHDB_VOLUME" in result.stderr


def test_restore_overlay_changes_only_graphdb_storage(compose):
    base = compose()
    restored = compose(restored=True, volume="hi-recovery-migration-restore_graphdb-data")
    assert base.returncode == restored.returncode == 0, restored.stderr
    original, migrated = json.loads(base.stdout), json.loads(restored.stdout)
    assert migrated["volumes"]["graphdb-data"] == {
        "name": "hi-recovery-migration-restore_graphdb-data", "external": True,
    }
    migrated["volumes"]["graphdb-data"] = original["volumes"]["graphdb-data"]
    assert migrated == original


def test_migration_rehearsal_has_independent_application_volumes(compose):
    result = compose(restored=True, volume="hi-recovery-fixture-restore_graphdb-data",
                     project="hi-deploy-test-fixture")
    assert result.returncode == 0, result.stderr
    config = json.loads(result.stdout)
    assert config["volumes"]["graphdb-data"]["external"] is True
    assert config["volumes"]["caddy-data"]["name"] == "hi-deploy-test-fixture_caddy-data"
    assert config["volumes"]["caddy-config"]["name"] == "hi-deploy-test-fixture_caddy-config"
    assert config["volumes"]["feedback-data"]["name"] == "hi-deploy-test-fixture_feedback-data"


@pytest.mark.parametrize("project", ["hi-project-deploy", "hi-project", ""])
def test_live_smoke_refuses_non_disposable_projects(monkeypatch, project):
    monkeypatch.setattr(subprocess, "check_output", lambda *_a, **_k: pytest.fail("No Docker call expected"))
    with pytest.raises(ValueError, match="disposable"):
        local_stack("default", project)


def test_live_smoke_refuses_remote_docker_before_inspection(monkeypatch):
    calls = []

    def remote(command, **_):
        calls.append(command)
        return "ssh://unapproved-host"

    monkeypatch.setattr(subprocess, "check_output", remote)
    with pytest.raises(ValueError, match="local Docker socket"):
        local_stack("remote", "hi-deploy-test-fixture")
    assert len(calls) == 1


@pytest.mark.parametrize("ports, error", [
    ({"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]}, "only to loopback"),
    ({"80/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8081"}]}, "127.0.0.1:8080"),
    ({"80/tcp": None, "443/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8443"}]}, "127.0.0.1:8080"),
])
def test_live_smoke_checks_loopback_http_binding(monkeypatch, ports, error):
    responses = iter(["unix:///var/run/docker.sock", "test-container", json.dumps(ports)])
    monkeypatch.setattr(subprocess, "check_output", lambda *_a, **_k: next(responses))
    with pytest.raises(ValueError, match=error):
        local_stack("default", "hi-deploy-test-fixture")
