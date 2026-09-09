"""Integration Layer 错误分类。

所有对外调用与同步任务抛出的异常都继承自 :class:`IntegrationError`，并携带
机器可读 ``code``（对齐 `packages/contracts/schemas/error.schema.json`）、
``request_id``（对齐 `X-Request-Id`）与可选的字段级 ``details``。

超时、连接失败、鉴权失败、上游错误等被分类为不同子类，使调用方可以
按类别决定是否重试。
"""

from __future__ import annotations

from typing import Any, Optional


class IntegrationError(Exception):
    """Integration Layer 所有错误的基类。"""

    code: str = "integration_error"
    http_status: int = 500

    def __init__(
        self,
        message: str,
        *,
        request_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        details: Optional[list[dict[str, str]]] = None,
        cause: Optional[BaseException] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.request_id = request_id
        self.trace_id = trace_id
        self.details = details
        self.cause = cause

    def to_envelope(self) -> dict[str, Any]:
        """序列化为统一错误响应结构（对齐 error.schema.json）。"""
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            error["details"] = self.details
        if self.request_id:
            error["request_id"] = self.request_id
        return {"error": error}


class UpstreamTimeoutError(IntegrationError):
    """对外系统调用超时。可安全重试。"""

    code = "upstream_timeout"
    http_status = 504


class UpstreamConnectionError(IntegrationError):
    """对外系统连接失败（不可达 / DNS / 握手失败）。"""

    code = "upstream_unavailable"
    http_status = 502


class UpstreamAuthError(IntegrationError):
    """对外系统鉴权失败（401 / 403）。"""

    code = "upstream_auth_error"
    http_status = 401


class ResourceNotFoundError(IntegrationError):
    """目标资源不存在（404）。"""

    code = "not_found"
    http_status = 404


class PayloadValidationError(IntegrationError):
    """负载校验失败（422）。"""

    code = "validation_error"
    http_status = 422


class IdempotencyConflictError(IntegrationError):
    """同一幂等键 + 不同负载：拒绝执行（409 Conflict）。"""

    code = "conflict"
    http_status = 409


class UpstreamError(IntegrationError):
    """对外系统返回的其它非 2xx 错误。"""

    code = "upstream_error"
    http_status = 502
