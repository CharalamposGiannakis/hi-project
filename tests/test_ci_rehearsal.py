"""Guard the CI helper against contacting remote Docker or adopting existing resources."""

import importlib.util
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest


spec = importlib.util.spec_from_file_location("ci_rehearsal", Path(__file__).resolve().parents[1] / ".github/scripts/rehearse.py")
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


def test_rehearsal_refuses_remote_docker_before_any_resource_operation(monkeypatch):
    calls = []

    def remote(context, *arguments, **_):
        calls.append((context, arguments))
        return SimpleNamespace(stdout="ssh://unapproved-host")

    monkeypatch.setattr(ci, "docker", remote)
    with pytest.raises(ValueError, match="local Docker socket"):
        ci.require_local("remote")
    assert len(calls) == 1 and calls[0][1][0] == "context"


@pytest.mark.parametrize("existing", ["volume", "container"])
def test_rehearsal_refuses_existing_resources_without_mutations(monkeypatch, existing):
    calls = []

    def inspect(_context, *arguments, **_):
        calls.append(arguments)
        if arguments[0] == "volume":
            return SimpleNamespace(stdout="hi-recovery-ci-test-source_graphdb-data" if existing == "volume" else "")
        assert arguments[0] == "ps"
        return SimpleNamespace(stdout="existing-container" if existing == "container" else "")

    monkeypatch.setattr(ci, "docker", inspect)
    with pytest.raises(ValueError, match="fresh"):
        ci.require_fresh("default", ["hi-recovery-ci-test-source"])
    assert all(arguments[0] in {"volume", "ps"} for arguments in calls)


def test_rehearsal_cleans_its_disposable_projects_after_partial_startup(monkeypatch, tmp_path):
    calls = []

    def fail_start(_context, *arguments, **_):
        calls.append(arguments)
        if "up" in arguments:
            raise subprocess.CalledProcessError(1, ["docker", "compose", "up"])
        return SimpleNamespace(stdout="", returncode=0)

    monkeypatch.setattr(ci, "docker", fail_start)
    with pytest.raises(subprocess.CalledProcessError):
        ci.rehearse("default", tmp_path)
    cleanup = [arguments for arguments in calls if "down" in arguments]
    assert len(cleanup) == 2
    assert all("--volumes" in arguments for arguments in cleanup)
    assert all(arguments[arguments.index("-p") + 1].startswith("hi-recovery-ci-") for arguments in cleanup)
