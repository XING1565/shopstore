"""品牌（Brand）API：创建 / 查询 / 更新 / 删除。

品牌是商品归属（``brand_id``），由运营代维护。删除仅允许在品牌下无商品时进行，
否则返回 409，避免破坏商品外键引用。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import (
    PrincipalDep,
    SessionDep,
    require_operator,
)
from app.schemas import (
    BrandCreate,
    BrandList,
    BrandUpdate,
    BrandView,
)
from app.services import brands as brand_service
from app.services.serializers import brand_to_view

router = APIRouter(tags=["brands"])


@router.get(
    "/brands",
    response_model=BrandList,
    response_model_exclude_none=True,
    summary="分页列出品牌",
    operation_id="listBrands",
)
def list_brands(
    session: SessionDep,
    principal: PrincipalDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BrandList:
    require_operator(principal)
    rows, total = brand_service.list_brands(session, limit=limit, offset=offset)
    return BrandList(
        items=[brand_to_view(b) for b in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/brands",
    response_model=BrandView,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
    summary="创建品牌（运营）",
    operation_id="createBrand",
)
def create_brand(
    payload: BrandCreate,
    session: SessionDep,
    principal: PrincipalDep,
) -> BrandView:
    require_operator(principal)
    brand = brand_service.create_brand(session, payload)
    return brand_to_view(brand)


@router.get(
    "/brands/{brand_id}",
    response_model=BrandView,
    response_model_exclude_none=True,
    summary="查询单个品牌",
    operation_id="getBrand",
)
def get_brand(
    brand_id: str,
    session: SessionDep,
    principal: PrincipalDep,
) -> BrandView:
    require_operator(principal)
    brand = brand_service.get_brand(session, brand_id)
    return brand_to_view(brand)


@router.patch(
    "/brands/{brand_id}",
    response_model=BrandView,
    response_model_exclude_none=True,
    summary="更新品牌（运营）",
    operation_id="updateBrand",
)
def update_brand(
    brand_id: str,
    payload: BrandUpdate,
    session: SessionDep,
    principal: PrincipalDep,
) -> BrandView:
    require_operator(principal)
    brand = brand_service.update_brand(session, brand_id, payload)
    return brand_to_view(brand)


@router.delete(
    "/brands/{brand_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除品牌（运营，仅无商品时）",
    operation_id="deleteBrand",
)
def delete_brand(
    brand_id: str,
    session: SessionDep,
    principal: PrincipalDep,
) -> None:
    require_operator(principal)
    brand_service.delete_brand(session, brand_id)
