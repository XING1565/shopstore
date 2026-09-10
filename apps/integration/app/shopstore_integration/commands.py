"""Core 命令（Command）封装。

Core 领域模块通过发布命令与 Integration 交互，而不是直接调用 Woo / Odoo API。
命令携带 ``trace_id`` / ``request_id`` / ``idempotency_key`` 与负载，
Integration 按 ``command_type`` 分派到对应的同步任务（:class:`SyncTask`）。

命令命名约定对齐契约：``{domain}.{entity}.{action}``，例如
``catalog.product.publish``、``commerce.order.export``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import uuid4

from .idempotency import IdempotencyKey


@dataclass(frozen=True)
class Command:
    """Integration 消费的命令。Core 只构造该结构，不携带任何 Odoo API 细节。"""

    command_type: str
    idempotency_key: IdempotencyKey
    payload: dict[str, Any]
    trace_id: str
    request_id: Optional[str] = None

    @property
    def idempotency_key_value(self) -> str:
        return self.idempotency_key.value


def new_trace_id() -> str:
    """生成一次跨系统业务流转的 trace_id（UUID v4）。"""
    return str(uuid4())


def new_request_id() -> str:
    """生成单次请求的 request_id（UUID v4，对应 X-Request-Id）。"""
    return str(uuid4())


def publish_product_command(
    *,
    sku: str,
    name: str,
    amount_minor: int,
    currency: str = "USD",
    trace_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Command:
    """构造「发布商品到 Woo / Odoo」命令（阶段 0 Mock 链路示例）。"""
    return Command(
        command_type="catalog.product.publish",
        idempotency_key=IdempotencyKey(
            scope="core", entity="product", action="publish", source_id=sku
        ),
        payload={
            "sku": sku,
            "name": name,
            "price": {"amount_minor": amount_minor, "currency": currency},
        },
        trace_id=trace_id or new_trace_id(),
        request_id=request_id,
    )


def export_order_command(
    *,
    marketplace_order_id: str,
    lines: list[dict[str, Any]],
    retailer_ref: Optional[str] = None,
    retailer_name: Optional[str] = None,
    retailer_email: Optional[str] = None,
    trace_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Command:
    """构造「导出 Core 订单到 Odoo 销售单」命令。

    ``retailer_ref`` 是 Core 买家映射到 Odoo partner 的稳定业务键（``res.partner.ref``）；
    ``retailer_name`` / ``retailer_email`` 用于 partner 缺失时按映射规则创建。
    """
    payload: dict[str, Any] = {
        "marketplace_order_id": marketplace_order_id,
        "lines": lines,
    }
    if retailer_ref:
        payload["retailer_ref"] = retailer_ref
    if retailer_name:
        payload["retailer_name"] = retailer_name
    if retailer_email:
        payload["retailer_email"] = retailer_email
    return Command(
        command_type="commerce.order.export",
        idempotency_key=IdempotencyKey(
            scope="core", entity="order", action="export", source_id=marketplace_order_id
        ),
        payload=payload,
        trace_id=trace_id or new_trace_id(),
        request_id=request_id,
    )


__all__ = [
    "Command",
    "new_trace_id",
    "new_request_id",
    "publish_product_command",
    "export_order_command",
]
