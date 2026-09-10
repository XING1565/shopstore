"""买家（Retailer）服务：注册、审核、查询。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.events import EventType, publish_event
from app.errors import AppError
from app.models import Retailer
from app.models.enums import RetailerStatus
from app.models.state_machine import InvalidStateTransitionError
from app.schemas import ErrorDetail, RetailerCreate, RetailerReview

__all__ = [
    "register_retailer",
    "get_retailer",
    "list_retailers",
    "review_retailer",
    "record_odoo_partner",
]


def _retailer_event_data(r: Retailer) -> dict:
    return {
        "retailer_id": r.id,
        "email": r.email,
        "company_name": r.company_name,
        "status": r.status.value,
    }


def register_retailer(
    session: Session,
    payload: RetailerCreate,
    *,
    request_id: str | None = None,
) -> Retailer:
    exists = session.query(Retailer).filter(Retailer.email == payload.email).first()
    if exists is not None:
        raise AppError(409, "conflict", "该邮箱已注册")

    retailer = Retailer(
        email=payload.email,
        company_name=payload.company_name,
        contact_name=payload.contact_name,
        phone=payload.phone,
    )
    session.add(retailer)
    session.flush()
    publish_event(
        session,
        EventType.RETAILER_REGISTERED,
        _retailer_event_data(retailer),
        request_id=request_id,
    )
    session.commit()
    return retailer


def get_retailer(session: Session, retailer_id: str) -> Retailer:
    retailer = session.get(Retailer, retailer_id)
    if retailer is None:
        raise AppError(404, "not_found", "买家不存在")
    return retailer


def list_retailers(
    session: Session,
    *,
    limit: int,
    offset: int,
) -> tuple[list[Retailer], int]:
    total = session.query(Retailer).count()
    rows = (
        session.query(Retailer)
        .order_by(Retailer.created_at.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return rows, total


def review_retailer(
    session: Session,
    retailer_id: str,
    target: RetailerStatus,
    payload: RetailerReview,
    *,
    actor: str | None = None,
    request_id: str | None = None,
) -> Retailer:
    """运营审核：pending -> approved / rejected（含 suspend / 恢复，见状态机）。"""
    retailer = get_retailer(session, retailer_id)
    try:
        retailer.transition_to(target, actor=actor, note=payload.note)
    except InvalidStateTransitionError as exc:
        raise AppError(409, "conflict", f"买家状态迁移被拒绝：{exc}") from exc

    if target is RetailerStatus.approved:
        event_type = EventType.RETAILER_APPROVED
    elif target is RetailerStatus.rejected:
        event_type = EventType.RETAILER_REJECTED
    else:
        event_type = None

    if event_type is not None:
        publish_event(
            session,
            event_type,
            _retailer_event_data(retailer),
            request_id=request_id,
        )
    session.commit()
    return retailer


def record_odoo_partner(
    session: Session,
    retailer_id: str,
    *,
    odoo_partner_ref: str | None = None,
    odoo_partner_id: int | None = None,
    request_id: str | None = None,
) -> Retailer:
    """写回买家 → Odoo partner 的外部 ID 映射（Integration 调用）。

    幂等语义：

    - 买家已映射到同一 ``odoo_partner_ref`` → 直接返回，无副作用；
    - 买家已映射到不同 ``odoo_partner_ref`` → 409（同一买家不应出现两个 partner）；
    - 首次写回 → 记录映射。
    """
    retailer = get_retailer(session, retailer_id)
    if odoo_partner_ref is not None:
        if (
            retailer.odoo_partner_ref is not None
            and retailer.odoo_partner_ref != odoo_partner_ref
        ):
            raise AppError(
                409,
                "conflict",
                "买家已映射到不同的 Odoo partner ref",
                details=[
                    ErrorDetail(
                        field="odoo_partner_ref",
                        reason=(
                            f"买家 {retailer_id} 已映射到 "
                            f"{retailer.odoo_partner_ref}，收到 {odoo_partner_ref}"
                        ),
                    )
                ],
            )
        retailer.odoo_partner_ref = odoo_partner_ref
    if odoo_partner_id is not None:
        retailer.odoo_partner_id = odoo_partner_id
    session.commit()
    return retailer
