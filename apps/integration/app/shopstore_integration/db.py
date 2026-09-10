"""Integration Layer 数据库访问（``sync_jobs`` 任务表）。

阶段 1 用数据库任务表承载同步任务 / 幂等键 / 重试与死信，避免提前引入
消息中间件（见 docs/版本清单.md 第 5.2 节）。默认连接可通过环境变量覆盖：

- ``INTEGRATION_DATABASE_URL``（首选）
- ``DATABASE_URL``（回退，便于与 Core 同库的本地开发）
- 缺省 ``sqlite:///:memory:``（仅测试 / 无持久化场景）
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


class Base(DeclarativeBase):
    """Integration Layer 所有 ORM 模型的基类（sync_jobs 任务表）。"""


def _default_url() -> str:
    return (
        os.environ.get("INTEGRATION_DATABASE_URL")
        or os.environ.get("DATABASE_URL")
        or "sqlite:///:memory:"
    )


def get_engine() -> Engine:
    """返回进程级缓存的 SQLAlchemy Engine。"""
    global _engine
    if _engine is None:
        _engine = create_engine(_default_url(), pool_pre_ping=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """返回进程级缓存的 Session 工厂。"""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False
        )
    return _session_factory


def create_all(bind: Engine | None = None) -> None:
    """按当前模型元数据建表（阶段 1 用于本地 / 测试引导，正式迁移见 migrations）。"""
    Base.metadata.create_all(bind or get_engine())
