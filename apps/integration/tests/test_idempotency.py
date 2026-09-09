"""验证幂等语义：同一键 + 同一负载只执行一次；同一键 + 不同负载拒绝（409）。"""

from __future__ import annotations

import pytest

from shopstore_integration.adapters import MockAdapter
from shopstore_integration.commands import publish_product_command
from shopstore_integration.errors import (
    IdempotencyConflictError,
    UpstreamTimeoutError,
)
from shopstore_integration.idempotency import (
    IdempotencyKey,
    InMemoryIdempotencyStore,
)
from shopstore_integration.tasks import TaskStatus
from shopstore_integration.tasks.publish_product import PublishProductTask


def _make_task(woo: MockAdapter, odoo: MockAdapter) -> PublishProductTask:
    return PublishProductTask(
        woo=woo,
        odoo=odoo,
        idempotency_store=InMemoryIdempotencyStore(),
    )


def test_same_key_same_payload_executes_once() -> None:
    woo = MockAdapter(name="woo")
    odoo = MockAdapter(name="odoo")
    task = _make_task(woo, odoo)

    command = publish_product_command(
        sku="DEMO-SKU-001", name="Demo", amount_minor=100, currency="USD"
    )

    first = task.execute(command)
    second = task.execute(command)

    assert first.status == TaskStatus.SUCCESS
    assert second.status == TaskStatus.SKIPPED
    assert first.external_ids == second.external_ids

    # Adapter 只被真正调用一次。
    assert len([c for c in woo.calls if c[0] == "upsert_product"]) == 1
    assert len([c for c in odoo.calls if c[0] == "upsert_product"]) == 1


def test_same_key_different_payload_conflicts() -> None:
    woo = MockAdapter(name="woo")
    odoo = MockAdapter(name="odoo")
    task = _make_task(woo, odoo)

    first = publish_product_command(
        sku="DEMO-SKU-001", name="Demo", amount_minor=100, currency="USD"
    )
    second = publish_product_command(
        sku="DEMO-SKU-001", name="Demo", amount_minor=200, currency="USD"
    )

    assert task.execute(first).status == TaskStatus.SUCCESS
    with pytest.raises(IdempotencyConflictError):
        task.execute(second)


def test_failed_task_can_retry_with_same_key() -> None:
    woo = MockAdapter(
        name="woo",
        fail_with=UpstreamTimeoutError("woo timed out"),
        fail_count=1,
    )
    odoo = MockAdapter(name="odoo")
    task = _make_task(woo, odoo)

    command = publish_product_command(
        sku="DEMO-SKU-001", name="Demo", amount_minor=100, currency="USD"
    )

    failed = task.execute(command)
    assert failed.status == TaskStatus.FAILED

    retried = task.execute(command)
    assert retried.status == TaskStatus.SUCCESS


def test_idempotency_key_roundtrip_and_validation() -> None:
    key = IdempotencyKey("core", "order", "export", "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d")
    assert str(key) == "core.order.export.1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d"
    assert IdempotencyKey.parse(str(key)) == key

    with pytest.raises(ValueError):
        IdempotencyKey("nope", "order", "export", "1")

    with pytest.raises(ValueError):
        IdempotencyKey("core", "Order", "export", "1")
