"""领域事件 outbox 表（Core 发布领域事件，不 import Woo / Odoo Adapter）。

Core 领域模块（注册 / 审核 / 商品发布 / 下单）在本表持久化领域事件，
Integration 层（ISSUE-0107 等）轮询消费并把投影写回 Core。
事件信封结构与 ``packages/contracts/events/envelope.schema.json`` 一致。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

from .base import new_uuid, utcnow

__all__ = ["OutboxEvent"]


class OutboxEvent(Base):
    """一条待消费 / 已消费的领域事件。

    ``id`` 即事件信封的 ``event_id``（UUID v4）；``data`` 即信封的 ``data`` 负载。
    事件类型遵循 ``{domain}.{entity}.{past_tense_verb}``（如 ``commerce.order.created``）。
    """

    __tablename__ = "domain_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    event_type: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_version: Mapped[str] = mapped_column(String(8), nullable=False, default="1")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="core")

    trace_id: Mapped[str] = mapped_column(String(36), nullable=False, default=new_uuid)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    data: Mapped[dict] = mapped_column(JSON, nullable=False)

    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def envelope(self) -> dict:
        """返回与 ``envelope.schema.json`` 一致的事件信封。"""
        return {
            "event_id": self.id,
            "event_type": self.event_type,
            "event_version": self.event_version,
            "source": self.source,
            "occurred_at": self.occurred_at,
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "data": self.data,
        }
