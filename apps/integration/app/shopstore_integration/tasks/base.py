"""同步任务抽象。

链路：``Core Command -> Integration Task -> Adapter -> Result``。

:class:`SyncTask` 负责编排：幂等检查（:class:`IdempotencyStore`）、
委托给具体 Adapter、错误分类与日志；子类只需实现 :meth:`SyncTask.handle`，
描述「收到命令后要做什么」，无需关心幂等与错误捕获。

阶段 1 使用 :class:`RetryableIdempotencyStore`（数据库 ``sync_jobs`` 表）时，
失败不再静默释放预留，而是记录失败并按退避排期重试 / 进入死信（ISSUE-0109）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

from ..commands import Command
from ..errors import IntegrationError
from ..idempotency import (
    IdempotencyStore,
    RetryableIdempotencyStore,
    hash_payload,
)
from ..logging import IntegrationLogger, get_logger


@dataclass(frozen=True)
class TaskStatus:
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    DEFERRED = "deferred"
    DEAD = "dead"


@dataclass(frozen=True)
class TaskResult:
    """同步任务的一次执行结果。"""

    status: str
    command_type: str
    idempotency_key: str
    trace_id: str
    request_id: Optional[str] = None
    external_ids: dict[str, Any] = field(default_factory=dict)
    error: Optional[IntegrationError] = None

    @property
    def ok(self) -> bool:
        return self.status in (TaskStatus.SUCCESS, TaskStatus.SKIPPED)


class SyncTask(ABC):
    """同步任务基类：封装幂等、错误捕获与日志。"""

    command_type: str = ""

    def __init__(
        self,
        *,
        idempotency_store: IdempotencyStore,
        logger: Optional[IntegrationLogger] = None,
    ) -> None:
        self.idempotency_store = idempotency_store
        self.logger = logger or get_logger("shopstore_integration.tasks")

    def _begin(self, command: Command, key: str, payload_hash: str):
        if isinstance(self.idempotency_store, RetryableIdempotencyStore):
            return self.idempotency_store.begin(
                key,
                payload_hash,
                command_type=command.command_type,
                payload=command.payload,
                trace_id=command.trace_id,
            )
        return self.idempotency_store.begin(key, payload_hash)

    def _record_failure(self, key: str, error: IntegrationError) -> None:
        if isinstance(self.idempotency_store, RetryableIdempotencyStore):
            self.idempotency_store.mark_failed(key, error)
        else:
            self.idempotency_store.abort(key)

    def execute(self, command: Command) -> TaskResult:
        """执行命令：先幂等检查，再委托 :meth:`handle`，统一捕获错误。"""
        key = command.idempotency_key_value
        record = self._begin(command, key, hash_payload(command.payload))

        if record.status == "completed":
            self.logger.info(
                "sync task skipped (idempotent)",
                command_type=command.command_type,
                idempotency_key=key,
                trace_id=command.trace_id,
            )
            return TaskResult(
                status=TaskStatus.SKIPPED,
                command_type=command.command_type,
                idempotency_key=key,
                trace_id=command.trace_id,
                request_id=command.request_id,
                external_ids=record.result or {},
            )

        if record.status == "dead":
            self.logger.error(
                "sync task dead-lettered; manual retry required",
                command_type=command.command_type,
                idempotency_key=key,
                trace_id=command.trace_id,
            )
            return TaskResult(
                status=TaskStatus.DEAD,
                command_type=command.command_type,
                idempotency_key=key,
                trace_id=command.trace_id,
                request_id=command.request_id,
            )

        if record.status in ("deferred", "running"):
            reason = "backoff not elapsed" if record.status == "deferred" else "already in progress"
            self.logger.info(
                "sync task deferred",
                command_type=command.command_type,
                idempotency_key=key,
                trace_id=command.trace_id,
                reason=reason,
            )
            return TaskResult(
                status=TaskStatus.DEFERRED,
                command_type=command.command_type,
                idempotency_key=key,
                trace_id=command.trace_id,
                request_id=command.request_id,
            )

        self.logger.info(
            "sync task started",
            command_type=command.command_type,
            idempotency_key=key,
            trace_id=command.trace_id,
        )

        try:
            external_ids = self.handle(command)
        except IntegrationError as exc:
            self._record_failure(key, exc)
            self.logger.error(
                "sync task failed",
                command_type=command.command_type,
                idempotency_key=key,
                trace_id=command.trace_id,
                error_code=exc.code,
            )
            return TaskResult(
                status=TaskStatus.FAILED,
                command_type=command.command_type,
                idempotency_key=key,
                trace_id=command.trace_id,
                request_id=command.request_id,
                error=exc,
            )

        self.idempotency_store.commit(key, external_ids)
        self.logger.info(
            "sync task completed",
            command_type=command.command_type,
            idempotency_key=key,
            trace_id=command.trace_id,
        )
        return TaskResult(
            status=TaskStatus.SUCCESS,
            command_type=command.command_type,
            idempotency_key=key,
            trace_id=command.trace_id,
            request_id=command.request_id,
            external_ids=external_ids,
        )

    @abstractmethod
    def handle(self, command: Command) -> dict[str, Any]:
        """执行实际业务动作，返回写入 Core 的外部 ID 映射（external_ids）。"""
        raise NotImplementedError


__all__ = ["SyncTask", "TaskResult", "TaskStatus"]
