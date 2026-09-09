"""Odoo accessibility + module-install smoke checks (profile R, read-only)."""

from __future__ import annotations

import pytest

import _smoke


@pytest.mark.r
def test_odoo_web_login_reachable():
    """Odoo web UI must answer 2xx/3xx on ``/web/login``.

    Positive control for the Odoo group: a down Odoo fails HERE, so the module
    and SKU probes below can report NOT_TESTED (mechanism) instead of failing for
    the wrong reason.
    """
    status, _body, error = _smoke.http_get(_smoke.ODOO_BASE_URL + "/web/login")
    if status is None:
        pytest.fail("service: Odoo web UI unreachable at %s/web/login (%s)" % (_smoke.ODOO_BASE_URL, error))
    assert 200 <= status < 400, (
        "service: Odoo web UI returned HTTP %s at %s/web/login" % (status, _smoke.ODOO_BASE_URL)
    )


@pytest.mark.r
def test_odoo_xmlrpc_reachable():
    """Odoo XML-RPC endpoint must answer ``common.version``.

    Positive control for the module/SKU probes, which are all expressed over
    XML-RPC. When this fails the XML-RPC probes become NOT_TESTED instead of
    masking the real failure with a misleading property result.
    """
    try:
        version = _smoke.odoo_version()
    except _smoke.OdooError as exc:
        pytest.fail("service: Odoo XML-RPC unreachable at %s (%s)" % (_smoke.ODOO_BASE_URL, exc))
    assert version.get("server_version"), "service: Odoo XML-RPC version response empty: %r" % version


@pytest.mark.r
def test_odoo_modules_installed():
    """Odoo ``sale`` and ``stock`` modules must be ``installed``.

    Deny-probe ("module NOT installed") with a paired must-succeed control: the
    ``base`` module, which is always installed in any Odoo database, must read
    back as ``installed`` too. If ``base`` cannot be confirmed, the probe
    mechanism is broken and the check reports NOT_TESTED rather than a false PASS
    or a false FAIL.
    """
    try:
        records = _smoke.odoo_execute(
            "ir.module.module",
            "search_read",
            [[["name", "in", ["base", "sale", "stock"]]]],
            {"fields": ["name", "state"]},
        )
    except _smoke.OdooError as exc:
        _smoke.not_tested("Odoo module probe unavailable: %s" % exc)

    states = {r.get("name"): r.get("state") for r in records}

    # positive control: base is always installed in a usable Odoo DB
    if states.get("base") != "installed":
        _smoke.not_tested(
            "positive control failed: base module state=%r (probe mechanism unreliable)"
            % states.get("base")
        )

    for module in ("sale", "stock"):
        assert states.get(module) == "installed", (
            "service: Odoo module '%s' not installed (state=%r)" % (module, states.get(module))
        )
