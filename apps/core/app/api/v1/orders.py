"""订单（Order）API：无支付下单（MOQ 校验）。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.api.deps import (
    PrincipalDep,
    SessionDep,
    require_approved_retailer,
    require_operator,
)
from app.errors import AppError
from app.schemas import (
    OrderCreate,
    OrderExternalIdWriteback,
    OrderFulfillmentUpdate,
    OrderList,
    OrderView,
)
from app.services import orders as order_service
from app.services.serializers import order_to_view

router = APIRouter(tags=["orders"])


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@router.post(
    "/orders",
    response_model=OrderView,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
    summary="无支付下单（MOQ 校验，仅认证买家）",
    operation_id="placeOrder",
)
def place_order(
    payload: OrderCreate,
    session: SessionDep,
    principal: PrincipalDep,
    request: Request,
) -> OrderView:
    retailer = require_approved_retailer(session, principal)
    order = order_service.place_order(
        session, retailer, payload, request_id=_request_id(request)
    )
    return order_to_view(order)


@router.get(
    "/orders",
    response_model=OrderList,
    response_model_exclude_none=True,
    summary="分页列出订单（运营全部，买家本人）",
    operation_id="listOrders",
)
def list_orders(
    session: SessionDep,
    principal: PrincipalDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OrderList:
    retailer_id = None
    if principal.is_retailer:
        retailer_id = principal.retailer_id
    elif not principal.is_operator:
        raise AppError(403, "forbidden", "无权查看订单")
    rows, total = order_service.list_orders(
        session, retailer_id=retailer_id, limit=limit, offset=offset
    )
    return OrderList(
        items=[order_to_view(o) for o in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/orders/{order_id}",
    response_model=OrderView,
    response_model_exclude_none=True,
    summary="查询单个订单（运营或本人）",
    operation_id="getOrder",
)
def get_order(
    order_id: str,
    session: SessionDep,
    principal: PrincipalDep,
) -> OrderView:
    order = order_service.get_order(session, order_id)
    if principal.is_retailer and principal.retailer_id != order.retailer_id:
        raise AppError(403, "forbidden", "无权查看其他买家订单")
    if principal.is_anonymous:
        raise AppError(403, "forbidden", "无权查看订单")
    return order_to_view(order)


@router.post(
    "/orders/{order_id}/fulfillment",
    response_model=OrderView,
    response_model_exclude_none=True,
    summary="回传履约状态（Integration -> Core，仅运营/系统）",
    operation_id="reportFulfillment",
)
def report_fulfillment(
    order_id: str,
    payload: OrderFulfillmentUpdate,
    session: SessionDep,
    principal: PrincipalDep,
    request: Request,
) -> OrderView:
    require_operator(principal)
    order = order_service.report_fulfillment(
        session, order_id, payload, request_id=_request_id(request)
    )
    return order_to_view(order)


@router.post(
    "/orders/{order_id}/external-ids",
    response_model=OrderView,
    response_model_exclude_none=True,
    summary="写回订单外部 ID 映射（Integration 调用，运营身份）",
    operation_id="writebackOrderExternalIds",
)
def writeback_external_ids(
    order_id: str,
    payload: OrderExternalIdWriteback,
    session: SessionDep,
    principal: PrincipalDep,
    request: Request,
) -> OrderView:
    require_operator(principal)
    if payload.odoo_sale_order_id is not None:
        order = order_service.record_odoo_sale_order(
            session,
            order_id,
            payload.odoo_sale_order_id,
            request_id=_request_id(request),
        )
    else:
        order = order_service.get_order(session, order_id)
        raise AppError(400, "bad_request", "未提供可写回的外部 ID")
    return order_to_view(order)
