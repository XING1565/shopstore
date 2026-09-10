"""领域对象 → API 视图（DTO）序列化。"""

from __future__ import annotations

from app.models import Order, Product, Retailer
from app.schemas import (
    Money,
    OrderExternalIds,
    OrderLineView,
    OrderView,
    ProductExternalIds,
    ProductView,
    RetailerView,
    to_utc_iso,
)

__all__ = [
    "retailer_to_view",
    "product_to_view",
    "order_to_view",
]


def retailer_to_view(r: Retailer) -> RetailerView:
    return RetailerView(
        retailer_id=r.id,
        email=r.email,
        company_name=r.company_name,
        contact_name=r.contact_name,
        phone=r.phone,
        odoo_partner_ref=r.odoo_partner_ref,
        odoo_partner_id=r.odoo_partner_id,
        status=r.status.value,
        reviewed_by=r.reviewed_by,
        reviewed_at=to_utc_iso(r.reviewed_at),
        review_note=r.review_note,
        created_at=to_utc_iso(r.created_at),
        updated_at=to_utc_iso(r.updated_at),
    )


def product_to_view(p: Product, *, with_pricing: bool) -> ProductView:
    price = None
    moq = None
    if with_pricing:
        price = Money(
            amount_minor=p.wholesale_price_minor,
            currency=p.wholesale_price_currency,
        )
        moq = p.moq
    return ProductView(
        product_id=p.id,
        sku=p.sku,
        name=p.name,
        brand_id=p.brand_id,
        wholesale_price=price,
        moq=moq,
        status=p.status.value,
        external_ids=ProductExternalIds(
            woo_product_id=p.woo_product_id,
            odoo_product_id=p.odoo_product_id,
        ),
        created_at=to_utc_iso(p.created_at),
        updated_at=to_utc_iso(p.updated_at),
    )


def order_to_view(o: Order) -> OrderView:
    lines = [
        OrderLineView(
            sku=line.sku,
            quantity=line.quantity,
            unit_price=Money(
                amount_minor=line.unit_price_minor,
                currency=line.unit_price_currency,
            ),
        )
        for line in o.lines
    ]
    total_minor = sum(line.unit_price_minor * line.quantity for line in o.lines)
    return OrderView(
        marketplace_order_id=o.id,
        retailer_id=o.retailer_id,
        status=o.status.value,
        lines=lines,
        total=Money(amount_minor=total_minor, currency=o.currency),
        external_ids=OrderExternalIds(
            woo_order_id=o.woo_order_id,
            odoo_sale_order_id=o.odoo_sale_order_id,
            odoo_delivery_id=o.odoo_delivery_id,
        ),
        created_at=to_utc_iso(o.created_at),
        updated_at=to_utc_iso(o.updated_at),
    )
