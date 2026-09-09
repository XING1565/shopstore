"""Core -> Integration -> Mock chain smoke check (profile R, no external I/O).

The Integration Layer is a library in stage 0 (no long-running service). This
check exercises the in-process chain ``Core Command -> Integration Task ->
Adapter -> Mock Result`` using the real dispatcher and the Mock adapter, and
verifies that an unknown command type is rejected (idempotent dispatch guard).

This is pure Python and has no dependency on the running Docker stacks, so it
always produces a definitive PASS/FAIL (never NOT_TESTED).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import _smoke

_INTEGRATION_APP = _smoke.REPO_ROOT / "apps" / "integration" / "app"
if str(_INTEGRATION_APP) not in sys.path:
    sys.path.insert(0, str(_INTEGRATION_APP))

from shopstore_integration.adapters import MockAdapter  # noqa: E402
from shopstore_integration.commands import (  # noqa: E402
    Command,
    export_order_command,
    publish_product_command,
)
from shopstore_integration.errors import IntegrationError  # noqa: E402
from shopstore_integration.idempotency import (  # noqa: E402
    IdempotencyKey,
    InMemoryIdempotencyStore,
)
from shopstore_integration.tasks import TaskStatus  # noqa: E402
from shopstore_integration.tasks.dispatch import TaskDispatcher  # noqa: E402
from shopstore_integration.tasks.export_order import ExportOrderTask  # noqa: E402
from shopstore_integration.tasks.publish_product import PublishProductTask  # noqa: E402


@pytest.mark.r
def test_publish_product_mock_chain():
    """Publish-product command flows through dispatcher to a Mock result."""
    woo = MockAdapter(name="woo")
    odoo = MockAdapter(name="odoo")
    dispatcher = TaskDispatcher()
    dispatcher.register(
        PublishProductTask(woo=woo, odoo=odoo, idempotency_store=InMemoryIdempotencyStore())
    )

    result = dispatcher.dispatch(
        publish_product_command(
            sku="DEMO-SKU-001",
            name="Demo Product",
            amount_minor=129900,
            currency="USD",
        )
    )

    assert result.status == TaskStatus.SUCCESS, "integration: publish chain status=%r" % result.status
    assert result.external_ids["sku"] == "DEMO-SKU-001"
    assert result.external_ids["woo_product_id"] > 0
    assert result.external_ids["odoo_product_id"] > 0
    assert any(call[0] == "upsert_product" for call in woo.calls)
    assert any(call[0] == "upsert_product" for call in odoo.calls)


@pytest.mark.r
def test_export_order_mock_chain():
    """Export-order command flows through dispatcher to a Mock sale-order result."""
    odoo = MockAdapter(name="odoo")
    dispatcher = TaskDispatcher()
    dispatcher.register(
        ExportOrderTask(odoo=odoo, idempotency_store=InMemoryIdempotencyStore())
    )

    result = dispatcher.dispatch(
        export_order_command(
            marketplace_order_id="1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
            lines=[],
        )
    )

    assert result.status == TaskStatus.SUCCESS, "integration: export chain status=%r" % result.status
    assert result.external_ids["odoo_sale_order_id"] > 0
    assert any(call[0] == "create_sale_order" for call in odoo.calls)


@pytest.mark.r
def test_unknown_command_rejected():
    """Deny-probe: an unknown command type is rejected.

    Paired with the two must-succeed chain tests above so that a rejection is
    attributable to the command type, not to a broken dispatcher.
    """
    dispatcher = TaskDispatcher()
    command = Command(
        command_type="unknown.thing.action",
        idempotency_key=IdempotencyKey("core", "thing", "action", "1"),
        payload={},
        trace_id="trace",
    )
    with pytest.raises(IntegrationError):
        dispatcher.dispatch(command)
