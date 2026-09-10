"""同步任务：回传 Odoo 履约状态到 Core（Odoo -> Core 履约状态回传）。

链路：``Core Command (commerce.order.fulfillment) -> ReportFulfillmentTask
-> 映射 Odoo 交货单状态为 Core 订单状态 -> CoreAdapter.report_fulfillment``。

读取 Odoo 交货单状态的职责由轮询消费方完成（它调用
:class:`~shopstore_integration.adapters.OdooAdapter.get_delivery_status` 并把
读到的 ``odoo_status`` 写入命令负载）；本任务负责把 Odoo 状态映射为 Core 订单
状态并回传。Core 的订单状态机保证幂等与防倒退：

- 重复回传同一状态 = 空操作（Core 返回当前订单）；
- 乱序 / 倒退回传 = Core 拒绝（409），不导致状态倒退。
"""

from __future__ import annotations

from typing import Any, Optional

from ..adapters import CoreAdapter
from ..commands import Command, new_request_id
from ..idempotency import IdempotencyStore
from ..logging import IntegrationLogger
from .base import SyncTask

__all__ = [
    "ReportFulfillmentTask",
    "ODOO_STATE_TO_ORDER_STATUS",
    "map_delivery_status_to_order_status",
]

# Odoo stock.picking 状态 -> Core 订单状态。
# ``None`` 表示该状态尚无实质进展，不推进（回传被跳过）。
ODOO_STATE_TO_ORDER_STATUS: dict[str, Optional[str]] = {
    "draft": None,
    "waiting": None,
    "confirmed": "inventory_reserved",
    "assigned": "picking_ready",
    "done": "shipped",
    "cancel": "cancelled",
}

# Odoo Adapter 可能已把状态归一化为 Core 订单状态值，直接透传。
_NORMALIZED_ORDER_STATUSES = {
    "odoo_confirmed",
    "inventory_reserved",
    "picking_ready",
    "shipped",
    "cancelled",
}


def map_delivery_status_to_order_status(status: str) -> Optional[str]:
    """把 Odoo 交货单状态映射为 Core 订单状态；无实质进展返回 ``None``。"""
    if status in _NORMALIZED_ORDER_STATUSES:
        return status
    return ODOO_STATE_TO_ORDER_STATUS.get(status)


class ReportFulfillmentTask(SyncTask):
    """读取命令负载中的 Odoo 交货单状态并回传 Core。"""

    command_type = "commerce.order.fulfillment"

    def __init__(
        self,
        *,
        core: CoreAdapter,
        idempotency_store: IdempotencyStore,
        logger: Optional[IntegrationLogger] = None,
    ) -> None:
        super().__init__(idempotency_store=idempotency_store, logger=logger)
        self.core = core

    def handle(self, command: Command) -> dict[str, Any]:
        payload = command.payload
        marketplace_order_id = payload["marketplace_order_id"]
        odoo_delivery_id = payload.get("odoo_delivery_id")
        odoo_sale_order_id = payload.get("odoo_sale_order_id")
        odoo_status = payload["odoo_status"]

        target = map_delivery_status_to_order_status(odoo_status)
        result: dict[str, Any] = {
            "marketplace_order_id": marketplace_order_id,
            "odoo_delivery_id": odoo_delivery_id,
            "odoo_sale_order_id": odoo_sale_order_id,
        }
        if target is None:
            # 尚无实质进展（如 draft / waiting），不推进 Core 状态。
            result["status"] = None
            result["skipped"] = True
            return result

        request_id = command.request_id or new_request_id()
        core_view = self.core.report_fulfillment(
            marketplace_order_id,
            status=target,
            odoo_delivery_id=odoo_delivery_id,
            odoo_sale_order_id=odoo_sale_order_id,
            request_id=request_id,
            trace_id=command.trace_id,
        )
        result["status"] = core_view.get("status", target)
        return result
