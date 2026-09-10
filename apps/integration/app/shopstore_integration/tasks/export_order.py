"""示例同步任务：导出 Core 订单到 Odoo 销售单（阶段 0 占位，不实现正式同步）。"""

from __future__ import annotations

from typing import Any, Optional

from ..adapters import OdooAdapter
from ..commands import Command, new_request_id
from ..idempotency import IdempotencyStore
from ..logging import IntegrationLogger
from .base import SyncTask


class ExportOrderTask(SyncTask):
    """把 Core 订单导出为 Odoo 销售单，写回 ``odoo_sale_order_id``。

    阶段 0 仅验证链路，不实现正式订单同步语义。
    """

    command_type = "commerce.order.export"

    def __init__(
        self,
        *,
        odoo: OdooAdapter,
        idempotency_store: IdempotencyStore,
        logger: Optional[IntegrationLogger] = None,
    ) -> None:
        super().__init__(idempotency_store=idempotency_store, logger=logger)
        self.odoo = odoo

    def handle(self, command: Command) -> dict[str, Any]:
        request_id = command.request_id or new_request_id()
        result = self.odoo.create_sale_order(command.payload, request_id=request_id)
        external_ids: dict[str, Any] = {
            "marketplace_order_id": command.payload["marketplace_order_id"],
            "odoo_sale_order_id": result["odoo_sale_order_id"],
        }
        if result.get("odoo_partner_id") is not None:
            external_ids["odoo_partner_id"] = result["odoo_partner_id"]
        if result.get("odoo_partner_ref"):
            external_ids["odoo_partner_ref"] = result["odoo_partner_ref"]
        return external_ids


__all__ = ["ExportOrderTask"]
