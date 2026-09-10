"""订单导出 Worker：订阅 Core 订单事件，在 Odoo 创建销售单并写回。

链路：

    Core ``commerce.order.created`` 事件
      -> 轮询 Core ``GET /api/v1/events``
      -> 去重（Core 订单已有 ``odoo_sale_order_id`` 则跳过）
      -> :class:`ExportOrderTask`（幂等键 + Odoo ``client_order_ref`` 去重）
      -> 写回 ``odoo_sale_order_id``（Core ``POST /orders/{id}/external-ids``）
      -> ack 事件（``POST /events/{id}/ack``）

同一订单重复触发不会重复创建销售单：三层去重（Core 映射检查、``sync_jobs``
幂等键、Odoo ``client_order_ref`` 查找）保证幂等。
"""

from __future__ import annotations

from typing import Any, Optional

from .adapters import OdooAdapter
from .commands import export_order_command, new_request_id
from .core_client import CoreClient
from .idempotency import IdempotencyStore
from .logging import IntegrationLogger, get_logger
from .tasks.base import TaskResult, TaskStatus
from .tasks.dispatch import TaskDispatcher
from .tasks.export_order import ExportOrderTask

__all__ = ["OrderExportWorker"]


class OrderExportWorker:
    """把 Core 订单事件导出为 Odoo 销售单的轮询 Worker。

    参数：
        core: Core Marketplace API 客户端（:class:`CoreClient`）。
        odoo: Odoo Adapter（真实 :class:`HttpOdooAdapter` 或测试替身）。
        idempotency_store: 幂等存储（阶段 1 用 :class:`SyncJobsStore`）。
    """

    EVENT_TYPE = "commerce.order.created"

    def __init__(
        self,
        *,
        core: CoreClient,
        odoo: OdooAdapter,
        idempotency_store: IdempotencyStore,
        logger: Optional[IntegrationLogger] = None,
    ) -> None:
        self.core = core
        self.odoo = odoo
        self.logger = logger or get_logger("shopstore_integration.worker")
        self._task = ExportOrderTask(
            odoo=odoo, idempotency_store=idempotency_store, logger=self.logger
        )
        self._dispatcher = TaskDispatcher()
        self._dispatcher.register(self._task)

    def run_once(self, *, limit: int = 50) -> int:
        """拉取并处理一批待消费订单事件，返回处理的事件数。

        每个事件独立 try/except：单个事件失败不阻断整批，失败事件不 ack，
        留待下一轮重试（幂等键保证不重复创建销售单）。
        """
        request_id = new_request_id()
        events = self.core.list_pending_events(
            event_type=self.EVENT_TYPE, limit=limit, request_id=request_id
        )
        for event in events:
            self._process_event(event)
        return len(events)

    def _process_event(self, event: dict[str, Any]) -> None:
        event_id = event.get("event_id")
        trace_id = event.get("trace_id")
        data = event.get("data") or {}
        request_id = event.get("request_id") or new_request_id()
        marketplace_order_id = data.get("marketplace_order_id")
        retailer_id = data.get("retailer_id")

        if not marketplace_order_id or not retailer_id:
            self.logger.error(
                "order event missing required fields; leaving unacked",
                event_id=event_id,
                trace_id=trace_id,
            )
            return

        try:
            order = self.core.get_order(marketplace_order_id, request_id=request_id)
            if (order.get("external_ids") or {}).get("odoo_sale_order_id"):
                self.logger.info(
                    "order already mapped to odoo sale order; skip",
                    marketplace_order_id=marketplace_order_id,
                    trace_id=trace_id,
                )
                self.core.ack_event(event_id, request_id=request_id)
                return
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                "cannot read core order; will retry",
                marketplace_order_id=marketplace_order_id,
                error=str(exc),
            )
            return

        try:
            retailer = self.core.get_retailer(retailer_id, request_id=request_id)
            command = export_order_command(
                marketplace_order_id=marketplace_order_id,
                lines=data.get("lines", []),
                retailer_ref=retailer_id,
                retailer_name=retailer.get("company_name"),
                retailer_email=retailer.get("email"),
                trace_id=trace_id,
                request_id=request_id,
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                "cannot read core retailer; will retry",
                marketplace_order_id=marketplace_order_id,
                error=str(exc),
            )
            return

        result: TaskResult = self._dispatcher.dispatch(command)
        if result.status == TaskStatus.DEFERRED:
            self.logger.info(
                "order export deferred (backoff); leaving event pending",
                marketplace_order_id=marketplace_order_id,
                trace_id=trace_id,
            )
            return
        if result.status == TaskStatus.DEAD:
            self.logger.error(
                "order export dead-lettered; manual retry required",
                marketplace_order_id=marketplace_order_id,
                trace_id=trace_id,
            )
            return
        if not result.ok:
            self.logger.error(
                "order export failed; leaving event pending for retry",
                marketplace_order_id=marketplace_order_id,
                trace_id=trace_id,
                error_code=result.error.code if result.error else None,
            )
            return

        odoo_sale_order_id = result.external_ids.get("odoo_sale_order_id")
        if not odoo_sale_order_id:
            self.logger.error(
                "order export returned no odoo_sale_order_id; leaving pending",
                marketplace_order_id=marketplace_order_id,
            )
            return

        try:
            self.core.record_odoo_sale_order(
                marketplace_order_id,
                odoo_sale_order_id,
                request_id=request_id,
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.error(
                "writeback odoo_sale_order_id failed; leaving pending",
                marketplace_order_id=marketplace_order_id,
                odoo_sale_order_id=odoo_sale_order_id,
                error=str(exc),
            )
            return

        self.core.ack_event(event_id, request_id=request_id)
        self.logger.info(
            "order exported to odoo and written back",
            marketplace_order_id=marketplace_order_id,
            odoo_sale_order_id=odoo_sale_order_id,
            trace_id=trace_id,
        )
