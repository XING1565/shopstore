"""验证 RetryWorker：退避重试、死信与人工重试，且重试不重复创建 Odoo 销售单。"""

from __future__ import annotations

from shopstore_integration.adapters import MockAdapter
from shopstore_integration.commands import export_order_command
from shopstore_integration.errors import UpstreamTimeoutError
from shopstore_integration.retry import RetryWorker, command_from_job
from shopstore_integration.sync_jobs import STATUS_COMPLETED, STATUS_DEAD
from shopstore_integration.tasks import TaskStatus
from shopstore_integration.tasks.dispatch import TaskDispatcher
from shopstore_integration.tasks.export_order import ExportOrderTask


class CountingOdoo(MockAdapter):
    """记录成功创建销售单次数的替身（失败调用不计入）。"""

    def __init__(self, *, fail_with, fail_count):
        super().__init__(name="odoo", fail_with=fail_with, fail_count=fail_count)
        self.successful_creates = 0

    def create_sale_order(self, order, *, request_id):
        result = super().create_sale_order(order, request_id=request_id)
        self.successful_creates += 1
        return result


def _make_retry(clock_store, odoo):
    task = ExportOrderTask(odoo=odoo, idempotency_store=clock_store)
    dispatcher = TaskDispatcher()
    dispatcher.register(task)
    retry = RetryWorker(store=clock_store, dispatcher=dispatcher)
    return retry, dispatcher


def test_retries_recover_without_duplicate_sale_order(clock, clock_store) -> None:
    odoo = MockAdapter(name="odoo", fail_with=UpstreamTimeoutError("odoo timeout"), fail_count=2)
    retry, dispatcher = _make_retry(clock_store, odoo)

    command = export_order_command(marketplace_order_id="ORDER-1", lines=[])
    first = dispatcher.dispatch(command)
    assert first.status == TaskStatus.FAILED

    # 退避未到期：不重试。
    summary = retry.run_retries()
    assert summary["total"] == 0

    # 到期后重试（第一次仍失败，第二次成功），不重复创建销售单。
    clock.advance(2.0)
    summary = retry.run_retries()
    assert summary["failed"] == 1

    clock.advance(2.0)
    summary = retry.run_retries()
    assert summary["success"] == 1

    job = clock_store.get("core.order.export.ORDER-1")
    assert job.status == STATUS_COMPLETED
    assert job.result["odoo_sale_order_id"] is not None
    assert len([c for c in odoo.calls if c[0] == "create_sale_order"]) == 3  # 2 fail + 1 success

    # 幂等：再次触发返回既有结果，不再创建销售单。
    again = dispatcher.dispatch(command)
    assert again.status == TaskStatus.SKIPPED
    assert again.external_ids["odoo_sale_order_id"] == job.result["odoo_sale_order_id"]


def test_dead_letter_then_manual_retry_no_duplicate(clock, clock_store) -> None:
    odoo = CountingOdoo(fail_with=UpstreamTimeoutError("odoo down"), fail_count=3)
    retry, dispatcher = _make_retry(clock_store, odoo)

    command = export_order_command(marketplace_order_id="ORDER-1", lines=[])
    assert dispatcher.dispatch(command).status == TaskStatus.FAILED  # attempt 1

    for _ in range(2):  # attempts 2, 3 -> 耗尽重试，进入死信
        clock.advance(2.0)
        retry.run_retries()

    assert len(retry.list_dead()) == 1
    assert odoo.successful_creates == 0  # 失败期间从未真正创建销售单

    # 人工重试：odoo 已恢复，成功完成且只创建一次销售单。
    result = retry.retry_job("core.order.export.ORDER-1")
    assert result.status == TaskStatus.SUCCESS
    assert clock_store.get("core.order.export.ORDER-1").status == STATUS_COMPLETED
    assert odoo.successful_creates == 1


def test_manual_retry_of_dead_job_returns_none_for_unknown(clock_store) -> None:
    odoo = MockAdapter(name="odoo")
    retry, _ = _make_retry(clock_store, odoo)
    assert retry.retry_job("core.order.export.UNKNOWN") is None


def test_command_from_job_requires_command_type(clock_store) -> None:
    from shopstore_integration.idempotency import hash_payload

    clock_store.begin(
        "core.order.export.ORDER-1",
        hash_payload({"marketplace_order_id": "ORDER-1"}),
    )
    job = clock_store.get("core.order.export.ORDER-1")

    import pytest

    with pytest.raises(ValueError):
        command_from_job(job)
