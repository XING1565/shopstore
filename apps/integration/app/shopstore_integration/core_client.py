"""Core HTTP 客户端（供 Integration 调用 Core API）。

Integration 通过 Core 的 HTTP API 与 Core 交互，不直接访问 Core 数据库：

- 轮询待消费领域事件（``GET /api/v1/events``）；
- 确认事件已消费（``POST /api/v1/events/{id}/ack``）；
- 写回订单外部 ID（``POST /api/v1/orders/{id}/external-ids``）；
- 读取买家档案（``GET /api/v1/retailers/{id}``，用于映射 Odoo partner）。

身份沿用 Core 阶段 1 的轻量 header 模型（``X-Actor-Role: operator``）。
"""

from __future__ import annotations

from typing import Any, Optional
from urllib.parse import urlencode

from .http_client import UnifiedHttpClient
from .logging import IntegrationLogger, get_logger

__all__ = ["CoreClient"]


class CoreClient:
    """Core Marketplace API 的轻量客户端。"""

    def __init__(
        self,
        *,
        base_url: str,
        client: UnifiedHttpClient,
        operator_name: str = "integration",
        logger: Optional[IntegrationLogger] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.operator_name = operator_name
        self.logger = logger or get_logger("shopstore_integration.core_client")

    def _headers(self) -> dict[str, str]:
        return {"X-Actor-Role": "operator", "X-Operator-Name": self.operator_name}

    def _get(self, path: str, *, request_id: str, params: Optional[dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        return self.client.request(
            "GET", url, request_id=request_id, headers=self._headers()
        )

    def _post(self, path: str, *, request_id: str, json: Optional[Any] = None) -> Any:
        return self.client.request(
            "POST",
            f"{self.base_url}{path}",
            request_id=request_id,
            json=json,
            headers=self._headers(),
        )

    def list_pending_events(
        self,
        *,
        event_type: str,
        limit: int = 50,
        request_id: str,
    ) -> list[dict[str, Any]]:
        body = self._get(
            "/api/v1/events",
            request_id=request_id,
            params={"event_type": event_type, "limit": limit},
        )
        return (body or {}).get("items", [])

    def ack_event(self, event_id: str, *, request_id: str) -> None:
        self._post(f"/api/v1/events/{event_id}/ack", request_id=request_id)

    def record_odoo_sale_order(
        self,
        order_id: str,
        odoo_sale_order_id: int,
        *,
        request_id: str,
    ) -> dict[str, Any]:
        return self._post(
            f"/api/v1/orders/{order_id}/external-ids",
            request_id=request_id,
            json={"odoo_sale_order_id": odoo_sale_order_id},
        )

    def get_retailer(self, retailer_id: str, *, request_id: str) -> dict[str, Any]:
        return self._get(f"/api/v1/retailers/{retailer_id}", request_id=request_id)

    def record_odoo_partner(
        self,
        retailer_id: str,
        *,
        odoo_partner_ref: Optional[str] = None,
        odoo_partner_id: Optional[int] = None,
        request_id: str,
    ) -> dict[str, Any]:
        return self._post(
            f"/api/v1/retailers/{retailer_id}/external-ids",
            request_id=request_id,
            json={
                "odoo_partner_ref": odoo_partner_ref,
                "odoo_partner_id": odoo_partner_id,
            },
        )

    def get_order(self, order_id: str, *, request_id: str) -> dict[str, Any]:
        return self._get(f"/api/v1/orders/{order_id}", request_id=request_id)
