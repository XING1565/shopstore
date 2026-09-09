"""请求上下文中间件：追踪 ID 与访问日志。"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("core.access")


class RequestContextMiddleware:
    """为每个 HTTP 请求注入 X-Request-Id 并记录访问日志。

    - 若请求未携带 X-Request-Id，服务端生成 UUID v4 并回显。
    - 生成的 request_id 挂载到 scope["state"]，供错误响应读取。
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = headers.get("x-request-id") or str(uuid.uuid4())
        scope.setdefault("state", {})["request_id"] = request_id

        started = time.perf_counter()

        async def send_wrapper(message: dict) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = list(message["headers"]) + [
                    (b"x-request-id", request_id.encode("latin-1"))
                ]
                logger.info(
                    "request_id=%s method=%s path=%s status=%s duration_ms=%d",
                    request_id,
                    scope.get("method", ""),
                    scope.get("path", ""),
                    message["status"],
                    int((time.perf_counter() - started) * 1000),
                )
            await send(message)

        await self.app(scope, receive, send_wrapper)
