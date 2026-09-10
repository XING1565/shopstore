"""``sync_jobs`` 任务表与数据库幂等存储。

阶段 1 用数据库任务表（``sync_jobs``）承载幂等键与同步任务状态，替代进程内
:class:`InMemoryIdempotencyStore`。本模块（ISSUE-0107）落地幂等键持久化：
``SyncJobsStore`` 实现与进程内实现一致的 begin / commit / abort 语义；
ISSUE-0109 将在本表上扩展重试 / 退避 / 死信字段。

幂等键 ``core.order.export.{marketplace_order_id}`` 持久化到 ``sync_jobs``，
同一订单重复触发时命中已完成的键，直接返回既有结果，不再重复创建销售单。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, Session

from .db import Base
from .errors import IdempotencyConflictError
from .idempotency import IdempotencyRecord

__all__ = ["SyncJob", "SyncJobsStore"]

_STATUS_RUNNING = "running"
_STATUS_COMPLETED = "completed"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SyncJob(Base):
    """一条同步任务 / 幂等记录。

    幂等键唯一；``status`` 为 ``running`` 表示执行中（可重试），``completed``
    表示已成功；``result`` 保存写回 Core 的外部 ID 映射等结果。
    """

    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=_STATUS_RUNNING)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class SyncJobsStore:
    """数据库幂等存储，语义与 :class:`InMemoryIdempotencyStore` 一致。

    参数：
        session_factory: 返回 SQLAlchemy ``Session`` 的可调用对象（测试用 SQLite
            内存库 + StaticPool 工厂即可）。
    """

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def begin(self, key: str, payload_hash: str) -> IdempotencyRecord:
        session = self._session_factory()
        try:
            existing = session.query(SyncJob).filter_by(idempotency_key=key).first()
            if existing is None:
                session.add(
                    SyncJob(idempotency_key=key, payload_hash=payload_hash, status=_STATUS_RUNNING)
                )
                session.commit()
                return IdempotencyRecord(key=key, status="new")

            if existing.payload_hash != payload_hash:
                raise IdempotencyConflictError(
                    "idempotency key reused with a different payload",
                    details=[{"field": "idempotency_key", "reason": "payload mismatch"}],
                )
            if existing.status == _STATUS_COMPLETED:
                return IdempotencyRecord(
                    key=key, status="completed", result=existing.result
                )
            return IdempotencyRecord(key=key, status="running")
        finally:
            session.close()

    def commit(self, key: str, result: dict[str, Any]) -> None:
        session = self._session_factory()
        try:
            row = session.query(SyncJob).filter_by(idempotency_key=key).first()
            if row is None:
                raise KeyError(f"cannot commit unknown idempotency key {key!r}")
            row.status = _STATUS_COMPLETED
            row.result = result
            session.commit()
        finally:
            session.close()

    def abort(self, key: str) -> None:
        session = self._session_factory()
        try:
            row = session.query(SyncJob).filter_by(idempotency_key=key).first()
            if row is not None:
                session.delete(row)
                session.commit()
        finally:
            session.close()
