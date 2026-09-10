"""同步任务重试器：对 ``sync_jobs`` 中到期失败的作业按退避重试（不丢单）。

``RetryWorker`` 依赖注册了全部同步任务的 :class:`TaskDispatcher`，把到期失败的
:class:`SyncJob` 重建为 :class:`Command` 重新分派。幂等由 ``SyncTask`` /
``SyncJobsStore`` 保证：同一键重试命中已完成记录直接返回既有结果，不会重复
创建 Odoo 销售单；若再次失败则继续退避，耗尽后进入死信等待人工重试。
"""

from __future__ import annotations

from typing import Any, Optional

from .commands import Command, new_request_id, new_trace_id
from .idempotency import IdempotencyKey
from .logging import IntegrationLogger, get_logger
from .sync_jobs import STATUS_DEAD, STATUS_FAILED, SyncJob, SyncJobsStore
from .tasks.base import TaskResult
from .tasks.dispatch import TaskDispatcher

__all__ = ["RetryWorker", "command_from_job"]


def command_from_job(job: SyncJob) -> Command:
    """从 ``sync_jobs`` 记录重建命令（供重试重新分派）。"""
    if not job.command_type:
        raise ValueError(
            f"job {job.idempotency_key!r} has no command_type; cannot rebuild command"
        )
    return Command(
        command_type=job.command_type,
        idempotency_key=IdempotencyKey.parse(job.idempotency_key),
        payload=job.payload or {},
        trace_id=job.trace_id or new_trace_id(),
        request_id=new_request_id(),
    )


class RetryWorker:
    """把到期失败的同步任务重新分派执行的轮询重试器。

    参数：
        store: 数据库任务表存储（:class:`SyncJobsStore`）。
        dispatcher: 已注册全部同步任务的 :class:`TaskDispatcher`。
    """

    def __init__(
        self,
        *,
        store: SyncJobsStore,
        dispatcher: TaskDispatcher,
        logger: Optional[IntegrationLogger] = None,
    ) -> None:
        self.store = store
        self.dispatcher = dispatcher
        self.logger = logger or get_logger("shopstore_integration.retry")

    def run_retries(
        self, *, now: Optional[Any] = None, limit: Optional[int] = None
    ) -> dict[str, int]:
        """拉取一批到期失败的作业并重试，返回按结果状态计数的摘要。"""
        due = self.store.list_jobs(due_only=True, now=now)
        if limit is not None:
            due = due[:limit]

        summary: dict[str, int] = {
            "total": len(due),
            "success": 0,
            "skipped": 0,
            "failed": 0,
            "deferred": 0,
            "dead": 0,
        }
        for job in due:
            try:
                result = self._retry_one(job)
            except ValueError as exc:
                self.logger.warning(
                    "cannot rebuild command for retry; skipping",
                    idempotency_key=job.idempotency_key,
                    error=str(exc),
                )
                summary["skipped"] += 1
                continue
            summary[result.status] += 1
        return summary

    def retry_job(self, key: str, *, now: Optional[Any] = None) -> Optional[TaskResult]:
        """人工重试：把任务重新置为立即到期并执行一次。

        任务不存在时返回 ``None``。
        """
        if self.store.get(key) is None:
            return None
        self.store.retry(key, now=now)
        job = self.store.get(key)
        if job is None:
            return None
        return self._retry_one(job)

    def _retry_one(self, job: SyncJob) -> TaskResult:
        command = command_from_job(job)
        return self.dispatcher.dispatch(command)

    def list_failed(self) -> list[SyncJob]:
        return self.store.list_jobs(status=STATUS_FAILED)

    def list_dead(self) -> list[SyncJob]:
        return self.store.list_jobs(status=STATUS_DEAD)
