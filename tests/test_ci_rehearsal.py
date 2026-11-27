"""Guard the CI helper against contacting remote Docker or adopting existing resources."""

import importlib.util
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


spec = importlib.util.spec_from_file_location("ci_rehearsal", Path(__file__).resolve().parents[1] / ".github/scripts/rehearse.py")
ci = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci)


def directory_link(link, target):
    if sys.platform == "win32":
        import _winapi
        # Directory junctions do not require Windows symlink privileges.
        _winapi.CreateJunction(str(target), str(link))
    else:
        link.symlink_to(target, target_is_directory=True)


def test_bundle_discovery_accepts_one_directory_without_aliases(tmp_path):
    bundle = tmp_path / "test_azure_capture_transport0" / "capture"
    bundle.mkdir(parents=True)
    assert ci.find_captured_bundle(tmp_path) == bundle.resolve()


def test_bundle_discovery_deduplicates_pytest_current_directory_alias(tmp_path):
    test_directory = tmp_path / "test_azure_capture_transport0"
    bundle = test_directory / "capture"
    bundle.mkdir(parents=True)
    directory_link(tmp_path / "test_azure_capture_transportcurrent", test_directory)
    # Reproduce the original false ambiguity with real filesystem aliases.
    assert len(list(tmp_path.glob("test_azure_capture_transport*/capture"))) == 2
    assert ci.find_captured_bundle(tmp_path) == bundle.resolve()


def test_bundle_discovery_rejects_missing_bundle(tmp_path):
    with pytest.raises(RuntimeError, match="found 0 distinct locations"):
        ci.find_captured_bundle(tmp_path)


def test_bundle_discovery_rejects_distinct_bundles_even_with_alias(tmp_path):
    for index in (0, 1):
        (tmp_path / f"test_azure_capture_transport{index}" / "capture").mkdir(parents=True)
    directory_link(tmp_path / "test_azure_capture_transportcurrent", tmp_path / "test_azure_capture_transport1")
    with pytest.raises(RuntimeError, match="found 2 distinct locations"):
        ci.find_captured_bundle(tmp_path)


def test_bundle_discovery_rejects_alias_outside_capture_root(tmp_path):
    capture = tmp_path / "capture"
    capture.mkdir()
    outside = tmp_path / "outside"
    (outside / "capture").mkdir(parents=True)
    directory_link(capture / "test_azure_capture_transportcurrent", outside)
    with pytest.raises(RuntimeError, match="inside the capture root"):
        ci.find_captured_bundle(capture)


def test_bundle_discovery_after_real_pytest_capture(tmp_path):
    test_file = tmp_path / "test_capture.py"
    test_file.write_text(
        "def test_azure_capture_transport(tmp_path):\n    (tmp_path / 'capture').mkdir()\n", encoding="utf-8",
    )
    capture = tmp_path / "capture"
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", str(test_file), "--basetemp", str(capture)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    if sys.platform != "win32":
        assert (capture / "test_azure_capture_transportcurrent").is_symlink()
        assert len(list(capture.glob("test_azure_capture_transport*/capture"))) == 2
    assert ci.find_captured_bundle(capture) == (capture / "test_azure_capture_transport0" / "capture").resolve()


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
