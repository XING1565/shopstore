"""数据库引擎、会话管理与数据库连接检查。"""

from __future__ import annotations

import time
from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


class Base(DeclarativeBase):
    """所有 ORM 模型的基类（阶段 0 尚无业务模型）。"""


def get_engine() -> Engine:
    """返回进程级缓存的 SQLAlchemy Engine。"""
    global _engine
    if _engine is None:
        from .config import get_settings

        settings = get_settings()
        _engine = create_engine(
            settings.build_database_url(),
            pool_pre_ping=True,
            echo=settings.app_debug,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """返回进程级缓存的 Session 工厂。"""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autoflush=False,
            expire_on_commit=False,
        )
    return _session_factory


def get_session() -> Iterator[Session]:
    """FastAPI 依赖：请求级数据库会话。"""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def check_database() -> dict:
    """执行一次最小连接探活（SELECT 1），返回检查结果。

    返回形如 ``{"status": "ok" | "down", "latency_ms": int}``。
    """
    started = time.perf_counter()
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        status = "ok"
    except Exception:
        status = "down"
    latency_ms = int((time.perf_counter() - started) * 1000)
    return {"status": status, "latency_ms": latency_ms}
