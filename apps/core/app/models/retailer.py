"""Retailer（买家）模型与认证状态机。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

from .base import TimestampMixin, new_uuid, sa_enum, utcnow
from .enums import RetailerStatus
from .state_machine import RETAILER_TRANSITIONS, InvalidStateTransitionError, logger

__all__ = ["Retailer"]


class Retailer(TimestampMixin, Base):
    """Marketplace 买家档案（Core 主权，见 docs/架构方案.md 第 7 节）。"""

    __tablename__ = "retailers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(
        String(320), nullable=False, unique=True, index=True
    )
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Odoo 客户映射：``odoo_partner_ref`` 是匹配 ``res.partner.ref`` 的稳定业务键
    # （如 ``DEMO-RTL-001``），``odoo_partner_id`` 是 Odoo 侧 partner 整数 ID。
    # 两者由 Integration 首次导出订单时写回（见 docs/数据模型与状态机.md §4）。
    odoo_partner_ref: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    odoo_partner_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )

    status: Mapped[RetailerStatus] = mapped_column(
        sa_enum(RetailerStatus, "retailer_status"),
        nullable=False,
        default=RetailerStatus.pending,
    )

    # 运营审核字段（approve / reject / suspend 时由运营填写）
    reviewed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    def transition_to(
        self,
        target: RetailerStatus,
        *,
        actor: str | None = None,
        note: str | None = None,
    ) -> None:
        """按认证状态机推进；非法迁移（含倒退）拒绝并记录告警日志。"""
        target = RetailerStatus(target)
        if target is self.status:
            return
        allowed = RETAILER_TRANSITIONS.get(self.status, set())
        if target not in allowed:
            logger.warning(
                "拒绝非法买家状态迁移 retailer_id=%s from=%s to=%s",
                self.id,
                self.status.value,
                target.value,
            )
            raise InvalidStateTransitionError(
                "retailer",
                self.id,
                self.status.value,
                target.value,
                (a.value for a in allowed),
            )
        old = self.status
        self.status = target
        if target in {
            RetailerStatus.approved,
            RetailerStatus.rejected,
            RetailerStatus.suspended,
        }:
            self.reviewed_by = actor
            self.reviewed_at = utcnow()
            self.review_note = note
        logger.info(
            "买家状态迁移 retailer_id=%s %s -> %s", self.id, old.value, target.value
        )
