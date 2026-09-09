"""pytest 全局夹具。

测试默认使用 SQLite 内存库，不依赖本机 PostgreSQL；可用 DATABASE_URL 覆盖。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 确保 `app` 包解析到当前 checkout 的 apps/core/app，而非环境里的陈旧
# editable 安装（曾导致 `from app.config import reset_settings` 被劫持到
# 其他 workdir 的旧 config.py）。与 apps/integration/tests/conftest.py 一致。
APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

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
