"""领域状态机：单向推进 + 明确回退规则。

- Order 主线（``submitted -> ... -> shipped -> completed``）只允许单向推进，
  任何状态倒退（如 ``shipped -> inventory_reserved``）都会被拒绝。
- ``cancelled`` 是终态，仅允许从发货前状态进入。
- ``sync_failed`` 是可恢复的旁路状态：进入时记录来源状态（``sync_failed_from``），
  重试成功后回退到该来源状态；不允许跳到其他状态。

非法迁移会：1) 记录告警日志；2) 抛出 :class:`InvalidStateTransitionError`。
"""

from __future__ import annotations

import logging
from collections.abc import Iterable

from .enums import OrderStatus, RetailerStatus

__all__ = [
    "InvalidStateTransitionError",
    "ORDER_TRANSITIONS",
    "ORDER_RESUMABLE_STATES",
    "RETAILER_TRANSITIONS",
]

logger = logging.getLogger("app.state_machine")


class InvalidStateTransitionError(ValueError):
    """非法状态迁移（含状态倒退）异常。"""

    def __init__(
        self,
        entity: str,
        entity_id: str | None,
        current: str,
        target: str,
        allowed: Iterable[str],
    ) -> None:
        self.entity = entity
        self.entity_id = entity_id
        self.current = current
        self.target = target
        self.allowed = sorted(allowed)
        super().__init__(
            f"{entity} 非法状态迁移: {current} -> {target}；允许目标: {self.allowed}"
        )


# 订单状态机：仅单向推进 + 明确回退
ORDER_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.draft: {OrderStatus.submitted, OrderStatus.cancelled},
    OrderStatus.submitted: {OrderStatus.sent_to_odoo, OrderStatus.cancelled},
    OrderStatus.sent_to_odoo: {
        OrderStatus.odoo_confirmed,
        OrderStatus.sync_failed,
        OrderStatus.cancelled,
    },
    OrderStatus.odoo_confirmed: {
        OrderStatus.inventory_reserved,
        OrderStatus.sync_failed,
        OrderStatus.cancelled,
    },
    OrderStatus.inventory_reserved: {
        OrderStatus.picking_ready,
        OrderStatus.sync_failed,
        OrderStatus.cancelled,
    },
    OrderStatus.picking_ready: {
        OrderStatus.shipped,
        OrderStatus.sync_failed,
        OrderStatus.cancelled,
    },
    OrderStatus.shipped: {OrderStatus.completed},
    OrderStatus.completed: set(),
    OrderStatus.cancelled: set(),
    OrderStatus.sync_failed: set(),
}

# sync_failed 可回退到的状态（重试成功后恢复）
ORDER_RESUMABLE_STATES = {
    OrderStatus.sent_to_odoo,
    OrderStatus.odoo_confirmed,
    OrderStatus.inventory_reserved,
    OrderStatus.picking_ready,
}

# Retailer 认证状态机（核心路径 Pending -> Approved）
RETAILER_TRANSITIONS: dict[RetailerStatus, set[RetailerStatus]] = {
    RetailerStatus.pending: {RetailerStatus.approved, RetailerStatus.rejected},
    RetailerStatus.approved: {RetailerStatus.suspended},
    RetailerStatus.suspended: {RetailerStatus.approved},
    RetailerStatus.rejected: set(),
}
