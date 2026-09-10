"""验证数据库幂等存储 SyncJobsStore：begin/commit/abort、幂等、冲突。"""

from __future__ import annotations

import pytest

from shopstore_integration.errors import IdempotencyConflictError
from shopstore_integration.idempotency import hash_payload


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
