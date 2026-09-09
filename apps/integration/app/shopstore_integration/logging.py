"""Integration Layer 日志接口。

提供统一的 :class:`IntegrationLogger` 接口（Protocol）与一个基于标准库
``logging`` 的默认实现。所有日志都应携带 ``request_id`` / ``trace_id`` 等
追踪上下文，便于跨系统排查（对齐契约 `X-Request-Id` / `trace_id`）。
"""

from __future__ import annotations

import logging as _stdlib_logging
from typing import Any, Mapping, Optional, Protocol, runtime_checkable


@runtime_checkable
class IntegrationLogger(Protocol):
    """结构化日志接口。实现方需支持带上下文字段的记录。"""

    def debug(self, message: str, **context: Any) -> None: ...

    def info(self, message: str, **context: Any) -> None: ...

    def warning(self, message: str, **context: Any) -> None: ...

    def error(self, message: str, **context: Any) -> None: ...

    def with_context(self, **fields: Any) -> "IntegrationLogger": ...


class DefaultLogger:
    """基于标准库 ``logging`` 的默认实现，上下文以 ``key=value`` 拼接。"""

    def __init__(
        self,
        name: str,
        level: str = "debug",
        context: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self._logger = _stdlib_logging.getLogger(name)
        self._logger.setLevel(self._normalize_level(level))
        self._context: dict[str, Any] = dict(context or {})

    @staticmethod
    def _normalize_level(level: str) -> int:
        return getattr(_stdlib_logging, level.upper(), _stdlib_logging.DEBUG)

    def _render(self, message: str, context: Mapping[str, Any]) -> str:
        parts: list[str] = [message]
        for key, value in context.items():
            parts.append(f"{key}={value}")
        return " ".join(parts)

    def debug(self, message: str, **context: Any) -> None:
        self._logger.debug(self._render(message, {**self._context, **context}))

    def info(self, message: str, **context: Any) -> None:
        self._logger.info(self._render(message, {**self._context, **context}))

    def warning(self, message: str, **context: Any) -> None:
        self._logger.warning(self._render(message, {**self._context, **context}))

    def error(self, message: str, **context: Any) -> None:
        self._logger.error(self._render(message, {**self._context, **context}))

    def with_context(self, **fields: Any) -> "DefaultLogger":
        return DefaultLogger(
            name=self._logger.name,
            level=_stdlib_logging.getLevelName(self._logger.level),
            context={**self._context, **fields},
        )


def get_logger(name: str, level: str = "debug") -> IntegrationLogger:
    """返回一个默认日志器。"""
    return DefaultLogger(name=name, level=level)
