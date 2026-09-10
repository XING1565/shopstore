"""履约状态回传长驻轮询 worker（ISSUE-0115）。

链路：

    Core 订单（已写回 ``odoo_sale_order_id`` 且未到履约终态）
      -> 读 Odoo 出库交货单（``stock.picking``）状态
      -> 按状态机阶梯计算需按序回传的 Core 订单状态
      -> 逐状态分派 :class:`ReportFulfillmentTask`（幂等 + 重试 / 退避）
      -> Core 单向推进（重复 / 乱序 / 倒退由 Core 状态机拒绝）

轮询幂等：:func:`report_fulfillment_command` 的幂等键按
``odoo_delivery_id + odoo_status`` 区分，同一交货单的同一状态只回传一次；
重复 / 乱序回传不会导致状态倒退（非法迁移由 Core 拒绝并记录）。

Core 的订单状态机比 Odoo 交货单状态更细（``sent_to_odoo -> odoo_confirmed ->
inventory_reserved -> picking_ready -> shipped``），因此 worker 会按
:data:`FULFILLMENT_STATUS_LADDER` 补齐中间状态，保证按状态机单向推进。
"""

from __future__ import annotations

import time
from typing import Any, Optional

from .adapters import OdooAdapter
from .commands import new_request_id, report_fulfillment_command
from .core_client import CoreClient
from .errors import IntegrationError
from .logging import IntegrationLogger, get_logger
from .tasks.base import TaskResult, TaskStatus
from .tasks.dispatch import TaskDispatcher
from .tasks.report_fulfillment import map_delivery_status_to_order_status

__all__ = [
    "FulfillmentSyncWorker",
    "FULFILLMENT_STATUS_LADDER",
    "POLLABLE_STATUSES",
    "fulfillment_status_path",
]

# 履约主线状态阶梯：从「Odoo 已确认」到「已发货」的单向推进顺序。
FULFILLMENT_STATUS_LADDER: list[str] = [
    "odoo_confirmed",
    "inventory_reserved",
    "picking_ready",
    "shipped",
]

# 需要轮询的 Core 订单状态（已导出到 Odoo 且未到履约终态）。
POLLABLE_STATUSES = {
    "sent_to_odoo",
    "odoo_confirmed",
    "inventory_reserved",
    "picking_ready",
}

_TERMINAL_STATUSES = {"shipped", "completed", "cancelled"}


def fulfillment_status_path(current: str, target: Optional[str]) -> list[str]:
    """计算从 ``current`` 到 ``target`` 需要按序回传的 Core 订单状态。

    - ``target`` 为 ``None``（Odoo 侧尚无实质进展）时返回空列表；
    - ``target`` 为 ``cancelled`` 时单独返回 ``["cancelled"]``（是否允许由 Core
      状态机校验）；
    - 其余目标状态按 :data:`FULFILLMENT_STATUS_LADDER` 截取尚未到达的阶梯区间，
      保证 Core 状态机单向推进（补齐被粗粒度 Odoo 状态跳过的中间态）。
    """
    if target is None:
        return []
    if target == "cancelled":
        if current in _TERMINAL_STATUSES or current == "cancelled":
            return []
        return ["cancelled"]
    if target not in FULFILLMENT_STATUS_LADDER:
        return []

    current_index = (
        FULFILLMENT_STATUS_LADDER.index(current)
        if current in FULFILLMENT_STATUS_LADDER
        else -1
    )
    target_index = FULFILLMENT_STATUS_LADDER.index(target)
    if target_index <= current_index:
        return []
    return FULFILLMENT_STATUS_LADDER[current_index + 1 : target_index + 1]


