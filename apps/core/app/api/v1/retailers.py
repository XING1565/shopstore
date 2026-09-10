"""买家（Retailer）API：注册（默认 Pending）、运营审核。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from app.api.deps import (
    PrincipalDep,
    SessionDep,
    require_operator,
)
from app.errors import AppError
from app.models.enums import RetailerStatus
from app.schemas import RetailerCreate, RetailerList, RetailerReview, RetailerView
from app.services import retailers as retailer_service
from app.services.serializers import retailer_to_view

router = APIRouter(tags=["retailers"])


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


@router.post(
    "/retailers",
    response_model=RetailerView,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
    summary="注册买家（默认 Pending）",
    operation_id="registerRetailer",
)
def register_retailer(
    payload: RetailerCreate,
    session: SessionDep,
    request: Request,
) -> RetailerView:
    retailer = retailer_service.register_retailer(
        session, payload, request_id=_request_id(request)
    )
    return retailer_to_view(retailer)


@router.get(
    "/retailers",
    response_model=RetailerList,
    response_model_exclude_none=True,
    summary="分页列出买家（运营）",
    operation_id="listRetailers",
)
def list_retailers(
    session: SessionDep,
    principal: PrincipalDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RetailerList:
    require_operator(principal)
    rows, total = retailer_service.list_retailers(session, limit=limit, offset=offset)
    return RetailerList(
        items=[retailer_to_view(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/retailers/{retailer_id}",
    response_model=RetailerView,
    response_model_exclude_none=True,
    summary="查询单个买家",
    operation_id="getRetailer",
)
def get_retailer(
    retailer_id: str,
    session: SessionDep,
    principal: PrincipalDep,
) -> RetailerView:
    retailer = retailer_service.get_retailer(session, retailer_id)
    if principal.is_retailer:
        if principal.retailer_id != retailer_id:
            raise AppError(403, "forbidden", "无权查看其他买家")
    return retailer_to_view(retailer)


@router.post(
    "/retailers/{retailer_id}/approve",
    response_model=RetailerView,
    response_model_exclude_none=True,
    summary="运营审核通过（Pending → Approved）",
    operation_id="approveRetailer",
)
def approve_retailer(
    retailer_id: str,
    payload: RetailerReview,
    session: SessionDep,
    principal: PrincipalDep,
    request: Request,
) -> RetailerView:
    require_operator(principal)
    retailer = retailer_service.review_retailer(
        session,
        retailer_id,
        RetailerStatus.approved,
        payload,
        actor=principal.operator_name or "operator",
        request_id=_request_id(request),
    )
    return retailer_to_view(retailer)


@router.post(
    "/retailers/{retailer_id}/reject",
    response_model=RetailerView,
    response_model_exclude_none=True,
    summary="运营拒绝（Pending → Rejected）",
    operation_id="rejectRetailer",
)
def reject_retailer(
    retailer_id: str,
    payload: RetailerReview,
    session: SessionDep,
    principal: PrincipalDep,
    request: Request,
) -> RetailerView:
    require_operator(principal)
    retailer = retailer_service.review_retailer(
        session,
        retailer_id,
        RetailerStatus.rejected,
        payload,
        actor=principal.operator_name or "operator",
        request_id=_request_id(request),
    )
    return retailer_to_view(retailer)
