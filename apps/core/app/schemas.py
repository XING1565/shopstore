"""响应 / 请求数据模型（与 packages/contracts 契约保持一致）。

时间字段在 API 层一律以 RFC 3339 UTC 字符串（``Z`` 结尾）返回，见
``packages/contracts/schemas/timestamp.schema.json``；金额用最小单位整数
（``amount_minor`` + ``currency``），见 ``money.schema.json``。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "HealthCheck",
    "Health",
    "ErrorDetail",
    "ErrorBody",
    "ErrorEnvelope",
    "Money",
    "ProductExternalIds",
    "OrderExternalIds",
    "RetailerCreate",
    "RetailerReview",
    "RetailerExternalIdWriteback",
    "RetailerView",
    "RetailerList",
    "ProductCreate",
    "ProductUpdate",
    "ProductView",
    "ProductList",
    "OrderCreate",
    "OrderLineCreate",
    "OrderLineView",
    "OrderView",
    "OrderList",
    "OrderFulfillmentUpdate",
    "OrderExternalIdWriteback",
    "DomainEventView",
    "DomainEventList",
    "to_utc_iso",
]

RetailerStatusLiteral = Literal["pending", "approved", "rejected", "suspended"]
ProductStatusLiteral = Literal["draft", "published", "archived"]
OrderStatusLiteral = Literal[
    "draft",
    "submitted",
    "sent_to_odoo",
    "odoo_confirmed",
    "inventory_reserved",
    "picking_ready",
    "shipped",
    "completed",
    "cancelled",
    "sync_failed",
]


def to_utc_iso(dt: datetime | None) -> str | None:
    """将时间戳规范化为 RFC 3339 UTC（``Z`` 结尾）。SQLite 读出的 naive 时间按 UTC 处理。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class HealthCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded", "down"]
    latency_ms: int | None = None


class Health(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok", "degraded", "down"]
    checks: dict[str, HealthCheck] = Field(default_factory=dict)


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    reason: str


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: list[ErrorDetail] | None = None
    request_id: str | None = None


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorBody


class Money(BaseModel):
    """统一金额格式（money.schema.json）。禁止浮点数。"""

    model_config = ConfigDict(extra="forbid")

    amount_minor: int
    currency: str = Field(pattern=r"^[A-Z]{3}$", default="USD")


class ProductExternalIds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    woo_product_id: int | None = None
    odoo_product_id: int | None = None


class OrderExternalIds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    woo_order_id: int | None = None
    odoo_sale_order_id: int | None = None
    odoo_delivery_id: int | None = None


class RetailerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    company_name: str = Field(min_length=1, max_length=255)
    contact_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)


class RetailerReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=2000)


class RetailerExternalIdWriteback(BaseModel):
    """Integration 写回买家 Odoo partner 外部 ID 映射的请求体（至少提供一项）。"""

    model_config = ConfigDict(extra="forbid")

    odoo_partner_ref: str | None = Field(default=None, max_length=64)
    odoo_partner_id: int | None = None


class RetailerList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list["RetailerView"]
    total: int
    limit: int
    offset: int


class RetailerView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retailer_id: str
    email: str
    company_name: str
    contact_name: str | None = None
    phone: str | None = None
    odoo_partner_ref: str | None = None
    odoo_partner_id: int | None = None
    status: RetailerStatusLiteral
    reviewed_by: str | None = None
    reviewed_at: str | None = None
    review_note: str | None = None
    created_at: str
    updated_at: str


class ProductCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]{1,62}[A-Z0-9]$")
    name: str = Field(min_length=1, max_length=255)
    brand_id: str
    wholesale_price: Money
    moq: int = Field(ge=1)


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=255)
    brand_id: str | None = None
    wholesale_price: Money | None = None
    moq: int | None = Field(default=None, ge=1)


class ProductView(BaseModel):
    """商品视图。

    ``wholesale_price`` / ``moq`` 仅在查看者为运营或已认证（approved）买家时返回，
    其余场景为 ``None``（未认证买家不可见完整批发价与 MOQ）。
    """

    model_config = ConfigDict(extra="forbid")

    product_id: str
    sku: str
    name: str
    brand_id: str
    wholesale_price: Money | None = None
    moq: int | None = None
    status: ProductStatusLiteral
    external_ids: ProductExternalIds
    created_at: str
    updated_at: str


class ProductList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ProductView]
    total: int
    limit: int
    offset: int


class OrderLineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]{1,62}[A-Z0-9]$")
    quantity: int = Field(ge=1)


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lines: list[OrderLineCreate] = Field(min_length=1)
    woo_order_id: int | None = None


class OrderLineView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str
    quantity: int
    unit_price: Money


class OrderView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    marketplace_order_id: str
    retailer_id: str
    status: OrderStatusLiteral
    lines: list[OrderLineView]
    total: Money
    external_ids: OrderExternalIds
    created_at: str
    updated_at: str


class OrderList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OrderView]
    total: int
    limit: int
    offset: int


class OrderFulfillmentUpdate(BaseModel):
    """履约状态回传（Integration -> Core）。

    ``status`` 为 Integration 将 Odoo 交货单状态映射后的目标订单状态
    （Core 按订单状态机推进，非法 / 倒退迁移由 Core 拒绝）。
    """

    model_config = ConfigDict(extra="forbid")

    status: OrderStatusLiteral
    odoo_delivery_id: int | None = None
    odoo_sale_order_id: int | None = None


class OrderExternalIdWriteback(BaseModel):
    """Integration 写回订单外部 ID 映射的请求体（至少提供一项）。"""

    model_config = ConfigDict(extra="forbid")

    odoo_sale_order_id: int | None = None
    woo_order_id: int | None = None
    odoo_delivery_id: int | None = None


class DomainEventView(BaseModel):
    """领域事件 outbox 条目视图（供 Integration 轮询）。"""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: str
    event_version: str
    source: str
    occurred_at: str
    trace_id: str
    request_id: str | None = None
    data: dict


class DomainEventList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DomainEventView]
    total: int
    limit: int