class FulfillmentSyncWorker:
    """读取 Odoo 交货单状态并回传 Core 的长驻轮询 worker。

    参数：
        core: Core Marketplace API 客户端（:class:`CoreClient`，列订单）。
        odoo: Odoo Adapter（读交货单状态）。
        dispatcher: 已注册 :class:`ReportFulfillmentTask` 的分派器。
    """

    def __init__(
        self,
        *,
        core: CoreClient,
        odoo: OdooAdapter,
        dispatcher: TaskDispatcher,
        logger: Optional[IntegrationLogger] = None,
    ) -> None:
        self.core = core
        self.odoo = odoo
        self.dispatcher = dispatcher
        self.logger = logger or get_logger("shopstore_integration.fulfillment_worker")

    def run_once(self, *, limit: int = 50) -> int:
        """拉取一批待同步订单并尝试推进，返回本轮尝试同步的订单数。

        每个订单独立处理：单个订单的 Odoo 读取 / 回传失败不阻断整批；回传失败
        由 ``sync_jobs`` 幂等键 + 重试 / 退避承接，下一轮继续。
        """
        request_id = new_request_id()
        orders = self.core.list_orders(limit=limit, offset=0, request_id=request_id)
        processed = 0
        for order in orders:
            if self._process_order(order):
                processed += 1
        return processed

    def run(
        self,
        *,
        interval_seconds: int = 30,
        limit: int = 50,
        once: bool = False,
    ) -> None:
        """长驻轮询循环。``once=True`` 时只执行一轮（测试 / 单次触发用）。"""
        while True:
            try:
                count = self.run_once(limit=limit)
                self.logger.debug("fulfillment poll cycle completed", orders=count)
            except Exception as exc:  # noqa: BLE001
                self.logger.error("fulfillment poll cycle failed", error=str(exc))
            if once:
                return
            time.sleep(interval_seconds)

    def _process_order(self, order: dict[str, Any]) -> bool:
        """处理单个订单，返回是否为待同步候选订单（已尝试处理）。

        非候选（无 ``odoo_sale_order_id`` 或已到履约终态）返回 ``False``；其余
        无论成功推进、尚无进展、还是读取失败（下一轮重试），均返回 ``True``。
        """
        marketplace_order_id = order.get("marketplace_order_id")
        status = order.get("status")
        external_ids = order.get("external_ids") or {}
        odoo_sale_order_id = external_ids.get("odoo_sale_order_id")

        if not marketplace_order_id or odoo_sale_order_id is None:
            return False
        if status not in POLLABLE_STATUSES:
            return False

        request_id = new_request_id()
        try:
            delivery = self.odoo.get_delivery_for_sale_order(
                odoo_sale_order_id, request_id=request_id
            )
        except IntegrationError as exc:
            self.logger.warning(
                "cannot read odoo delivery; will retry next cycle",
                marketplace_order_id=marketplace_order_id,
                odoo_sale_order_id=odoo_sale_order_id,
                error_code=getattr(exc, "code", None),
            )
            return True

        if delivery is None:
            # 销售单尚未确认，无交货单；下一轮再查。
            return True

        odoo_delivery_id = delivery.get("odoo_delivery_id")
        odoo_status = delivery.get("status")
        if odoo_delivery_id is None or not odoo_status:
            self.logger.warning(
                "odoo delivery missing id/status; skipping",
                marketplace_order_id=marketplace_order_id,
            )
            return True

        target = map_delivery_status_to_order_status(odoo_status)
        path = fulfillment_status_path(status, target)
        if not path:
            return True  # 已到达目标或 Odoo 侧尚无进展，无需回传

        for step in path:
            command = report_fulfillment_command(
                marketplace_order_id=marketplace_order_id,
                odoo_delivery_id=odoo_delivery_id,
                odoo_sale_order_id=odoo_sale_order_id,
                odoo_status=step,
                request_id=request_id,
            )
            result: TaskResult = self.dispatcher.dispatch(command)
            self._log_result(marketplace_order_id, step, result)

        return True

    def _log_result(
        self, marketplace_order_id: str, step: str, result: TaskResult
    ) -> None:
        context = {
            "marketplace_order_id": marketplace_order_id,
            "status": step,
            "idempotency_key": result.idempotency_key,
        }
        if result.status == TaskStatus.SUCCESS:
            self.logger.info("fulfillment reported to core", **context)
        elif result.status == TaskStatus.SKIPPED:
            self.logger.info("fulfillment skipped (idempotent)", **context)
        elif result.status == TaskStatus.DEFERRED:
            self.logger.info("fulfillment deferred (backoff)", **context)
        elif result.status == TaskStatus.DEAD:
            self.logger.error("fulfillment dead-lettered; manual retry required", **context)
        else:
            self.logger.error(
                "fulfillment report failed; will retry",
                **context,
                error_code=result.error.code if result.error else None,
            )
