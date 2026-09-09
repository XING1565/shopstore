"""存活与就绪检查（无版本前缀的运维端点）。"""

from __future__ import annotations

from fastapi import APIRouter

from ..db import check_database
from ..errors import AppError
from ..schemas import Health, HealthCheck

router = APIRouter(tags=["health"])


@router.get("/health", response_model=Health, summary="服务存活检查", operation_id="getHealth")
def health() -> Health:
    """存活探针：进程存活即返回 ok，不检查依赖。"""
    return Health(status="ok")


@router.get("/ready", response_model=Health, summary="依赖就绪检查", operation_id="getReady")
def ready() -> Health:
    """就绪探针：检查数据库等依赖是否就绪。

    依赖就绪返回 200；依赖不可用返回 503（统一错误响应）。
    """
    db = check_database()
    checks = {"database": HealthCheck(**db)}
    if db["status"] != "ok":
        raise AppError(503, "service_unavailable", "依赖未就绪：database")
    return Health(status="ok", checks=checks)
