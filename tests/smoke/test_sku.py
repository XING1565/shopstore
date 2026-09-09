"""Canonical test-SKU existence smoke checks (profile R, read-only).

The two canonical SKUs (``DEMO-SKU-001`` / ``DEMO-SKU-002``) are seeded
idempotently by ISSUE-0008 into both Woo and Odoo. Both must exist and each SKU
must be unique. No real customer data is involved: SKUs use the fixed ``DEMO-SKU-###``
namespace and ``example.test`` domain.
"""

from __future__ import annotations

import pytest

import _smoke


@pytest.mark.r
def test_odoo_sku_exist_unique():
    """Each canonical SKU must exist exactly once in Odoo ``product.template``.

    Positive control: the ``product.template`` model itself must be queryable
    (``search_count`` returns an int). If the model cannot be queried, the probe
    mechanism is broken and the check reports NOT_TESTED.
    """
    try:
        count = _smoke.odoo_execute("product.template", "search_count", [[]])
    except _smoke.OdooError as exc:
        _smoke.not_tested("Odoo SKU probe unavailable: %s" % exc)

    if not isinstance(count, int):
        _smoke.not_tested("positive control failed: product.template search_count=%r" % count)

    try:
        records = _smoke.odoo_execute(
            "product.template",
            "search_read",
            [[["default_code", "in", list(_smoke.CANONICAL_SKUS)]]],
            {"fields": ["default_code"]},
        )
    except _smoke.OdooError as exc:
        _smoke.not_tested("Odoo SKU search unavailable: %s" % exc)

    found = {}
    for rec in records:
        code = rec.get("default_code")
        found[code] = found.get(code, 0) + 1

    for sku in _smoke.CANONICAL_SKUS:
        assert found.get(sku, 0) == 1, (
            "service: Odoo SKU %s not unique/existing (found=%d)" % (sku, found.get(sku, 0))
        )


@pytest.mark.r
def test_woo_sku_exist():
    """Each canonical SKU must exist in Woo.

    Read mechanism: WooCommerce REST API when ``WOO_CONSUMER_KEY``/``SECRET`` are
    set, otherwise ``wp`` inside the running Woo container. When neither is
    available the check reports NOT_TESTED; the positive control for Woo being up
    is ``test_woo_front_reachable``.
    """
    present = _smoke.woo_sku_ids()
    if present is None:
        _smoke.not_tested(
            "Woo SKU probe unavailable (no WOO_CONSUMER_KEY/ docker/wp-cli); "
            "Woo reachability is covered by test_woo_front_reachable"
        )

    for sku in _smoke.CANONICAL_SKUS:
        assert sku in present, "service: Woo SKU %s missing (present=%r)" % (sku, sorted(present))
