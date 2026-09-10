"""履约状态回传长驻轮询 worker（ISSUE-0115）测试。

覆盖：读取 Odoo 交货单状态 → 按状态机阶梯逐状态回传 → Core 推进到 shipped；
重复轮询幂等、乱序不倒退、Odoo 读取失败不阻断、状态 / 外部 ID 过滤。
"""

from __future__ import annotations

from shopstore_integration.errors import IdempotencyConflictError
from shopstore_integration.fulfillment_worker import (
    FULFILLMENT_STATUS_LADDER,
    POLLABLE_STATUSES,
    FulfillmentSyncWorker,
    fulfillment_status_path,
)
from shopstore_integration.tasks.dispatch import TaskDispatcher
from shopstore_integration.tasks.report_fulfillment import ReportFulfillmentTask

_LADDER = ["odoo_confirmed", "inventory_reserved", "picking_ready", "shipped"]

_TRANSITIONS = {
    "sent_to_odoo": {"odoo_confirmed", "cancelled"},
    "odoo_confirmed": {"inventory_reserved", "cancelled"},
    "inventory_reserved": {"picking_ready", "cancelled"},
    "picking_ready": {"shipped", "cancelled"},
    "shipped": {"completed"},
    "completed": set(),
    "cancelled": set(),
}


class FakeCoreState:
    """Core 订单状态机替身：仅允许单向推进，非法迁移抛冲突（模拟 409）。"""

    def __init__(self) -> None:
        self.orders: dict[str, dict] = {}
        self.reports: list[tuple[str, str, object, object]] = []

    def seed(self, order_id: str, status: str, odoo_sale_order_id=None) -> None:
        external = {}
        if odoo_sale_order_id is not None:
            external["odoo_sale_order_id"] = odoo_sale_order_id
        self.orders[order_id] = {"status": status, "external_ids": external}

    def report_fulfillment(
        self,
        marketplace_order_id: str,
        *,
        status: str,
        odoo_delivery_id=None,
        odoo_sale_order_id=None,
        request_id: str,
        trace_id=None,
    ) -> dict:
        order = self.orders[marketplace_order_id]
        current = order["status"]
        if status == current:
            return {"marketplace_order_id": marketplace_order_id, "status": status}
        allowed = _TRANSITIONS.get(current, set())
        if status not in allowed:
            raise IdempotencyConflictError(
                f"invalid transition {current} -> {status}", request_id=request_id
            )
        order["status"] = status
        if odoo_delivery_id is not None:
            order["external_ids"]["odoo_delivery_id"] = odoo_delivery_id
        if odoo_sale_order_id is not None:
            order["external_ids"]["odoo_sale_order_id"] = odoo_sale_order_id
        self.reports.append(
            (marketplace_order_id, status, odoo_delivery_id, odoo_sale_order_id)
        )
        return {"marketplace_order_id": marketplace_order_id, "status": status}


class FakeCoreClient:
    """CoreClient 替身：list_orders 返回给定订单视图。"""

    def __init__(self, orders: list[dict]) -> None:
        self.orders = orders

    def list_orders(self, *, limit, offset, request_id):
        return self.orders[offset : offset + limit]


class FakeOdoo:
    """OdooAdapter 替身：按 order 返回可控交货单状态。"""

    def __init__(self, deliveries: dict[int, dict] | None = None) -> None:
        self.deliveries = deliveries or {}
        self.fail = None

    def get_delivery_for_sale_order(self, odoo_sale_order_id, *, request_id):
        if self.fail is not None:
            raise self.fail
        return self.deliveries.get(odoo_sale_order_id)


def _order(order_id: str, status: str, odoo_sale_order_id: int) -> dict:
    return {
        "marketplace_order_id": order_id,
        "status": status,
        "external_ids": {"odoo_sale_order_id": odoo_sale_order_id},
    }


def _make_worker(core_client, odoo, core_state, sync_jobs_store):
    dispatcher = TaskDispatcher()
    dispatcher.register(
        ReportFulfillmentTask(core=core_state, idempotency_store=sync_jobs_store)
    )
    worker = FulfillmentSyncWorker(core=core_client, odoo=odoo, dispatcher=dispatcher)
    return worker


def test_fulfillment_status_path() -> None:
    assert fulfillment_status_path("sent_to_odoo", "shipped") == _LADDER
    assert fulfillment_status_path("sent_to_odoo", "picking_ready") == [
        "odoo_confirmed",
        "inventory_reserved",
        "picking_ready",
    ]
    assert fulfillment_status_path("inventory_reserved", "shipped") == [
        "picking_ready",
        "shipped",
    ]
    assert fulfillment_status_path("shipped", "shipped") == []
    assert fulfillment_status_path("picking_ready", "inventory_reserved") == []
    assert fulfillment_status_path("sent_to_odoo", None) == []
    assert fulfillment_status_path("sent_to_odoo", "cancelled") == ["cancelled"]
    assert fulfillment_status_path("cancelled", "cancelled") == []
    assert fulfillment_status_path("sent_to_odoo", "mystery") == []


