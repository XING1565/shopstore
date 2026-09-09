"""pytest 全局夹具。

测试默认使用 SQLite 内存库，不依赖本机 PostgreSQL；可用 DATABASE_URL 覆盖。
"""

from __future__ import annotations

import os

os.environ["DATABASE_URL"] = os.environ.get("DATABASE_URL", "sqlite:///:memory:")

import pytest  # noqa: E402

from app.config import reset_settings  # noqa: E402


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
