"""领域事件发布。

Core 只发布领域命令 / 领域事件，不 import Woo / Odoo Adapter 细节。
事件以 outbox 模式持久化到 ``domain_events`` 表（``OutboxEvent``），
由 Integration 层（ISSUE-0107 / ISSUE-0104 等）轮询消费并写回投影。

事件类型命名遵循 ``{domain}.{entity}.{past_tense_verb}``：
- ``identity.retailer.registered / approved / rejected``
- ``catalog.product.created / updated / published / archived``
- ``commerce.order.created``
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.outbox import OutboxEvent

from ..models.base import new_uuid, utcnow

__all__ = [
    "EventType",
    "publish_event",
    "product_event_data",
]


class EventType:
    """领域事件类型常量（三段点分隔，见 envelope.schema.json）。"""

    RETAILER_REGISTERED = "identity.retailer.registered"
    RETAILER_APPROVED = "identity.retailer.approved"
    RETAILER_REJECTED = "identity.retailer.rejected"

    PRODUCT_CREATED = "catalog.product.created"
    PRODUCT_UPDATED = "catalog.product.updated"
    PRODUCT_PUBLISHED = "catalog.product.published"
    PRODUCT_ARCHIVED = "catalog.product.archived"

    ORDER_CREATED = "commerce.order.created"


def publish_event(
    session: Session,
    event_type: str,
    data: dict,
    *,
    request_id: str | None = None,
    trace_id: str | None = None,
    event_version: str = "1",
) -> OutboxEvent:
    """发布一条领域事件到 outbox（与业务写操作同事务，由调用方 commit）。

    ``data`` 形状遵循对应事件 schema；此处不校验内容，只保证信封完整。
    """
    event = OutboxEvent(
        event_type=event_type,
        event_version=event_version,
        source="core",
        trace_id=trace_id or new_uuid(),
        request_id=request_id,
        occurred_at=utcnow(),
        data=data,
    )
    session.add(event)
    return event


def product_event_data(product, *, include_external_ids: bool = False) -> dict:
    """构造 ``product-events.schema.json`` 的 ``ProductEventData`` 快照。

    批发价 / MOQ 是 Core 真相，随事件携带，供 Integration 提取投影字段。
    """
    from app.models.product import Product  # local import to avoid cycle

    assert isinstance(product, Product)
    data = {
        "product_id": product.id,
        "sku": product.sku,
        "name": product.name,
        "brand_id": product.brand_id,
        "wholesale_price": {
            "amount_minor": product.wholesale_price_minor,
            "currency": product.wholesale_price_currency,
        },
        "moq": product.moq,
        "status": product.status.value,
    }
    external_ids = {}
    if include_external_ids or product.woo_product_id is not None:
        external_ids["woo_product_id"] = product.woo_product_id
    if include_external_ids or product.odoo_product_id is not None:
        external_ids["odoo_product_id"] = product.odoo_product_id
    if external_ids:
        data["external_ids"] = external_ids
    return data
