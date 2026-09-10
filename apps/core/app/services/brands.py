"""品牌（Brand）服务：创建、查询、更新、删除。

品牌是商品（Product）的归属，``brand_id`` 是产品创建的前置依赖。阶段一由运营
代维护（对应数据模型注释），后续 Vendor Portal 自助。
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.errors import AppError
from app.models import Brand, Product
from app.models.enums import BrandStatus
from app.schemas import BrandCreate, BrandUpdate

__all__ = [
    "create_brand",
    "get_brand",
    "list_brands",
    "update_brand",
    "delete_brand",
]


def _name_conflict(session: Session, name: str, *, exclude_id: str | None = None) -> bool:
    query = session.query(Brand).filter(Brand.name == name)
    if exclude_id is not None:
        query = query.filter(Brand.id != exclude_id)
    return query.first() is not None


def create_brand(session: Session, payload: BrandCreate) -> Brand:
    if _name_conflict(session, payload.name):
        raise AppError(409, "conflict", "品牌名称已存在")

    brand = Brand(
        name=payload.name,
        description=payload.description,
        logo_url=payload.logo_url,
    )
    session.add(brand)
    session.commit()
    return brand


def get_brand(session: Session, brand_id: str) -> Brand:
    brand = session.get(Brand, brand_id)
    if brand is None:
        raise AppError(404, "not_found", "品牌不存在")
    return brand


def list_brands(
    session: Session,
    *,
    limit: int,
    offset: int,
) -> tuple[list[Brand], int]:
    total = session.query(Brand).count()
    rows = (
        session.query(Brand)
        .order_by(Brand.created_at.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return rows, total


def update_brand(
    session: Session,
    brand_id: str,
    payload: BrandUpdate,
) -> Brand:
    brand = get_brand(session, brand_id)
    fields = payload.model_fields_set

    if "name" in fields:
        if payload.name is None:
            raise AppError(422, "validation_error", "品牌名称不能为空")
        if _name_conflict(session, payload.name, exclude_id=brand_id):
            raise AppError(409, "conflict", "品牌名称已存在")
        brand.name = payload.name
    if "description" in fields:
        brand.description = payload.description
    if "logo_url" in fields:
        brand.logo_url = payload.logo_url
    if "status" in fields:
        brand.status = BrandStatus(payload.status)

    session.commit()
    return brand


def delete_brand(session: Session, brand_id: str) -> None:
    brand = get_brand(session, brand_id)

    has_products = (
        session.query(Product).filter(Product.brand_id == brand_id).first() is not None
    )
    if has_products:
        raise AppError(
            409,
            "conflict",
            "品牌下存在商品，无法删除；请先下架或改绑其商品",
        )

    session.delete(brand)
    session.commit()
