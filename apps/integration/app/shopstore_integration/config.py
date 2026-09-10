"""Integration Layer 配置与超时设置。

从环境变量加载配置（不写死）；超时 / 重试参数统一收敛到
:class:`TimeoutConfig` 与 :class:`RetryConfig`，供统一请求客户端与同步任务使用。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Mapping, Optional


@dataclass(frozen=True)
class TimeoutConfig:
    """单个对外 HTTP 调用的超时预算（单位：秒）。"""

    connect_seconds: float = 5.0
    read_seconds: float = 30.0
    write_seconds: float = 30.0
    pool_seconds: float = 5.0


@dataclass(frozen=True)
class RetryConfig:
    """同步任务的重试策略（阶段 0 仅记录配置，重试在后续阶段落地）。"""

    max_attempts: int = 3
    backoff_seconds: float = 0.5
    backoff_factor: float = 2.0


@dataclass(frozen=True)
class IntegrationSettings:
    """Integration Layer 运行时配置，全部可由环境变量覆盖。"""

    app_env: str = "local"
    app_debug: bool = True
    log_level: str = "debug"

    core_base_url: str = "http://localhost:8000"
    woo_base_url: str = "http://localhost:8080"
    odoo_base_url: str = "http://localhost:8069"

    # Odoo JSON-RPC 登录（履约轮询 worker 读取交货单状态用）
    odoo_db: str = "shopstore_odoo"
    odoo_user: str = "admin"
    odoo_password: str = ""

    sync_poll_interval_seconds: int = 30
    sync_retry_max: int = 5

    timeout: TimeoutConfig = field(default_factory=TimeoutConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "IntegrationSettings":
        env = os.environ if environ is None else environ

        def _str(name: str, default: str) -> str:
            value = env.get(name)
            return default if value is None or value == "" else value

        def _int(name: str, default: int) -> int:
            value = _str(name, "")
            if value == "":
                return default
            return int(value)

        def _float(name: str, default: float) -> float:
            value = _str(name, "")
            if value == "":
                return default
            return float(value)

        def _bool(name: str, default: bool) -> bool:
            value = _str(name, "").strip().lower()
            if value == "":
                return default
            return value in {"1", "true", "yes", "on"}

        timeout = TimeoutConfig(
            connect_seconds=_float("HTTP_TIMEOUT_CONNECT_SECONDS", 5.0),
            read_seconds=_float("HTTP_TIMEOUT_READ_SECONDS", 30.0),
            write_seconds=_float("HTTP_TIMEOUT_WRITE_SECONDS", 30.0),
            pool_seconds=_float("HTTP_TIMEOUT_POOL_SECONDS", 5.0),
        )
        retry = RetryConfig(
            max_attempts=_int("SYNC_RETRY_MAX", 3),
            backoff_seconds=_float("SYNC_RETRY_BACKOFF_SECONDS", 0.5),
            backoff_factor=_float("SYNC_RETRY_BACKOFF_FACTOR", 2.0),
        )

        return cls(
            app_env=_str("APP_ENV", "local"),
            app_debug=_bool("APP_DEBUG", True),
            log_level=_str("LOG_LEVEL", "debug"),
            core_base_url=_str("CORE_BASE_URL", "http://localhost:8000"),
            woo_base_url=_str("WOO_BASE_URL", "http://localhost:8080"),
            odoo_base_url=_str("ODOO_BASE_URL", "http://localhost:8069"),
            odoo_db=_str("ODOO_DB_NAME", "shopstore_odoo"),
            odoo_user=_str("ODOO_USER", "admin"),
            odoo_password=_str("ODOO_PASSWORD", ""),
            sync_poll_interval_seconds=_int("SYNC_POLL_INTERVAL_SECONDS", 30),
            sync_retry_max=_int("SYNC_RETRY_MAX", 5),
            timeout=timeout,
            retry=retry,
        )


def get_settings(environ: Optional[Mapping[str, str]] = None) -> IntegrationSettings:
    """加载当前环境的 Integration 配置（优先进程环境变量）。"""
    return IntegrationSettings.from_env(environ)
