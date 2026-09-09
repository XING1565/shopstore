"""测试 Mock Adapter。

实现 :class:`WooAdapter` 与 :class:`OdooAdapter` 两个接口，返回确定性结果，
用于阶段 0 验证链路 ``Core Command -> Integration Task -> Adapter -> Mock Result``。

可配置注入延迟与错误（如超时），用于验证「超时和异常可以被捕获」。
"""

from __future__ import annotations

import itertools
import time
from typing import Any, Optional

from ..errors import IntegrationError
from .odoo import OdooAdapter
from .woo import WooAdapter


class MockAdapter:
    """实现 Woo / Odoo 两个接口的测试替身。

    参数：
        name: 系统名（``woo`` 或 ``odoo``），影响返回的 ID 字段名。
        latency_seconds: 每次调用前的模拟延迟。
        fail_with: 要抛出的 :class:`IntegrationError`（用于模拟超时/上游错误）。
        fail_count: 连续失败次数，超过后恢复正常（默认 1）。
    """

    def __init__(
        self,
        name: str,
        *,
        latency_seconds: float = 0.0,
        fail_with: Optional[IntegrationError] = None,
        fail_count: int = 1,
    ) -> None:
        self.name = name
        self.latency_seconds = latency_seconds
        self.fail_with = fail_with
        self._fail_remaining = fail_count
        self._id_counter = itertools.count(1)
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def _record(self, method: str, *args: Any) -> None:
        self.calls.append((method, args))

    def _maybe_fail(self, request_id: str) -> None:
        if self.fail_with is not None and self._fail_remaining > 0:
            self._fail_remaining -= 1
            error = self.fail_with
            raise error.__class__(
                error.message,
                request_id=request_id,
                cause=error.cause,
            )

    def _maybe_latency(self) -> None:
        if self.latency_seconds > 0:
            time.sleep(self.latency_seconds)

    def _next_id(self) -> int:
        return next(self._id_counter)

    def _id_field(self) -> str:
        return "woo_product_id" if self.name == "woo" else "odoo_product_id"

    # ---- WooAdapter ----
    def health_check(self, *, request_id: str) -> bool:
        self._record("health_check")
        self._maybe_latency()
        self._maybe_fail(request_id)
        return True

    def get_product(self, sku: str, *, request_id: str) -> Optional[dict[str, Any]]:
        self._record("get_product", sku)
        self._maybe_latency()
        self._maybe_fail(request_id)
        return None

    def upsert_product(self, product: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        self._record("upsert_product", product)
        self._maybe_latency()
        self._maybe_fail(request_id)
        return {self._id_field(): self._next_id(), "sku": product.get("sku")}

    def get_order(self, woo_order_id: int, *, request_id: str) -> Optional[dict[str, Any]]:
        self._record("get_order", woo_order_id)
        self._maybe_latency()
        self._maybe_fail(request_id)
        return None

    def update_order(self, woo_order_id: int, patch: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        self._record("update_order", woo_order_id, patch)
        self._maybe_latency()
        self._maybe_fail(request_id)
        return {"woo_order_id": woo_order_id, **patch}

    # ---- OdooAdapter ----
    def create_sale_order(self, order: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        self._record("create_sale_order", order)
        self._maybe_latency()
        self._maybe_fail(request_id)
        return {"odoo_sale_order_id": self._next_id()}

    def confirm_sale_order(self, odoo_sale_order_id: int, *, request_id: str) -> dict[str, Any]:
        self._record("confirm_sale_order", odoo_sale_order_id)
        self._maybe_latency()
        self._maybe_fail(request_id)
        return {"odoo_sale_order_id": odoo_sale_order_id, "status": "confirmed"}

    def get_delivery_status(self, odoo_delivery_id: int, *, request_id: str) -> dict[str, Any]:
        self._record("get_delivery_status", odoo_delivery_id)
        self._maybe_latency()
        self._maybe_fail(request_id)
        return {"odoo_delivery_id": odoo_delivery_id, "status": "picking_ready"}


__all__ = ["MockAdapter"]
