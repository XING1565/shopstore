"""pytest fixtures and report hooks for the QA smoke suite (ISSUE-0009).

Fixtures:
- :func:`wprofile` — gate for write-path (profile W) tests. Skips when
  ``SMOKE_PROFILE`` does not enable writes; FAILS (never skips) when the target
  environment is production.

Hooks:
- :func:`pytest_terminal_summary` — prints a PASS / FAIL / NOT_TESTED tally.
- :func:`pytest_sessionfinish` — when ``SMOKE_STRICT`` is set, a run that has any
  NOT_TESTED check exits non-zero so an untested run is never treated as green.
"""

from __future__ import annotations

import pytest

import _smoke


@pytest.fixture
def wprofile():
    """Allow a write-path test to run only on a non-production, write-enabled run."""
    if _smoke.is_production():
        pytest.fail(
            "write-path smoke test must NEVER run against production "
            "(SMOKE_TARGET=%s)" % _smoke.TARGET
        )
    if not _smoke.profile_runs_w():
        pytest.skip("write-path test; set SMOKE_PROFILE=w|all on staging to enable")
    return True


def _skip_reason(report) -> str:
    longrepr = getattr(report, "longrepr", None)
    if longrepr is None:
        return ""
    reason = str(longrepr[-1]) if isinstance(longrepr, tuple) and longrepr else str(longrepr)
    if reason.startswith("Skipped: "):
        reason = reason[len("Skipped: "):]
    return reason


def pytest_terminal_summary(terminalreporter, exitstatus, config):  # noqa: ARG001
    stats = terminalreporter.stats
    passed = len(stats.get("passed", []))
    failed = len(stats.get("failed", []))
    error = len(stats.get("error", []))
    not_tested = 0
    skipped = 0
    for rep in stats.get("skipped", []):
        if _skip_reason(rep).startswith("NOT_TESTED"):
            not_tested += 1
        else:
            skipped += 1

    lines = [
        "",
        "==> smoke summary: PASS=%d FAIL=%d NOT_TESTED=%d (profile-skipped=%d)"
        % (passed, failed + error, not_tested, skipped),
    ]
    if not_tested:
        lines.append("   WARNING: NOT_TESTED checks present - do not treat this run as green.")
    terminalreporter.write_sep("=", "smoke result")
    for line in lines:
        terminalreporter.write_line(line)


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    if _smoke.STRICT and _smoke.not_tested_count > 0:
        session.exitstatus = 2
