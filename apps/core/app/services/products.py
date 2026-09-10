"""商品（Product）服务：创建、查询、更新、发布、下架。

批发价 / MOQ 是 Core 真相；投影由 Integration 依据领域事件写入 Woo / Odoo。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domain.events import EventType, product_event_data, publish_event
from app.errors import AppError
from app.models import Brand, Product
from app.models.enums import ProductStatus
from app.models.state_machine import InvalidStateTransitionError
from app.schemas import ProductCreate, ProductUpdate

__all__ = [
    "create_product",
    "get_product",
    "list_products",
    "update_product",
    "publish_product",
    "archive_product",
]


def create_product(
    session: Session,
    payload: ProductCreate,
    *,
    request_id: str | None = None,
) -> Product:
    if session.query(Product).filter(Product.sku == payload.sku).first() is not None:
        raise AppError(409, "conflict", "SKU 已存在")
    brand = session.get(Brand, payload.brand_id)
    if brand is None:
        raise AppError(400, "bad_request", "品牌不存在")

    product = Product(
        sku=payload.sku,
        name=payload.name,
        brand_id=payload.brand_id,
        wholesale_price_minor=payload.wholesale_price.amount_minor,
        wholesale_price_currency=payload.wholesale_price.currency,
        moq=payload.moq,
    )
    session.add(product)
    session.flush()
    publish_event(
        session,
        EventType.PRODUCT_CREATED,
        product_event_data(product),
        request_id=request_id,
    )
    session.commit()
    return product


def get_product(session: Session, product_id: str) -> Product:
    product = session.get(Product, product_id)
    if product is None:
        raise AppError(404, "not_found", "商品不存在")
    return product


def list_products(
    session: Session,
    *,
    limit: int,
    offset: int,
) -> tuple[list[Product], int]:
    total = session.query(Product).count()
    rows = (
        session.query(Product)
        .order_by(Product.created_at.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return rows, total


def update_product(
    session: Session,
    product_id: str,
    payload: ProductUpdate,
    *,
    request_id: str | None = None,
) -> Product:
    product = get_product(session, product_id)

    if payload.brand_id is not None:
        brand = session.get(Brand, payload.brand_id)
        if brand is None:
            raise AppError(400, "bad_request", "品牌不存在")
        product.brand_id = payload.brand_id
    if payload.name is not None:
        product.name = payload.name
    if payload.wholesale_price is not None:
        product.wholesale_price_minor = payload.wholesale_price.amount_minor
        product.wholesale_price_currency = payload.wholesale_price.currency
    if payload.moq is not None:
        product.moq = payload.moq

    publish_event(
        session,
        EventType.PRODUCT_UPDATED,
        product_event_data(product),
        request_id=request_id,
    )
    session.commit()
    return product


def publish_product(
    session: Session,
    product_id: str,
    *,
    request_id: str | None = None,
) -> Product:
    product = get_product(session, product_id)
    try:
        product.transition_to(ProductStatus.published)
    except InvalidStateTransitionError as exc:
        raise AppError(409, "conflict", f"商品状态迁移被拒绝：{exc}") from exc

    publish_event(
        session,
        EventType.PRODUCT_PUBLISHED,
        product_event_data(product),
        request_id=request_id,
    )
    session.commit()
    return product


def archive_product(
    session: Session,
    product_id: str,
    *,
    request_id: str | None = None,
) -> Product:
    product = get_product(session, product_id)
    try:
        product.transition_to(ProductStatus.archived)
    except InvalidStateTransitionError as exc:
        raise AppError(409, "conflict", f"商品状态迁移被拒绝：{exc}") from exc

    publish_event(
        session,
        EventType.PRODUCT_ARCHIVED,
        {"product_id": product.id, "sku": product.sku},
        request_id=request_id,
    )
    session.commit()
    return product
