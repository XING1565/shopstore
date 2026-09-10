"""ShopVidi Integration Layer.

跨系统连接层：Woo / Odoo Adapter、同步任务、幂等、统一 HTTP 客户端与错误分类。

阶段 0 只提供骨架与 Mock 验证链路：

    Core Command -> Integration Task -> Adapter -> Mock Result

Core 领域模块不直接依赖 Woo / Odoo API 细节；Integration 负责对外 API 适配、
超时、重试、幂等、错误分类与日志。
"""

from __future__ import annotations

from . import config, errors, http_client, idempotency
from .config import IntegrationSettings, RetryConfig, TimeoutConfig
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
from .http_client import UnifiedHttpClient
from .retry import RetryWorker
from .sync_jobs import SyncJob, SyncJobsStore

__all__ = [
    "IntegrationSettings",
    "RetryConfig",
    "TimeoutConfig",
    "IntegrationError",
    "IdempotencyConflictError",
    "PayloadValidationError",
    "ResourceNotFoundError",
    "UpstreamAuthError",
    "UpstreamConnectionError",
    "UpstreamError",
    "UpstreamTimeoutError",
    "UnifiedHttpClient",
    "SyncJob",
    "SyncJobsStore",
    "RetryWorker",
    "config",
    "errors",
    "http_client",
    "idempotency",
]

__version__ = "0.1.0"
