"""应用日志配置。"""

from __future__ import annotations

import logging

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """配置根日志器与 uvicorn 日志。

    访问日志由 core.access 中间件记录；此处将 uvicorn 默认访问日志降噪以避免重复。
    """
    logging.basicConfig(level=level.upper(), format=_LOG_FORMAT)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(level.upper())
