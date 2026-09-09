"""WooCommerce accessibility smoke check (profile R, read-only)."""

from __future__ import annotations

import pytest

import _smoke


@pytest.mark.r
def test_woo_front_reachable():
    """WooCommerce storefront must answer on ``GET /`` and serve a WordPress site.

    Two layers guard against a false PASS: a bare 302 from ``/`` to the WordPress
    install screen (``/wp-admin/install.php``) also looks "reachable" yet the store
    is not installed. We therefore additionally require ``GET /wp-json/`` to return
    200 with a JSON body, which only a fully-installed WordPress/WooCommerce site
    serves.

    This is the must-succeed positive control for the Woo group: the Woo SKU probe
    (test_sku.py) reports NOT_TESTED rather than FAIL when its own mechanism is
    unavailable, and it is THIS check that turns a down/not-installed Woo into a
    real FAIL.
    """
    status, _body, error = _smoke.http_get(_smoke.WOO_BASE_URL + "/")
    if status is None:
        pytest.fail("service: WooCommerce front unreachable at %s/ (%s)" % (_smoke.WOO_BASE_URL, error))
    assert 200 <= status < 400, (
        "service: WooCommerce front returned HTTP %s at %s/" % (status, _smoke.WOO_BASE_URL)
    )

    status, body, error = _smoke.http_json(_smoke.WOO_BASE_URL + "/wp-json/")
    if status is None:
        pytest.fail("service: WooCommerce REST index unreachable at %s/wp-json/ (%s)" % (_smoke.WOO_BASE_URL, error))
    assert status == 200, (
        "service: WooCommerce not installed (GET /wp-json/ returned HTTP %s; store may be "
        "stuck at the WordPress install screen)" % status
    )
    assert isinstance(body, dict), (
        "service: WooCommerce /wp-json/ did not return a JSON object (site not installed?)"
    )
