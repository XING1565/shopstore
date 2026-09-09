"""统一请求客户端。

基于 ``httpx`` 的统一 HTTP 客户端，供 Woo / Odoo 真实 Adapter 使用。
统一职责：

- 注入追踪头 ``X-Request-Id``（缺失时由调用方传入，客户端不生成）；
- 统一超时预算（:class:`TimeoutConfig`）；
- 将底层网络 / 状态码错误分类为 :class:`IntegrationError` 子类，
  使超时与异常可被上层捕获并决定是否重试。
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

import httpx

from .config import TimeoutConfig
from .errors import (
    IdempotencyConflictError,
    IntegrationError,
    PayloadValidationError,
    ResourceNotFoundError,
    UpstreamAuthError,
    UpstreamConnectionError,
    UpstreamError,
    UpstreamTimeoutError,
)
from .logging import IntegrationLogger, get_logger

_REQUEST_ID_HEADER = "X-Request-Id"


class UnifiedHttpClient:
    """httpx 的统一封装：注入追踪头、统一超时、统一错误分类。"""

    def __init__(
        self,
        *,
        timeout: Optional[TimeoutConfig] = None,
        logger: Optional[IntegrationLogger] = None,
        transport: Optional[httpx.BaseTransport] = None,
        auth: Optional[httpx.Auth] = None,
    ) -> None:
        self._timeout = timeout or TimeoutConfig()
        self._logger = logger or get_logger("shopstore_integration.http_client")
        self._client = httpx.Client(
            timeout=httpx.Timeout(
                connect=self._timeout.connect_seconds,
                read=self._timeout.read_seconds,
                write=self._timeout.write_seconds,
                pool=self._timeout.pool_seconds,
            ),
            transport=transport,
            auth=auth,
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        request_id: str,
        trace_id: Optional[str] = None,
        json: Optional[Any] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Any:
        """发起一次请求并返回解析后的 JSON；非 2xx 或网络错误抛分类异常。"""
        merged_headers = {_REQUEST_ID_HEADER: request_id}
        if headers:
            merged_headers.update(headers)

        try:
            response = self._client.request(
                method, url, json=json, headers=merged_headers
            )
        except httpx.TimeoutException as exc:
            raise UpstreamTimeoutError(
                f"upstream timed out: {method} {url}",
                request_id=request_id,
                trace_id=trace_id,
                cause=exc,
            ) from exc
        except httpx.TransportError as exc:
            raise UpstreamConnectionError(
                f"upstream connection failed: {method} {url}",
                request_id=request_id,
                trace_id=trace_id,
                cause=exc,
            ) from exc

        self._classify_status(response.status_code, method, url, request_id, trace_id)

        if response.status_code == 204:
            return None
        try:
            return response.json()
        except ValueError:
            return None

    def _classify_status(
        self,
        status_code: int,
        method: str,
        url: str,
        request_id: str,
        trace_id: Optional[str],
    ) -> None:
        if 200 <= status_code < 300:
            return

        context = dict(request_id=request_id, trace_id=trace_id)
        detail = f"upstream returned {status_code}: {method} {url}"

        if status_code in (401, 403):
            raise UpstreamAuthError(detail, **context)
        if status_code == 404:
            raise ResourceNotFoundError(detail, **context)
        if status_code == 409:
            raise IdempotencyConflictError(detail, **context)
        if status_code == 422:
            raise PayloadValidationError(detail, **context)
        raise UpstreamError(detail, **context)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "UnifiedHttpClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()


__all__ = ["UnifiedHttpClient", "IntegrationError"]
