"""验证 Mock 链路：Core Command -> Integration Task -> Adapter -> Mock Result。"""

from __future__ import annotations

from shopstore_integration.adapters import MockAdapter
from shopstore_integration.commands import (
    export_order_command,
    publish_product_command,
)
from shopstore_integration.idempotency import InMemoryIdempotencyStore
from shopstore_integration.tasks import TaskStatus
from shopstore_integration.tasks.dispatch import TaskDispatcher
from shopstore_integration.tasks.export_order import ExportOrderTask
from shopstore_integration.tasks.publish_product import PublishProductTask


def test_publish_product_chain_runs_end_to_end() -> None:
    woo = MockAdapter(name="woo")
    odoo = MockAdapter(name="odoo")
    task = PublishProductTask(
        woo=woo,
        odoo=odoo,
        idempotency_store=InMemoryIdempotencyStore(),
    )
    dispatcher = TaskDispatcher()
    dispatcher.register(task)

    command = publish_product_command(
        sku="DEMO-SKU-001",
        name="Demo Product",
        amount_minor=129900,
        currency="USD",
    )
    result = dispatcher.dispatch(command)

    assert result.status == TaskStatus.SUCCESS
    assert result.command_type == "catalog.product.publish"
    assert result.external_ids["sku"] == "DEMO-SKU-001"
    assert result.external_ids["woo_product_id"] > 0
    assert result.external_ids["odoo_product_id"] > 0

    assert any(call[0] == "upsert_product" for call in woo.calls)
    assert any(call[0] == "upsert_product" for call in odoo.calls)


def test_export_order_chain_runs_end_to_end() -> None:
    odoo = MockAdapter(name="odoo")
    task = ExportOrderTask(
        odoo=odoo,
        idempotency_store=InMemoryIdempotencyStore(),
    )
    dispatcher = TaskDispatcher()
    dispatcher.register(task)

    command = export_order_command(
        marketplace_order_id="1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
        lines=[],
    )
    result = dispatcher.dispatch(command)

    assert result.status == TaskStatus.SUCCESS
    assert result.external_ids["odoo_sale_order_id"] > 0
    assert any(call[0] == "create_sale_order" for call in odoo.calls)


def test_unknown_command_type_raises() -> None:
    from shopstore_integration.commands import Command
    from shopstore_integration.errors import IntegrationError
    from shopstore_integration.idempotency import IdempotencyKey

    import pytest

    dispatcher = TaskDispatcher()
    command = Command(
        command_type="unknown.thing.action",
        idempotency_key=IdempotencyKey("core", "thing", "action", "1"),
        payload={},
        trace_id="trace",
    )
    with pytest.raises(IntegrationError):
        dispatcher.dispatch(command)