def test_ladder_is_unidirectional(sync_jobs_store) -> None:
    # 阶梯必须与 Core 状态机主线顺序一致（odoo_confirmed -> ... -> shipped）。
    assert FULFILLMENT_STATUS_LADDER == _LADDER
    assert POLLABLE_STATUSES == {
        "sent_to_odoo",
        "odoo_confirmed",
        "inventory_reserved",
        "picking_ready",
    }


def test_worker_advances_order_to_shipped(sync_jobs_store) -> None:
    core_state = FakeCoreState()
    core_state.seed("ORDER-1", "sent_to_odoo", odoo_sale_order_id=2002)
    core_client = FakeCoreClient([_order("ORDER-1", "sent_to_odoo", 2002)])
    odoo = FakeOdoo({2002: {"odoo_delivery_id": 1001, "status": "done"}})

    worker = _make_worker(core_client, odoo, core_state, sync_jobs_store)
    count = worker.run_once()

    assert count == 1
    assert core_state.orders["ORDER-1"]["status"] == "shipped"
    # 按状态机单向推进，逐状态回传，未倒退。
    assert [r[1] for r in core_state.reports] == _LADDER
    assert core_state.orders["ORDER-1"]["external_ids"]["odoo_delivery_id"] == 1001


def test_worker_duplicate_poll_is_idempotent(sync_jobs_store) -> None:
    core_state = FakeCoreState()
    core_state.seed("ORDER-1", "sent_to_odoo", odoo_sale_order_id=2002)
    core_client = FakeCoreClient([_order("ORDER-1", "sent_to_odoo", 2002)])
    odoo = FakeOdoo({2002: {"odoo_delivery_id": 1001, "status": "done"}})

    worker = _make_worker(core_client, odoo, core_state, sync_jobs_store)
    worker.run_once()
    assert core_state.orders["ORDER-1"]["status"] == "shipped"
    reports_after_first = len(core_state.reports)

    # 第二轮：订单已到 shipped，不再是可轮询状态，不再回传、不倒退。
    core_client.orders = [_order("ORDER-1", "shipped", 2002)]
    worker.run_once()
    assert len(core_state.reports) == reports_after_first
    assert core_state.orders["ORDER-1"]["status"] == "shipped"


def test_worker_skips_orders_without_sale_order_or_terminal(sync_jobs_store) -> None:
    core_state = FakeCoreState()
    core_client = FakeCoreClient(
        [
            {
                "marketplace_order_id": "ORDER-NO-ODOO",
                "status": "sent_to_odoo",
                "external_ids": {},
            },
            {
                "marketplace_order_id": "ORDER-DONE",
                "status": "completed",
                "external_ids": {"odoo_sale_order_id": 3003},
            },
        ]
    )
    odoo = FakeOdoo({3003: {"odoo_delivery_id": 1003, "status": "done"}})

    worker = _make_worker(core_client, odoo, core_state, sync_jobs_store)
    count = worker.run_once()

    assert count == 0
    assert core_state.reports == []


def test_worker_no_delivery_yet_skips(sync_jobs_store) -> None:
    core_state = FakeCoreState()
    core_state.seed("ORDER-1", "sent_to_odoo", odoo_sale_order_id=2002)
    core_client = FakeCoreClient([_order("ORDER-1", "sent_to_odoo", 2002)])
    odoo = FakeOdoo({})  # 销售单尚未确认，无交货单

    worker = _make_worker(core_client, odoo, core_state, sync_jobs_store)
    count = worker.run_once()

    assert count == 1
    assert core_state.reports == []
    assert core_state.orders["ORDER-1"]["status"] == "sent_to_odoo"


def test_worker_odoo_read_failure_does_not_block(sync_jobs_store) -> None:
    from shopstore_integration.errors import UpstreamTimeoutError

    core_state = FakeCoreState()
    core_state.seed("ORDER-1", "sent_to_odoo", odoo_sale_order_id=2002)
    core_client = FakeCoreClient([_order("ORDER-1", "sent_to_odoo", 2002)])
    odoo = FakeOdoo({2002: {"odoo_delivery_id": 1001, "status": "done"}})
    odoo.fail = UpstreamTimeoutError("odoo timeout")

    worker = _make_worker(core_client, odoo, core_state, sync_jobs_store)
    count = worker.run_once()

    assert count == 1
    assert core_state.reports == []
    assert core_state.orders["ORDER-1"]["status"] == "sent_to_odoo"


def test_worker_reports_cancelled(sync_jobs_store) -> None:
    core_state = FakeCoreState()
    core_state.seed("ORDER-1", "sent_to_odoo", odoo_sale_order_id=2002)
    core_client = FakeCoreClient([_order("ORDER-1", "sent_to_odoo", 2002)])
    odoo = FakeOdoo({2002: {"odoo_delivery_id": 1001, "status": "cancel"}})

    worker = _make_worker(core_client, odoo, core_state, sync_jobs_store)
    worker.run_once()

    assert core_state.orders["ORDER-1"]["status"] == "cancelled"
    assert [r[1] for r in core_state.reports] == ["cancelled"]
