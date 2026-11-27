"""Required CI suites must execute their checks; ordinary pytest keeps opt-in skips."""

import os
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / ".github/scripts/required_tests.py"


def run_tests(directory, *arguments, required=True, enabled=False):
    env = {**os.environ, "HI_GRAPHDB_LIVE": "0", "HI_DEPLOY_LIVE": "0", "HI_NEBULA_LIVE": "0",
           "HI_AZURE_CAPTURE_TEST_PROJECT": "", "NEBULA_API_KEY": "", "TEST_LIVE_ENABLED": "1" if enabled else "0"}
    command = [sys.executable, str(RUNNER)] if required else [sys.executable, "-m", "pytest"]
    return subprocess.run(command + ["-q", "-p", "no:cacheprovider", *map(str, arguments)],
                          cwd=directory, env=env, capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("source", [
    "import pytest\n@pytest.mark.skip(reason='disabled')\ndef test_live(): pass\n",
    "import pytest\ndef test_live(): pytest.skip('unavailable')\n",
    "import pytest\n@pytest.fixture\ndef service(): pytest.skip('unavailable')\ndef test_live(service): pass\n",
    "import pytest\n@pytest.mark.xfail(reason='not verified')\ndef test_live(): assert False\n",
])
def test_required_runner_rejects_skips_even_when_other_tests_pass(tmp_path, source):
    (tmp_path / "test_live.py").write_text(source, encoding="utf-8")
    (tmp_path / "test_unit.py").write_text("def test_unit(): pass\n", encoding="utf-8")
    result = run_tests(tmp_path, tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Required tests were skipped; verification failed" in result.stdout
    assert "test_live.py::test_live" in result.stdout


def test_required_runner_rejects_collection_skip_with_passing_tests(tmp_path):
    (tmp_path / "test_live.py").write_text("import pytest\npytest.skip('disabled', allow_module_level=True)\n", encoding="utf-8")
    (tmp_path / "test_unit.py").write_text("def test_unit(): pass\n", encoding="utf-8")
    result = run_tests(tmp_path, tmp_path)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Required tests were skipped; verification failed" in result.stdout


def test_opt_in_still_skips_locally_and_passes_when_explicitly_enabled(tmp_path):
    test = tmp_path / "test_live.py"
    test.write_text("import os, pytest\n@pytest.mark.skipif(os.getenv('TEST_LIVE_ENABLED') != '1', reason='opt in')\n"
                    "def test_live(): pass\n", encoding="utf-8")
    ordinary = run_tests(tmp_path, test, required=False)
    required = run_tests(tmp_path, test)
    enabled = run_tests(tmp_path, test, enabled=True)
    assert ordinary.returncode == 0 and "1 skipped" in ordinary.stdout
    assert required.returncode == 1
    assert enabled.returncode == 0 and "1 passed" in enabled.stdout


@pytest.mark.parametrize("filename", [
    "test_canonical_live.py", "test_graphdb_live.py", "test_azure_capture_live.py", "test_deploy_live.py",
])
def test_real_live_suite_cannot_pass_required_verification_when_opt_in_is_missing(tmp_path, filename):
    result = run_tests(tmp_path, ROOT / "tests" / filename)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Required tests were skipped; verification failed" in result.stdout


@pytest.mark.parametrize(("source", "arguments", "code"), [
    ("def test_failure(): assert False\n", (), 1),
    ("raise RuntimeError('collection failed')\n", (), 2),
    ("def test_pass(): pass\n", ("-k", "absent"), 5),
])
def test_required_runner_preserves_failures_collection_errors_and_empty_selection(tmp_path, source, arguments, code):
    test = tmp_path / "test_case.py"
    test.write_text(source, encoding="utf-8")
    result = run_tests(tmp_path, test, *arguments)
    assert result.returncode == code, result.stdout + result.stderr
