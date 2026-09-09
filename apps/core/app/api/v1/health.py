"""版本化健康检查（/api/v1/health）。"""

from __future__ import annotations

from fastapi import APIRouter

from ...schemas import Health

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=Health,
    summary="版本化健康检查",
    operation_id="getHealthV1",
)
def health_v1() -> Health:
    return Health(status="ok")
