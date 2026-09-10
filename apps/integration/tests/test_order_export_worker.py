"""订单导出 Worker 测试：Core 事件 → Odoo 销售单 → 写回 → ack，幂等与失败留待重试。"""

from __future__ import annotations

from shopstore_integration.adapters import MockAdapter
from shopstore_integration.errors import UpstreamTimeoutError
from shopstore_integration.worker import OrderExportWorker


class FakeCore:
    """CoreClient 的进程内替身（不发起真实 HTTP）。"""

    def __init__(self) -> None:
        self.orders: dict[str, dict] = {}
        self.retailers: dict[str, dict] = {}
        self.pending: list[dict] = []
        self.acked: list[str] = []
        self.writebacks: list[tuple[str, int]] = []
        self.fail_writeback = False

    def list_pending_events(self, *, event_type, limit, request_id):
        return [e for e in self.pending if e["event_id"] not in self.acked][:limit]

    def get_order(self, order_id, *, request_id):
        order = self.orders.get(order_id, {"external_ids": {}})
        return {"marketplace_order_id": order_id, "external_ids": order.get("external_ids", {})}

    def get_retailer(self, retailer_id, *, request_id):
        return self.retailers[retailer_id]

    def record_odoo_sale_order(self, order_id, odoo_sale_order_id, *, request_id):
        if self.fail_writeback:
            raise RuntimeError("writeback failed")
        self.orders[order_id] = {"external_ids": {"odoo_sale_order_id": odoo_sale_order_id}}
        self.writebacks.append((order_id, odoo_sale_order_id))
        return {"marketplace_order_id": order_id}

    def ack_event(self, event_id, *, request_id):
        self.acked.append(event_id)


def _event(event_id: str, order_id: str, retailer_id: str) -> dict:
    return {
        "event_id": event_id,
        "event_type": "commerce.order.created",
        "trace_id": f"trace-{event_id}",
        "request_id": None,
        "data": {
            "marketplace_order_id": order_id,
            "retailer_id": retailer_id,
            "status": "submitted",
            "lines": [
                {"sku": "DEMO-SKU-001", "quantity": 3, "unit_price": {"amount_minor": 129900, "currency": "USD"}},
            ],
            "total": {"amount_minor": 389700, "currency": "USD"},
            "external_ids": {},
        },
    }


def _make_worker(sync_jobs_store):
    core = FakeCore()
    core.retailers["RTL-1"] = {"company_name": "Acme", "email": "buyer@example.test"}
    odoo = MockAdapter(name="odoo")
    worker = OrderExportWorker(core=core, odoo=odoo, idempotency_store=sync_jobs_store)
    return worker, core, odoo


def _create_sale_order_calls(odoo: MockAdapter) -> int:
    return len([c for c in odoo.calls if c[0] == "create_sale_order"])


def test_worker_exports_order_and_writes_back(sync_jobs_store) -> None:
    worker, core, odoo = _make_worker(sync_jobs_store)
    core.pending.append(_event("ev-1", "ORDER-1", "RTL-1"))

    count = worker.run_once()

    assert count == 1
    assert _create_sale_order_calls(odoo) == 1
    assert ("ORDER-1", 1) in core.writebacks
    assert core.acked == ["ev-1"]
    assert core.orders["ORDER-1"]["external_ids"]["odoo_sale_order_id"] == 1


def test_worker_skips_already_mapped_order(sync_jobs_store) -> None:
    worker, core, odoo = _make_worker(sync_jobs_store)
    core.pending.append(_event("ev-1", "ORDER-1", "RTL-1"))
    core.pending.append(_event("ev-2", "ORDER-1", "RTL-1"))

    # 第二次轮询前，ORDER-1 已被写回（模拟上一轮已成功）。
    core.orders["ORDER-1"] = {"external_ids": {"odoo_sale_order_id": 1}}
    worker.run_once()

    assert _create_sale_order_calls(odoo) == 0
    assert core.acked == ["ev-1", "ev-2"]


def test_worker_retries_writeback_without_recreating(sync_jobs_store) -> None:
    worker, core, odoo = _make_worker(sync_jobs_store)
    core.pending.append(_event("ev-1", "ORDER-1", "RTL-1"))
    core.fail_writeback = True
    worker.run_once()

    # Odoo 已创建销售单（幂等键已提交），但写回失败、事件未 ack。
    assert _create_sale_order_calls(odoo) == 1
    assert core.acked == []
    assert core.orders.get("ORDER-1") is None

    # 下一轮：写回恢复，事件仍待消费 → 命中幂等键，不重建销售单，只补写回 + ack。
    core.fail_writeback = False
    worker.run_once()

    assert _create_sale_order_calls(odoo) == 1
    assert ("ORDER-1", 1) in core.writebacks
    assert core.acked == ["ev-1"]


def test_worker_leaves_event_pending_on_odoo_failure(sync_jobs_store) -> None:
    core = FakeCore()
    core.retailers["RTL-1"] = {"company_name": "Acme", "email": "buyer@example.test"}
    core.pending.append(_event("ev-1", "ORDER-1", "RTL-1"))
    odoo = MockAdapter(name="odoo", fail_with=UpstreamTimeoutError("odoo timeout"), fail_count=1)
    worker = OrderExportWorker(core=core, odoo=odoo, idempotency_store=sync_jobs_store)

    worker.run_once()

    assert core.acked == []
    assert core.writebacks == []

    # 重试成功后正常写回 + ack。
    worker.run_once()
    assert ("ORDER-1", 1) in core.writebacks
    assert core.acked == ["ev-1"]
