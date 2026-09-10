"""订单（Order）服务：无支付下单（MOQ 校验）、查询。"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.events import EventType, publish_event
from app.errors import AppError
from app.models import Order, OrderLine, Product, Retailer
from app.models.enums import OrderStatus, ProductStatus
from app.schemas import ErrorDetail, OrderCreate

__all__ = [
    "place_order",
    "get_order",
    "list_orders",
]


def _order_event_data(order: Order) -> dict:
    lines = [
        {
            "sku": line.sku,
            "quantity": line.quantity,
            "unit_price": {
                "amount_minor": line.unit_price_minor,
                "currency": line.unit_price_currency,
            },
        }
        for line in order.lines
    ]
    total_minor = sum(line.unit_price_minor * line.quantity for line in order.lines)
    return {
        "marketplace_order_id": order.id,
        "retailer_id": order.retailer_id,
        "status": order.status.value,
        "lines": lines,
        "total": {"amount_minor": total_minor, "currency": order.currency},
        "external_ids": {},
    }


def place_order(
    session: Session,
    retailer: Retailer,
    payload: OrderCreate,
    *,
    request_id: str | None = None,
) -> Order:
    """按 MOQ 校验数量，通过则创建 Marketplace 订单（状态 Submitted）。

    低于 MOQ 直接拒绝并提示原因；数量以商品 MOQ 为准。
    """
    lines: list[OrderLine] = []
    currency = None
    for item in payload.lines:
        product = session.query(Product).filter(Product.sku == item.sku).first()
        if product is None:
            raise AppError(
                400,
                "bad_request",
                f"SKU 不存在：{item.sku}",
                details=[ErrorDetail(field="lines", reason=f"sku {item.sku} 不存在")],
            )
        if product.status is not ProductStatus.published:
            raise AppError(
                409,
                "conflict",
                f"商品未发布，不能下单：{item.sku}",
                details=[
                    ErrorDetail(field="lines", reason=f"{item.sku} 状态为 {product.status.value}")
                ],
            )
        if item.quantity < product.moq:
            raise AppError(
                422,
                "moq_not_met",
                "下单数量低于最小起订量",
                details=[
                    ErrorDetail(
                        field="lines",
                        reason=(
                            f"{item.sku} 下单数量 {item.quantity} 低于 MOQ {product.moq}"
                        ),
                    )
                ],
            )
        if currency is None:
            currency = product.wholesale_price_currency
        elif currency != product.wholesale_price_currency:
            raise AppError(
                400,
                "bad_request",
                "同一订单不支持多币种商品",
                details=[
                    ErrorDetail(
                        field="lines",
                        reason=f"{item.sku} 货币 {product.wholesale_price_currency} 与订单货币 {currency} 不一致",
                    )
                ],
            )
        lines.append(
            OrderLine(
                sku=item.sku,
                quantity=item.quantity,
                unit_price_minor=product.wholesale_price_minor,
                unit_price_currency=product.wholesale_price_currency,
            )
        )

    order = Order(retailer_id=retailer.id, currency=currency or "USD")
    order.lines.extend(lines)
    session.add(order)
    session.flush()
    order.transition_to(OrderStatus.submitted, reason="checkout", actor=retailer.id)
    publish_event(
        session,
        EventType.ORDER_CREATED,
        _order_event_data(order),
        request_id=request_id,
    )
    session.commit()
    return order


def get_order(session: Session, order_id: str) -> Order:
    order = session.get(Order, order_id)
    if order is None:
        raise AppError(404, "not_found", "订单不存在")
    return order


def list_orders(
    session: Session,
    *,
    retailer_id: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Order], int]:
    query = session.query(Order)
    if retailer_id is not None:
        query = query.filter(Order.retailer_id == retailer_id)
    total = query.count()
    rows = query.order_by(Order.created_at.desc()).offset(offset).limit(limit).all()
    return rows, total
