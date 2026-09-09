"""Marketplace Core health / readiness smoke checks (profile R, read-only)."""

from __future__ import annotations

import pytest

import _smoke


@pytest.mark.r
def test_core_health_ok():
    """``GET /health`` must return 200 with ``{"status": "ok"}`` (liveness)."""
    status, body, error = _smoke.http_json(_smoke.CORE_BASE_URL + "/health")
    if status is None:
        pytest.fail("service: Core unreachable at %s/health (%s)" % (_smoke.CORE_BASE_URL, error))
    assert status == 200, "service: Core /health returned HTTP %s" % status
    assert body and body.get("status") == "ok", "service: Core /health body not ok: %r" % body


@pytest.mark.r
def test_core_ready_db_ok():
    """``GET /ready`` must report the database dependency as ``ok``.

    This is the database-readiness probe. Its must-succeed positive control is
    ``test_core_health_ok``: /health does NOT touch the database, so when /ready
    fails while /health passes we can attribute the failure to the database (and
    the 503 body names ``database`` as the unhealthy dependency).
    """
    status, body, error = _smoke.http_json(_smoke.CORE_BASE_URL + "/ready")
    if status is None:
        pytest.fail("service: Core unreachable at %s/ready (%s)" % (_smoke.CORE_BASE_URL, error))
    if status == 503:
        dep = None
        if isinstance(body, dict):
            dep = (body.get("error") or {}).get("code") or body.get("checks")
        pytest.fail("service: Core /ready reports dependency not ready (503, %s)" % dep)
    assert status == 200, "service: Core /ready returned HTTP %s" % status
    assert body and body.get("status") == "ok", "service: Core /ready body not ok: %r" % body
    checks = body.get("checks") or {}
    assert checks.get("database", {}).get("status") == "ok", (
        "service: Core database not ready: %r" % checks
    )
