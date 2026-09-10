"""验证数据库幂等存储 SyncJobsStore：begin/commit/abort、幂等、冲突与重试/退避/死信。"""

from __future__ import annotations

import pytest

from shopstore_integration.errors import (
    IdempotencyConflictError,
    PayloadValidationError,
    UpstreamTimeoutError,
)
from shopstore_integration.idempotency import hash_payload
from shopstore_integration.sync_jobs import (
    STATUS_COMPLETED,
    STATUS_DEAD,
    STATUS_FAILED,
    STATUS_RUNNING,
    compute_backoff_delay,
)


def _begin_job(store, key, payload, *, command_type="commerce.order.export"):
    return store.begin(
        key,
        hash_payload(payload),
        command_type=command_type,
        payload=payload,
        trace_id="trace-1",
    )


def test_begin_returns_new_then_running(sync_jobs_store) -> None:
    key = "core.order.export.ORDER-1"
    payload = {"marketplace_order_id": "ORDER-1"}

    first = sync_jobs_store.begin(key, hash_payload(payload))
    assert first.status == "new"

    second = sync_jobs_store.begin(key, hash_payload(payload))
    assert second.status == "running"


def test_commit_then_begin_returns_completed_with_result(sync_jobs_store) -> None:
    key = "core.order.export.ORDER-1"
    payload = {"marketplace_order_id": "ORDER-1"}
    result = {"odoo_sale_order_id": 1011, "marketplace_order_id": "ORDER-1"}

    sync_jobs_store.begin(key, hash_payload(payload))
    sync_jobs_store.commit(key, result)

    record = sync_jobs_store.begin(key, hash_payload(payload))
    assert record.status == "completed"
    assert record.result == result


def test_same_key_different_payload_conflicts(sync_jobs_store) -> None:
    key = "core.order.export.ORDER-1"
    sync_jobs_store.begin(key, hash_payload({"marketplace_order_id": "ORDER-1"}))

    with pytest.raises(IdempotencyConflictError):
        sync_jobs_store.begin(key, hash_payload({"marketplace_order_id": "ORDER-1", "x": 1}))


def test_abort_allows_retry(sync_jobs_store) -> None:
    key = "core.order.export.ORDER-1"
    payload = {"marketplace_order_id": "ORDER-1"}

    sync_jobs_store.begin(key, hash_payload(payload))
    sync_jobs_store.abort(key)

    retried = sync_jobs_store.begin(key, hash_payload(payload))
    assert retried.status == "new"


def test_commit_unknown_key_raises(sync_jobs_store) -> None:
    with pytest.raises(KeyError):
        sync_jobs_store.commit("core.order.export.UNKNOWN", {"odoo_sale_order_id": 1})


def test_compute_backoff_delay_is_exponential() -> None:
    from shopstore_integration.config import RetryConfig

    retry = RetryConfig(max_attempts=5, backoff_seconds=0.5, backoff_factor=2.0)
    assert compute_backoff_delay(1, retry) == 0.5
    assert compute_backoff_delay(2, retry) == 1.0
    assert compute_backoff_delay(3, retry) == 2.0
    assert compute_backoff_delay(4, retry) == 4.0


def test_mark_failed_records_failure_and_schedules_retry(clock, clock_store) -> None:
    key = "core.order.export.ORDER-1"
    payload = {"marketplace_order_id": "ORDER-1"}
    _begin_job(clock_store, key, payload)

    status = clock_store.mark_failed(key, UpstreamTimeoutError("odoo timeout"))

    assert status == STATUS_FAILED
    job = clock_store.get(key)
    assert job.status == STATUS_FAILED
    assert job.attempts == 1
    assert job.last_error == {"code": "upstream_timeout", "message": "odoo timeout"}
    assert job.next_retry_at is not None
    # 退避未到期时不可重试；到期后可重试。
    assert clock_store.list_jobs(due_only=True) == []
    clock.advance(2.0)
    due = clock_store.list_jobs(due_only=True)
    assert [j.idempotency_key for j in due] == [key]


def test_non_retryable_error_dead_letters_immediately(clock_store) -> None:
    key = "core.order.export.ORDER-1"
    payload = {"marketplace_order_id": "ORDER-1"}
    _begin_job(clock_store, key, payload)

    status = clock_store.mark_failed(key, PayloadValidationError("below MOQ"))

    assert status == STATUS_DEAD
    job = clock_store.get(key)
    assert job.status == STATUS_DEAD
    assert job.next_retry_at is None


def test_retryable_error_dead_letters_after_max_attempts(clock, clock_store) -> None:
    key = "core.order.export.ORDER-1"
    payload = {"marketplace_order_id": "ORDER-1"}

    _begin_job(clock_store, key, payload)  # attempt 1
    clock_store.mark_failed(key, UpstreamTimeoutError("odoo timeout"))

    clock.advance(2.0)
    _begin_job(clock_store, key, payload)  # attempt 2 (due)
    clock_store.mark_failed(key, UpstreamTimeoutError("odoo timeout"))

    clock.advance(2.0)
    _begin_job(clock_store, key, payload)  # attempt 3 (due) -> reaches max_attempts
    status = clock_store.mark_failed(key, UpstreamTimeoutError("odoo timeout"))

    assert status == STATUS_DEAD
    job = clock_store.get(key)
    assert job.status == STATUS_DEAD
    assert job.attempts == 3


def test_manual_retry_requeues_dead_job(clock, clock_store) -> None:
    key = "core.order.export.ORDER-1"
    payload = {"marketplace_order_id": "ORDER-1"}

    _begin_job(clock_store, key, payload)
    clock_store.mark_failed(key, PayloadValidationError("below MOQ"))
    assert clock_store.get(key).status == STATUS_DEAD

    clock_store.retry(key)

    job = clock_store.get(key)
    assert job.status == STATUS_FAILED
    assert job.attempts == 0
    assert job.last_error is None
    assert clock_store.list_jobs(due_only=True)  # 立即到期


def test_retry_rejects_non_failed_status(clock_store) -> None:
    key = "core.order.export.ORDER-1"
    payload = {"marketplace_order_id": "ORDER-1"}
    _begin_job(clock_store, key, payload)
    clock_store.commit(key, {"odoo_sale_order_id": 1})

    with pytest.raises(ValueError):
        clock_store.retry(key)


def test_list_jobs_filters_by_status(clock_store) -> None:
    payload = {"marketplace_order_id": "ORDER-1"}
    _begin_job(clock_store, "core.order.export.ORDER-1", payload)
    clock_store.commit("core.order.export.ORDER-1", {"odoo_sale_order_id": 1})
    _begin_job(clock_store, "core.order.export.ORDER-2", {"marketplace_order_id": "ORDER-2"})

    assert [j.idempotency_key for j in clock_store.list_jobs(status=STATUS_COMPLETED)] == [
        "core.order.export.ORDER-1"
    ]
    assert [j.idempotency_key for j in clock_store.list_jobs(status=STATUS_RUNNING)] == [
        "core.order.export.ORDER-2"
    ]


def test_get_returns_none_for_unknown(clock_store) -> None:
    assert clock_store.get("core.order.export.UNKNOWN") is None
