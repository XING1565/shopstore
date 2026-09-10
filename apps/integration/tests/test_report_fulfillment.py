"""验证履约状态回传任务：Odoo 状态映射 + 回传 Core + 幂等跳过。"""

from __future__ import annotations

import pytest

from shopstore_integration.adapters import MockCoreAdapter
from shopstore_integration.commands import report_fulfillment_command
from shopstore_integration.errors import UpstreamError
from shopstore_integration.idempotency import InMemoryIdempotencyStore
from shopstore_integration.tasks import TaskStatus
from shopstore_integration.tasks.report_fulfillment import (
    ODOO_STATE_TO_ORDER_STATUS,
    ReportFulfillmentTask,
    map_delivery_status_to_order_status,
)


def test_delivery_status_mapping() -> None:
    assert map_delivery_status_to_order_status("done") == "shipped"
    assert map_delivery_status_to_order_status("assigned") == "picking_ready"
    assert map_delivery_status_to_order_status("confirmed") == "inventory_reserved"
    assert map_delivery_status_to_order_status("cancel") == "cancelled"
    assert map_delivery_status_to_order_status("draft") is None
    assert map_delivery_status_to_order_status("waiting") is None
    # 归一化状态透传
    assert map_delivery_status_to_order_status("picking_ready") == "picking_ready"
    assert map_delivery_status_to_order_status("shipped") == "shipped"
    # 未知状态不映射
    assert map_delivery_status_to_order_status("mystery") is None


def test_mapping_covers_expected_odoo_states() -> None:
    assert set(ODOO_STATE_TO_ORDER_STATUS) == {
        "draft",
        "waiting",
        "confirmed",
        "assigned",
        "done",
        "cancel",
    }


def _make_task(core: MockCoreAdapter) -> ReportFulfillmentTask:
    return ReportFulfillmentTask(
        core=core,
        idempotency_store=InMemoryIdempotencyStore(),
    )


def test_report_shipped_calls_core_with_mapped_status() -> None:
    core = MockCoreAdapter()
    task = _make_task(core)

    command = report_fulfillment_command(
        marketplace_order_id="1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
        odoo_delivery_id=1001,
        odoo_status="done",
        odoo_sale_order_id=2002,
    )
    result = task.execute(command)

    assert result.status == TaskStatus.SUCCESS
    assert result.external_ids["status"] == "shipped"
    assert result.external_ids["odoo_delivery_id"] == 1001
    assert result.external_ids["odoo_sale_order_id"] == 2002

    call = core.calls[0]
    assert call[0] == "report_fulfillment"
    assert call[1] == "1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d"
    assert call[2] == "shipped"
    assert call[3] == 1001
    assert call[4] == 2002


def test_no_progress_state_is_skipped_without_core_call() -> None:
    core = MockCoreAdapter()
    task = _make_task(core)

    command = report_fulfillment_command(
        marketplace_order_id="1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
        odoo_delivery_id=1001,
        odoo_status="draft",
    )
    result = task.execute(command)

    assert result.status == TaskStatus.SUCCESS
    assert result.external_ids["skipped"] is True
    assert result.external_ids["status"] is None
    assert core.calls == []


def test_same_key_same_status_executes_once() -> None:
    core = MockCoreAdapter()
    task = _make_task(core)

    command = report_fulfillment_command(
        marketplace_order_id="1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
        odoo_delivery_id=1001,
        odoo_status="done",
    )
    first = task.execute(command)
    second = task.execute(command)

    assert first.status == TaskStatus.SUCCESS
    assert second.status == TaskStatus.SKIPPED
    assert len(core.calls) == 1


def test_different_status_same_delivery_uses_distinct_key() -> None:
    core = MockCoreAdapter()
    task = _make_task(core)

    picking = report_fulfillment_command(
        marketplace_order_id="1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
        odoo_delivery_id=1001,
        odoo_status="assigned",
    )
    shipped = report_fulfillment_command(
        marketplace_order_id="1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
        odoo_delivery_id=1001,
        odoo_status="done",
    )

    assert task.execute(picking).status == TaskStatus.SUCCESS
    assert task.execute(shipped).status == TaskStatus.SUCCESS
    # 两个不同状态各回传一次，不被幂等跳过。
    assert len(core.calls) == 2


def test_core_rejection_surfaces_as_failure() -> None:
    core = MockCoreAdapter()
    core._reject_with = UpstreamError("core rejected state transition")
    task = _make_task(core)

    command = report_fulfillment_command(
        marketplace_order_id="1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
        odoo_delivery_id=1001,
        odoo_status="done",
    )
    result = task.execute(command)

    assert result.status == TaskStatus.FAILED
    assert result.error is not None
    assert result.error.code == "upstream_error"


def test_command_type_matches_dispatcher_contract() -> None:
    assert ReportFulfillmentTask.command_type == "commerce.order.fulfillment"
