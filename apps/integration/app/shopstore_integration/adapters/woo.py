"""WooCommerce Adapter 接口。

只定义 Integration 与 WooCommerce 交互所需的能力；Core 不依赖本接口之外
的 Woo API 细节。阶段 0 仅接口 + Mock 实现，真实实现后续阶段落地。
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, runtime_checkable


@runtime_checkable
class WooAdapter(Protocol):
    """与 WooCommerce 交互的接口。返回/接收均为 snake_case 字典。"""

    def health_check(self, *, request_id: str) -> bool:
        """探活。"""
        ...

    def get_product(self, sku: str, *, request_id: str) -> Optional[dict[str, Any]]:
        """按 SKU 查询商品，不存在返回 None。"""
        ...

    def upsert_product(self, product: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        """创建/更新商品，返回含 ``woo_product_id`` 的映射。"""
        ...

    def get_order(self, woo_order_id: int, *, request_id: str) -> Optional[dict[str, Any]]:
        """按 Woo 订单 ID 查询订单，不存在返回 None。"""
        ...

    def update_order(self, woo_order_id: int, patch: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        """更新 Woo 订单。"""
        ...


__all__ = ["WooAdapter"]
