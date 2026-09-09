"""示例同步任务：发布商品到 Woo / Odoo（阶段 0 Mock 链路）。"""

from __future__ import annotations

from typing import Any, Optional

from ..adapters import OdooAdapter, WooAdapter
from ..commands import Command, new_request_id
from ..idempotency import IdempotencyStore
from ..logging import IntegrationLogger
from .base import SyncTask


class PublishProductTask(SyncTask):
    """把 Core 商品发布到 Woo 与 Odoo，写回外部 ID 映射。

    验证完整链路：Core Command -> Integration Task -> (Woo/Odoo) Adapter -> Result。
    """

    command_type = "catalog.product.publish"

    def __init__(
        self,
        *,
        woo: WooAdapter,
        odoo: OdooAdapter,
        idempotency_store: IdempotencyStore,
        logger: Optional[IntegrationLogger] = None,
    ) -> None:
        super().__init__(idempotency_store=idempotency_store, logger=logger)
        self.woo = woo
        self.odoo = odoo

    def handle(self, command: Command) -> dict[str, Any]:
        payload = command.payload
        sku = payload["sku"]
        request_id = command.request_id or new_request_id()

        woo_result = self.woo.upsert_product(
            {"sku": sku, "name": payload["name"], "price": payload["price"]},
            request_id=request_id,
        )
        odoo_result = self.odoo.upsert_product(
            {"sku": sku, "name": payload["name"]},
            request_id=request_id,
        )
        return {
            "sku": sku,
            "woo_product_id": woo_result["woo_product_id"],
            "odoo_product_id": odoo_result["odoo_product_id"],
        }


__all__ = ["PublishProductTask"]
