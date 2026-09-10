"""Order（订单）聚合：订单主实体、订单行、状态事件。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

from .base import TimestampMixin, new_uuid, sa_enum, utcnow
from .enums import OrderStatus
from .state_machine import (
    ORDER_RESUMABLE_STATES,
    ORDER_TRANSITIONS,
    InvalidStateTransitionError,
    logger,
)

__all__ = ["Order", "OrderLine", "OrderStatusEvent"]


class Order(TimestampMixin, Base):
    """Marketplace 订单业务主实体（Core 主权）。

    ``id`` 即契约 `order.schema.json` 中的 ``marketplace_order_id``（UUID v4）。
    外部 ID 映射（``woo_order_id`` / ``odoo_sale_order_id`` / ``odoo_delivery_id``）
    为 NULL 时表示该投影尚未创建。
    """

    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    retailer_id: Mapped[str] = mapped_column(
        ForeignKey("retailers.id"), nullable=False, index=True
    )

    status: Mapped[OrderStatus] = mapped_column(
        sa_enum(OrderStatus, "order_status"),
        nullable=False,
        default=OrderStatus.draft,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    # 外部 ID 映射（NULL = 投影尚未创建）
    woo_order_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    odoo_sale_order_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    odoo_delivery_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )

    # sync_failed 恢复点（进入 sync_failed 前的状态值，重试成功后回退）
    sync_failed_from: Mapped[str | None] = mapped_column(String(32), nullable=True)

    lines: Mapped[list["OrderLine"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )
    status_events: Mapped[list["OrderStatusEvent"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderStatusEvent.occurred_at",
    )

    def allowed_transitions(self) -> set[OrderStatus]:
        """返回当前状态允许迁移到的目标状态集合。"""
        if self.status is OrderStatus.sync_failed:
            if self.sync_failed_from:
                return {OrderStatus(self.sync_failed_from)}
            return set(ORDER_RESUMABLE_STATES)
        return ORDER_TRANSITIONS.get(self.status, set())

    def transition_to(
        self,
        target: OrderStatus,
        *,
        reason: str | None = None,
        actor: str | None = None,
    ) -> None:
        """按订单状态机单向推进；非法迁移（含倒退）拒绝并记录告警日志。

        每次成功迁移追加一条 :class:`OrderStatusEvent` 审计记录。
        """
        target = OrderStatus(target)
        if target is self.status:
            return
        allowed = self.allowed_transitions()
        if target not in allowed:
            logger.warning(
                "拒绝非法订单状态迁移 order_id=%s from=%s to=%s",
                self.id,
                self.status.value,
                target.value,
            )
            raise InvalidStateTransitionError(
                "order",
                self.id,
                self.status.value,
                target.value,
                (a.value for a in allowed),
            )
        old = self.status
        if target is OrderStatus.sync_failed:
            self.sync_failed_from = old.value
        elif self.status is OrderStatus.sync_failed:
            self.sync_failed_from = None
        self.status = target
        self.status_events.append(
            OrderStatusEvent(
                from_status=old.value,
                to_status=target.value,
                reason=reason,
                actor=actor,
            )
        )
        logger.info(
            "订单状态迁移 order_id=%s %s -> %s", self.id, old.value, target.value
        )


class OrderLine(Base):
    """订单行：SKU 快照 + 数量 + 单价（最小单位整数）。"""

    __tablename__ = "order_lines"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order: Mapped["Order"] = relationship(back_populates="lines")

    sku: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    unit_price_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD"
    )


class OrderStatusEvent(Base):
    """订单状态变更审计记录（跨系统编排所需的状态与审计信息）。"""

    __tablename__ = "order_status_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    order_id: Mapped[str] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    order: Mapped["Order"] = relationship(back_populates="status_events")

    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
