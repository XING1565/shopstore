"""pytest 全局夹具。

测试默认使用 SQLite 内存库，不依赖本机 PostgreSQL；可用 DATABASE_URL 覆盖。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 确保 `app` 包解析到当前 checkout 的 apps/core/app，而非环境里的陈旧
# editable 安装（曾导致 `from app.config import reset_settings` 被劫持到
# 其他 workdir 的旧 config.py）。`app` 是 apps/core/app 下的顶层包，
# 因此要把它上一级 apps/core 加入 sys.path。
CORE_DIR = Path(__file__).resolve().parents[1]
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

os.environ["DATABASE_URL"] = os.environ.get("DATABASE_URL", "sqlite:///:memory:")

import pytest  # noqa: E402

from app.config import reset_settings  # noqa: E402

import app.models  # noqa: E402,F401  确保业务模型注册进 Base.metadata


@pytest.fixture
def client():
    """函数级 TestClient，每次测试重建应用与配置缓存。"""
    reset_settings()
    from fastapi.testclient import TestClient

    from app.main import create_app

    application = create_app()
    with TestClient(application) as c:
        yield c
    reset_settings()


@pytest.fixture
def session():
    """函数级 SQLite 内存会话，用于模型与状态机测试（不依赖本机 PostgreSQL）。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db import Base

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    s = factory()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()
