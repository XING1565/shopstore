"""Data-persistence-across-restart smoke check (profile W, staging ONLY).

Writes a uniquely-named probe record into Odoo, restarts the Odoo stack
(``docker compose down`` + ``up -d``, named volumes kept), then verifies the
record survived and cleans it up. Uses the ``QA-PERSIST-*`` namespace and the
``example.test`` domain — no real customer data.

Profile W is hard-gated (see :func:`wprofile`): it is skipped when writes are
disabled and FAILS outright if the target is production, so this check can never
run against a live store.
"""

from __future__ import annotations

import os
import time

import pytest

import _smoke

_MARKER_REF = "QA-PERSIST-%d-%d" % (int(time.time()), os.getpid())


def _marker_found() -> bool:
    ids = _smoke.odoo_execute(
        "res.partner", "search", [[["ref", "=", _MARKER_REF]]]
    )
    return bool(ids)


def _cleanup(partner_id) -> None:
    try:
        _smoke.odoo_execute("res.partner", "unlink", [[partner_id]])
    except _smoke.OdooError:
        # best-effort: never let cleanup mask the real verification result
        pass


@pytest.mark.w
def test_odoo_data_persists_across_restart(wprofile):
    if not _smoke.docker_available():
        _smoke.not_tested("docker unavailable; cannot restart the Odoo stack")

    try:
        partner_id = _smoke.odoo_execute(
            "res.partner",
            "create",
            [{
                "name": "QA Persistence Probe",
                "ref": _MARKER_REF,
                "company_type": "company",
                "email": "qa-persist@example.test",
            }],
        )
    except _smoke.OdooError as exc:
        _smoke.not_tested("cannot create persistence marker: %s" % exc)

    # Positive control (must succeed): the marker exists immediately after write.
    assert _marker_found(), "positive control: marker %s not found right after create" % _MARKER_REF

    rc, _out, err = _smoke.run_compose(_smoke.ODOO_COMPOSE, ["down"])
    assert rc == 0, "service: Odoo `docker compose down` failed: %s" % err
    rc, _out, err = _smoke.run_compose(_smoke.ODOO_COMPOSE, ["up", "-d"])
    assert rc == 0, "service: Odoo `docker compose up -d` failed: %s" % err

    if not _smoke.wait_for_http(_smoke.ODOO_BASE_URL + "/web/login", timeout=120):
        pytest.fail("service: Odoo did not become reachable after restart")

    try:
        # Deny-probe: the marker must survive the restart.
        assert _marker_found(), (
            "service: Odoo data did NOT persist across restart (marker %s vanished)" % _MARKER_REF
        )
    finally:
        _cleanup(partner_id)
