"""Run explicitly required pytest suites, failing if collection or execution skips a check."""

from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class RequireNoSkips:
    def __init__(self):
        self.skipped = set()

    def pytest_collectreport(self, report):
        if report.skipped:
            self.skipped.add(report.nodeid)

    def pytest_runtest_logreport(self, report):
        if report.skipped:
            self.skipped.add(report.nodeid)

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus):
        if self.skipped and exitstatus == pytest.ExitCode.OK:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED

    def pytest_terminal_summary(self, terminalreporter):
        if self.skipped:
            terminalreporter.write_sep("=", "Required tests were skipped; verification failed", red=True)
            for nodeid in sorted(self.skipped):
                terminalreporter.write_line(nodeid)


if __name__ == "__main__":
    raise SystemExit(pytest.main(sys.argv[1:], plugins=[RequireNoSkips()]))
