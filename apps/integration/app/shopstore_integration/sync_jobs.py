"""``sync_jobs`` 任务表与数据库幂等存储。

阶段 1 用数据库任务表（``sync_jobs``）承载幂等键与同步任务状态，替代进程内
:class:`InMemoryIdempotencyStore`。本模块（ISSUE-0107）落地幂等键持久化；
ISSUE-0109 在本表上扩展重试 / 退避 / 死信字段：

- 幂等键 ``core.order.export.{marketplace_order_id}`` 持久化到 ``sync_jobs``，
  同一订单重复触发时命中已完成的键，直接返回既有结果，不再重复创建销售单；
- ``status`` 状态机：``running``（执行中）→ ``completed``（成功）
  或 ``failed``（失败待重试）→ ``dead``（重试耗尽，死信）；
- 每次失败递增 ``attempts`` 并按指数退避计算 ``next_retry_at``；
  可重试错误在达到 ``max_attempts`` 后进入死信，不可重试错误直接死信；
- 失败记录 ``last_error`` 持久化，供后台可见与人工重试（:meth:`retry`）。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Optional

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, Session

from .config import RetryConfig
from .db import Base
from .errors import IdempotencyConflictError, is_retryable
from .idempotency import IdempotencyRecord

__all__ = ["SyncJob", "SyncJobsStore", "compute_backoff_delay", "JOB_STATUSES"]

STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_DEAD = "dead"

JOB_STATUSES = (STATUS_RUNNING, STATUS_COMPLETED, STATUS_FAILED, STATUS_DEAD)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """把 SQLite 读出的 naive datetime 归一化为 aware UTC（PostgreSQL 原样返回）。"""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def compute_backoff_delay(attempts: int, retry_config: RetryConfig) -> float:
    """按已完成失败次数计算下一次重试的退避秒数（指数退避）。

    第 1 次失败（``attempts == 1``）退避 ``backoff_seconds``，之后每次乘以
    ``backoff_factor``。
    """
    exponent = max(attempts - 1, 0)
    return retry_config.backoff_seconds * (retry_config.backoff_factor ** exponent)


class SyncJob(Base):
    """一条同步任务 / 幂等记录。

    幂等键唯一；``status`` 为 ``running`` 表示执行中（可重试），``completed``
    表示已成功；``failed`` 表示失败且已按退避排期重试；``dead`` 表示重试耗尽
    （死信，需人工 :meth:`SyncJobsStore.retry`）。``result`` 保存写回 Core 的
    外部 ID 映射等结果，``payload`` / ``command_type`` / ``trace_id`` 用于在
    重试时重建命令，``last_error`` 保存最近一次失败的分类信息。
    """

    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    command_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    payload: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=STATUS_RUNNING)
    result: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )

    def to_dict(self) -> dict[str, Any]:
        """序列化为普通字典（后台可见 / CLI 输出用）。"""
        return {
            "id": self.id,
            "idempotency_key": self.idempotency_key,
            "command_type": self.command_type,
            "status": self.status,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "last_error": self.last_error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class SyncJobsStore:
    """数据库幂等存储，语义与 :class:`InMemoryIdempotencyStore` 一致，并扩展
    重试 / 退避 / 死信 / 人工重试（ISSUE-0109）。

    参数：
        session_factory: 返回 SQLAlchemy ``Session`` 的可调用对象（测试用 SQLite
            内存库 + StaticPool 工厂即可）。
        retry_config: 退避 / 重试上限配置，缺省 :class:`RetryConfig`。
        clock: 返回当前 UTC 时间的可调用对象，测试注入以控制退避时间。
    """

    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        retry_config: Optional[RetryConfig] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self._session_factory = session_factory
        self._retry_config = retry_config or RetryConfig()
        self._clock = clock or utcnow

    def begin(
        self,
        key: str,
        payload_hash: str,
        *,
        command_type: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        max_attempts: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> IdempotencyRecord:
        """预留一个幂等键（记录命令信息以便重试），返回下一步动作。

        ``status`` 取值：
        - ``"new"``：新建或到期可重试，调用方应执行；
        - ``"running"``：已有执行中记录，调用方应跳过（并发去重）；
        - ``"completed"``：已完成，携带既有 ``result``；
        - ``"deferred"``：失败且退避未到期，调用方应跳过并等待；
        - ``"dead"``：死信，需人工重试。
        """
        now = now or self._clock()
        session = self._session_factory()
        try:
            existing = session.query(SyncJob).filter_by(idempotency_key=key).first()
            if existing is None:
                session.add(
                    SyncJob(
                        idempotency_key=key,
                        payload_hash=payload_hash,
                        command_type=command_type,
                        payload=payload,
                        trace_id=trace_id,
                        status=STATUS_RUNNING,
                        attempts=0,
                        max_attempts=max_attempts or self._retry_config.max_attempts,
                    )
                )
                session.commit()
                return IdempotencyRecord(key=key, status="new")

            if existing.payload_hash != payload_hash:
                raise IdempotencyConflictError(
                    "idempotency key reused with a different payload",
                    details=[{"field": "idempotency_key", "reason": "payload mismatch"}],
                )

            if existing.status == STATUS_COMPLETED:
                return IdempotencyRecord(
                    key=key, status="completed", result=existing.result
                )
            if existing.status == STATUS_DEAD:
                return IdempotencyRecord(key=key, status="dead")
            if existing.status == STATUS_FAILED:
                next_retry_at = _as_utc(existing.next_retry_at)
                if next_retry_at is None or next_retry_at <= now:
                    existing.status = STATUS_RUNNING
                    session.commit()
                    return IdempotencyRecord(key=key, status="new")
                return IdempotencyRecord(key=key, status="deferred")
            return IdempotencyRecord(key=key, status="running")
        finally:
            session.close()

    def commit(self, key: str, result: dict[str, Any]) -> None:
        session = self._session_factory()
        try:
            row = session.query(SyncJob).filter_by(idempotency_key=key).first()
            if row is None:
                raise KeyError(f"cannot commit unknown idempotency key {key!r}")
            row.status = STATUS_COMPLETED
            row.result = result
            row.next_retry_at = None
            row.last_error = None
            session.commit()
        finally:
            session.close()

    def abort(self, key: str) -> None:
        """释放预留（执行失败时允许用同一键重试）。"""
        session = self._session_factory()
        try:
            row = session.query(SyncJob).filter_by(idempotency_key=key).first()
            if row is not None:
                session.delete(row)
                session.commit()
        finally:
            session.close()

    def mark_failed(self, key: str, error: BaseException, *, now: Optional[datetime] = None) -> str:
        """记录一次失败并调度重试 / 死信，返回新状态（``failed`` 或 ``dead``）。

        可重试错误按指数退避排期下一次重试；不可重试错误或已达 ``max_attempts``
        时直接进入死信。
        """
        now = now or self._clock()
        session = self._session_factory()
        try:
            row = session.query(SyncJob).filter_by(idempotency_key=key).first()
            if row is None:
                raise KeyError(f"cannot mark unknown idempotency key {key!r}")

            row.attempts += 1
            row.last_error = {
                "code": getattr(error, "code", "integration_error"),
                "message": str(error),
            }

            if not is_retryable(error) or row.attempts >= row.max_attempts:
                row.status = STATUS_DEAD
                row.next_retry_at = None
            else:
                row.status = STATUS_FAILED
                delay = compute_backoff_delay(row.attempts, self._retry_config)
                row.next_retry_at = now + timedelta(seconds=delay)

            session.commit()
            return row.status
        finally:
            session.close()

    def retry(self, key: str, *, now: Optional[datetime] = None) -> None:
        """人工重试：把失败 / 死信任务重新置为立即到期，并重置重试预算。

        仅对 ``failed`` / ``dead`` 任务有效；其余状态抛 :class:`ValueError`。
        """
        now = now or self._clock()
        session = self._session_factory()
        try:
            row = session.query(SyncJob).filter_by(idempotency_key=key).first()
            if row is None:
                raise KeyError(f"cannot retry unknown idempotency key {key!r}")
            if row.status not in (STATUS_FAILED, STATUS_DEAD):
                raise ValueError(
                    f"cannot retry job in status {row.status!r}; only failed/dead can be retried"
                )
            row.status = STATUS_FAILED
            row.next_retry_at = now
            row.attempts = 0
            row.last_error = None
            session.commit()
        finally:
            session.close()

    def get(self, key: str) -> Optional[SyncJob]:
        session = self._session_factory()
        try:
            return session.query(SyncJob).filter_by(idempotency_key=key).first()
        finally:
            session.close()

    def list_jobs(
        self,
        *,
        status: Optional[str] = None,
        due_only: bool = False,
        now: Optional[datetime] = None,
    ) -> list[SyncJob]:
        """列出任务（后台可见）。``due_only`` 只返回到期可重试的 ``failed`` 任务。"""
        now = now or self._clock()
        session = self._session_factory()
        try:
            query = session.query(SyncJob)
            if status is not None:
                query = query.filter(SyncJob.status == status)
            if due_only:
                query = query.filter(
                    SyncJob.status == STATUS_FAILED,
                    SyncJob.next_retry_at.isnot(None),
                    SyncJob.next_retry_at <= now,
                )
            return query.all()
        finally:
            session.close()
