"""真实 Odoo Adapter（JSON-RPC over HTTP）。

实现 :class:`OdooAdapter` 接口，通过 Odoo 外部 JSON-RPC API（``/jsonrpc``）
与 Odoo 交互。映射规则遵循 ``apps/odoo/config/MAPPING.md`` 与
``apps/odoo/config/mapping/odoo_mapping.rules.json``（ISSUE-0106）：

- 客户（partner）：``res.partner.ref`` == Core retailer 外部 ID，先查再建；
- SKU（产品）：``product.product.default_code`` == SKU，必须唯一；
- 订单幂等键：``sale.order.client_order_ref`` == ``marketplace_order_id``，
  创建前先查，命中即复用，不重复创建销售单。

Core 领域模块不 import 本模块：Integration 只把 Core 命令翻译为 Odoo API 调用。
"""

from __future__ import annotations

from typing import Any, Optional

from ..errors import (
    PayloadValidationError,
    ResourceNotFoundError,
    UpstreamAuthError,
    UpstreamError,
)
from ..logging import IntegrationLogger
from ..http_client import UnifiedHttpClient
from .base import BaseAdapter

__all__ = ["HttpOdooAdapter"]


def amount_minor_to_float(amount_minor: int, currency: str = "USD") -> float:
    """把契约金额（最小单位整数）转换为 Odoo 价格浮点（边界转换）。

    Odoo 内部以浮点表示价格；契约层禁止浮点金额。指数默认 2（USD/EUR 等），
    JPY 等零指数货币按 0 处理。
    """
    exponent = 0 if currency.upper() == "JPY" else 2
    return amount_minor / (10 ** exponent)


