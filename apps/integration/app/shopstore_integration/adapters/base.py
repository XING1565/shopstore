"""Adapter 公共基类。

真实 Woo / Odoo Adapter 的共享管道：持有 :class:`UnifiedHttpClient`，
统一拼接 base_url 与路径、注入追踪头。阶段 0 只提供接口与 Mock，
真实实现留待阶段一，但可复用此基类。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from ..http_client import UnifiedHttpClient
from ..logging import IntegrationLogger, get_logger


class BaseAdapter(ABC):
    """对外系统 Adapter 基类。"""

    name: str = "base"

    def __init__(
        self,
        *,
        base_url: str,
        client: UnifiedHttpClient,
        logger: Optional[IntegrationLogger] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client
        self.logger = logger or get_logger(f"shopstore_integration.adapter.{self.name}")

    def _request(
        self,
        method: str,
        path: str,
        *,
        request_id: str,
        trace_id: Optional[str] = None,
        json: Optional[Any] = None,
    ) -> Any:
        return self.client.request(
            method,
            f"{self.base_url}{path}",
            request_id=request_id,
            trace_id=trace_id,
            json=json,
        )

    @abstractmethod
    def health_check(self, *, request_id: str) -> bool:
        """探活，返回对外系统是否可用。"""
        raise NotImplementedError


__all__ = ["BaseAdapter"]
