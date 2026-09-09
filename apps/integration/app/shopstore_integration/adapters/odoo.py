"""Odoo Adapter 接口。

定义 Integration 与 Odoo 交互所需的能力。Core 通过此接口（而非 Odoo 原生
API 细节）完成 ERP 侧投影。阶段 0 仅接口 + Mock 实现，真实实现后续阶段落地。
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class OdooAdapter(Protocol):
    """与 Odoo 交互的接口。返回/接收均为 snake_case 字典。"""

    def health_check(self, *, request_id: str) -> bool:
        """探活。"""
        ...

    def upsert_product(self, product: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        """创建/更新产品，返回含 ``odoo_product_id`` 的映射。"""
        ...

    def create_sale_order(self, order: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        """创建销售单，返回含 ``odoo_sale_order_id`` 的映射。"""
        ...

    def confirm_sale_order(self, odoo_sale_order_id: int, *, request_id: str) -> dict[str, Any]:
        """确认销售单。"""
        ...

    def get_delivery_status(self, odoo_delivery_id: int, *, request_id: str) -> dict[str, Any]:
        """查询交货单状态，返回含 ``status`` 的映射。"""
        ...


__all__ = ["OdooAdapter"]
