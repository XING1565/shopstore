"""商品（Product）API：创建 / 查询 / 更新 / 发布 / 下架。

批发价 / MOQ 是 Core 真相。鉴权语义（PRD §7）：
未认证买家不可见批发价与 MOQ；已认证（approved）买家与运营可见。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.api.deps import (
    PrincipalDep,
    SessionDep,
    can_view_pricing,
    require_operator,
)
from app.schemas import (
    ProductCreate,
    ProductList,
    ProductUpdate,
    ProductView,
)
from app.services import products as product_service
from app.services.serializers import product_to_view

router = APIRouter(tags=["products"])


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@router.get(
    "/products",
    response_model=ProductList,
    response_model_exclude_none=True,
    summary="分页列出商品",
    operation_id="listProducts",
)
def list_products(
    session: SessionDep,
    principal: PrincipalDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProductList:
    with_pricing = can_view_pricing(session, principal)
    rows, total = product_service.list_products(session, limit=limit, offset=offset)
    return ProductList(
        items=[product_to_view(p, with_pricing=with_pricing) for p in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/products",
    response_model=ProductView,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
    summary="创建商品草稿（运营）",
    operation_id="createProduct",
)
def create_product(
    payload: ProductCreate,
    session: SessionDep,
    principal: PrincipalDep,
    request: Request,
) -> ProductView:
    require_operator(principal)
    product = product_service.create_product(
        session, payload, request_id=_request_id(request)
    )
    return product_to_view(product, with_pricing=True)


@router.get(
    "/products/{product_id}",
    response_model=ProductView,
    response_model_exclude_none=True,
    summary="查询单个商品（批发价按鉴权返回）",
    operation_id="getProduct",
)
def get_product(
    product_id: str,
    session: SessionDep,
    principal: PrincipalDep,
) -> ProductView:
    product = product_service.get_product(session, product_id)
    return product_to_view(product, with_pricing=can_view_pricing(session, principal))


@router.patch(
    "/products/{product_id}",
    response_model=ProductView,
    response_model_exclude_none=True,
    summary="更新商品（运营）",
    operation_id="updateProduct",
)
def update_product(
    product_id: str,
    payload: ProductUpdate,
    session: SessionDep,
    principal: PrincipalDep,
    request: Request,
) -> ProductView:
    require_operator(principal)
    product = product_service.update_product(
        session, product_id, payload, request_id=_request_id(request)
    )
    return product_to_view(product, with_pricing=True)


@router.post(
    "/products/{product_id}/publish",
    response_model=ProductView,
    response_model_exclude_none=True,
    summary="发布商品（draft → published，运营）",
    operation_id="publishProduct",
)
def publish_product(
    product_id: str,
    session: SessionDep,
    principal: PrincipalDep,
    request: Request,
) -> ProductView:
    require_operator(principal)
    product = product_service.publish_product(
        session, product_id, request_id=_request_id(request)
    )
    return product_to_view(product, with_pricing=True)


@router.post(
    "/products/{product_id}/archive",
    response_model=ProductView,
    response_model_exclude_none=True,
    summary="下架商品（published → archived，运营）",
    operation_id="archiveProduct",
)
def archive_product(
    product_id: str,
    session: SessionDep,
    principal: PrincipalDep,
    request: Request,
) -> ProductView:
    require_operator(principal)
    product = product_service.archive_product(
        session, product_id, request_id=_request_id(request)
    )
    return product_to_view(product, with_pricing=True)
