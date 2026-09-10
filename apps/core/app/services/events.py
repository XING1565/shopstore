"""领域事件 outbox 消费服务（供 Integration 轮询消费）。

Core 只发布领域事件到 ``domain_events`` 表（见 :mod:`app.domain.events`），
不 import Woo / Odoo Adapter 细节。Integration（ISSUE-0107 等）通过本服务的
HTTP 端点轮询待处理事件、处理完成后确认（ack）标记为已发布。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.errors import AppError
from app.models.base import utcnow
from app.models.outbox import OutboxEvent
from app.schemas import DomainEventView, to_utc_iso

__all__ = ["list_pending_events", "ack_event", "event_to_view"]


def event_to_view(event: OutboxEvent) -> DomainEventView:
    return DomainEventView(
        event_id=event.id,
        event_type=event.event_type,
        event_version=event.event_version,
        source=event.source,
        occurred_at=to_utc_iso(event.occurred_at),
        trace_id=event.trace_id,
        request_id=event.request_id,
        data=event.data,
    )


def list_pending_events(
    session: Session,
    *,
    event_type: str | None,
    limit: int,
) -> list[OutboxEvent]:
    """返回未发布（未 ack）的领域事件，按发生时间升序。"""
    query = session.query(OutboxEvent).filter(OutboxEvent.published.is_(False))
    if event_type:
        query = query.filter(OutboxEvent.event_type == event_type)
    return query.order_by(OutboxEvent.created_at.asc()).limit(limit).all()


def ack_event(session: Session, event_id: str) -> OutboxEvent:
    """确认事件已成功消费，标记为已发布（幂等：重复 ack 无副作用）。"""
    event = session.get(OutboxEvent, event_id)
    if event is None:
        raise AppError(404, "not_found", "事件不存在")
    if not event.published:
        event.published = True
        event.published_at = utcnow()
        session.commit()
    return event
