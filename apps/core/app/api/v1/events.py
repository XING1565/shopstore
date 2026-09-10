"""领域事件 outbox 消费 API（供 Integration 轮询 / 确认）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import PrincipalDep, SessionDep, require_operator
from app.schemas import DomainEventList
from app.services import events as event_service

router = APIRouter(tags=["events"])


@router.get(
    "/events",
    response_model=DomainEventList,
    response_model_exclude_none=True,
    summary="列出待消费（未确认）的领域事件",
    operation_id="listPendingEvents",
)
def list_pending_events(
    session: SessionDep,
    principal: PrincipalDep,
    event_type: Annotated[str | None, Query(max_length=255)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> DomainEventList:
    require_operator(principal)
    rows = event_service.list_pending_events(
        session, event_type=event_type, limit=limit
    )
    return DomainEventList(
        items=[event_service.event_to_view(e) for e in rows],
        total=len(rows),
        limit=limit,
    )


@router.post(
    "/events/{event_id}/ack",
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
    summary="确认领域事件已成功消费",
    operation_id="ackEvent",
)
def ack_event(
    event_id: str,
    session: SessionDep,
    principal: PrincipalDep,
) -> None:
    require_operator(principal)
    event_service.ack_event(session, event_id)