class HttpOdooAdapter(BaseAdapter):
    """通过 Odoo 外部 JSON-RPC API 操作的 Adapter。

    参数：
        base_url: Odoo 根地址（如 ``http://localhost:8069``）。
        db: Odoo 数据库名。
        username / password: Odoo 登录账号（外部 API 用）。
        client: 统一 HTTP 客户端（:class:`UnifiedHttpClient`）。
    """

    name = "odoo"

    def __init__(
        self,
        *,
        base_url: str,
        db: str,
        username: str,
        password: str,
        client: UnifiedHttpClient,
        logger: Optional[IntegrationLogger] = None,
    ) -> None:
        super().__init__(base_url=base_url, client=client, logger=logger)
        self.db = db
        self.username = username
        self.password = password
        self._uid: int | None = None

    # ---- JSON-RPC plumbing ----
    def _rpc(
        self,
        service: str,
        method: str,
        args: list[Any],
        *,
        request_id: str,
        trace_id: Optional[str] = None,
    ) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": service, "method": method, "args": args},
            "id": 1,
        }
        response = self._request(
            "POST",
            "/jsonrpc",
            request_id=request_id,
            trace_id=trace_id,
            json=payload,
        )
        if isinstance(response, dict) and "error" in response:
            err = response["error"]
            message = err.get("message") if isinstance(err, dict) else str(err)
            raise UpstreamError(
                f"odoo rpc error: {message}",
                request_id=request_id,
                trace_id=trace_id,
            )
        if isinstance(response, dict) and "result" in response:
            return response["result"]
        return response

    def _authenticate(self, *, request_id: str) -> int:
        if self._uid is None:
            result = self._rpc(
                "common",
                "authenticate",
                [self.db, self.username, self.password, {}],
                request_id=request_id,
            )
            if not result:
                raise UpstreamAuthError("odoo authentication failed", request_id=request_id)
            self._uid = int(result)
        return self._uid

    def _execute_kw(
        self,
        model: str,
        method: str,
        args: list[Any],
        *,
        request_id: str,
        kwargs: Optional[dict[str, Any]] = None,
    ) -> Any:
        uid = self._authenticate(request_id=request_id)
        return self._rpc(
            "object",
            "execute_kw",
            [self.db, uid, self.password, model, method, args, kwargs or {}],
            request_id=request_id,
        )

    def _search_read(
        self,
        model: str,
        domain: list[Any],
        *,
        request_id: str,
        fields: Optional[list[str]] = None,
        limit: int = 1,
    ) -> list[dict[str, Any]]:
        ids = self._execute_kw(
            model, "search", [domain], request_id=request_id, kwargs={"limit": limit}
        )
        if not ids:
            return []
        return self._execute_kw(
            model, "read", [ids, fields or []], request_id=request_id
        )

    # ---- OdooAdapter ----
    def health_check(self, *, request_id: str) -> bool:
        result = self._rpc("common", "version", [], request_id=request_id)
        return bool(result and isinstance(result, dict) and result.get("server_version"))

    def upsert_product(self, product: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        sku = product["sku"]
        existing = self._search_read(
            "product.product",
            [("default_code", "=", sku)],
            request_id=request_id,
            fields=["id", "default_code", "name"],
        )
        if existing:
            product_id = existing[0]["id"]
        else:
            product_id = self._execute_kw(
                "product.product",
                "create",
                [{"name": product.get("name") or sku, "default_code": sku, "sale_ok": True}],
                request_id=request_id,
            )
        return {"odoo_product_id": product_id, "sku": sku}

    def create_sale_order(self, order: dict[str, Any], *, request_id: str) -> dict[str, Any]:
        marketplace_order_id = order["marketplace_order_id"]
        ref = order.get("retailer_ref") or order.get("retailer_id")
        if not ref:
            raise PayloadValidationError(
                "missing retailer ref to map to odoo partner",
                request_id=request_id,
            )

        # 幂等去重：先按 client_order_ref 查找，命中则复用，不重复创建。
        existing = self._find_sale_order(marketplace_order_id, request_id=request_id)
        if existing is not None:
            return {"odoo_sale_order_id": existing["id"], "created": False}

        partner = self._resolve_or_create_partner(
            ref,
            name=order.get("retailer_name"),
            email=order.get("retailer_email"),
            request_id=request_id,
        )

        order_line: list[Any] = []
        for line in order.get("lines", []):
            product = self._resolve_product(line["sku"], request_id=request_id)
            unit_price = line.get("unit_price") or {}
            order_line.append(
                (
                    0,
                    0,
                    {
                        "product_id": product["id"],
                        "name": product.get("name") or line["sku"],
                        "product_uom_qty": line["quantity"],
                        "price_unit": amount_minor_to_float(
                            unit_price.get("amount_minor", 0),
                            unit_price.get("currency", "USD"),
                        ),
                    },
                )
            )

        so_id = self._execute_kw(
            "sale.order",
            "create",
            [
                {
                    "client_order_ref": marketplace_order_id,
                    "partner_id": partner["id"],
                    "partner_invoice_id": partner["id"],
                    "partner_shipping_id": partner["id"],
                    "order_line": order_line,
                }
            ],
            request_id=request_id,
        )
        return {
            "odoo_sale_order_id": so_id,
            "created": True,
            "odoo_partner_id": partner["id"],
            "odoo_partner_ref": partner["ref"],
        }

    def confirm_sale_order(self, odoo_sale_order_id: int, *, request_id: str) -> dict[str, Any]:
        self._execute_kw(
            "sale.order", "action_confirm", [odoo_sale_order_id], request_id=request_id
        )
        return {"odoo_sale_order_id": odoo_sale_order_id, "status": "confirmed"}

    def get_delivery_status(self, odoo_delivery_id: int, *, request_id: str) -> dict[str, Any]:
        pickings = self._search_read(
            "stock.picking",
            [("id", "=", odoo_delivery_id)],
            request_id=request_id,
            fields=["id", "state", "name"],
        )
        if not pickings:
            raise ResourceNotFoundError(
                f"delivery not found: {odoo_delivery_id}", request_id=request_id
            )
        return {
            "odoo_delivery_id": odoo_delivery_id,
            "status": pickings[0]["state"],
        }

    # ---- mapping helpers ----
    def _find_sale_order(
        self, client_order_ref: str, *, request_id: str
    ) -> Optional[dict[str, Any]]:
        orders = self._search_read(
            "sale.order",
            [("client_order_ref", "=", client_order_ref)],
            request_id=request_id,
            fields=["id", "client_order_ref"],
        )
        return orders[0] if orders else None

    def _resolve_or_create_partner(
        self,
        ref: str,
        *,
        name: Optional[str],
        email: Optional[str],
        request_id: str,
    ) -> dict[str, Any]:
        partners = self._search_read(
            "res.partner",
            [("ref", "=", ref)],
            request_id=request_id,
            fields=["id", "ref", "name", "email"],
        )
        if partners:
            return partners[0]
        partner_id = self._execute_kw(
            "res.partner",
            "create",
            [
                {
                    "name": name or ref,
                    "ref": ref,
                    "company_type": "company",
                    "customer_rank": 1,
                    "email": email or "",
                }
            ],
            request_id=request_id,
        )
        return {"id": partner_id, "ref": ref, "name": name, "email": email}

    def _resolve_product(self, sku: str, *, request_id: str) -> dict[str, Any]:
        products = self._search_read(
            "product.product",
            [("default_code", "=", sku)],
            request_id=request_id,
            fields=["id", "default_code", "name"],
        )
        if not products:
            raise ResourceNotFoundError(
                f"sku not found in odoo: {sku}", request_id=request_id
            )
        return products[0]
