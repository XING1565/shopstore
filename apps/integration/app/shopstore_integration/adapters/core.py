"""Core Adapter 接口与实现。

Integration 反向调用 Core 的能力（写回投影 / 履约状态）。Core 是订单主权系统，
Integration 通过本接口把 Odoo 侧读到的履约状态回传 Core，由 Core 的订单状态机
负责推进与防倒退校验。返回/接收均为 snake_case 字典。
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable

from .base import BaseAdapter

__all__ = ["CoreAdapter", "HttpCoreAdapter"]

_OPERATOR_HEADERS = {"X-Actor-Role": "operator"}


@runtime_checkable
class CoreAdapter(Protocol):
    """与 Core 交互的接口（Integration -> Core 反向调用）。"""

    def health_check(self, *, request_id: str) -> bool:
        """探活。"""
        ...

    def report_fulfillment(
        self,
        marketplace_order_id: str,
        *,
        status: str,
        odoo_delivery_id: Optional[int] = None,
        odoo_sale_order_id: Optional[int] = None,
        request_id: str,
        trace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """回传履约状态，返回 Core 订单视图（含 ``marketplace_order_id`` / ``status``）。"""
        ...


class HttpCoreAdapter(BaseAdapter):
    """真实 Core Adapter：走统一 HTTP 管道调用 Core 的履约回传端点。

    以运营（operator）身份调用 Core（阶段 1 无独立 IAM，见 Core ``deps.py``）。
    """

    name = "core"

    def health_check(self, *, request_id: str) -> bool:
        self._request("GET", "/api/v1/health", request_id=request_id)
        return True

    def report_fulfillment(
        self,
        marketplace_order_id: str,
        *,
        status: str,
        odoo_delivery_id: Optional[int] = None,
        odoo_sale_order_id: Optional[int] = None,
        request_id: str,
        trace_id: Optional[str] = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"status": status}
        if odoo_delivery_id is not None:
            payload["odoo_delivery_id"] = odoo_delivery_id
        if odoo_sale_order_id is not None:
            payload["odoo_sale_order_id"] = odoo_sale_order_id
        return self._request(
            "POST",
            f"/api/v1/orders/{marketplace_order_id}/fulfillment",
            request_id=request_id,
            trace_id=trace_id,
            json=payload,
            headers=_OPERATOR_HEADERS,
        )
