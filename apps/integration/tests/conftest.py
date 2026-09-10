"""pytest 配置：把 ``app/`` 加入导入路径，使 ``shopstore_integration`` 可被测试导入。"""

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import pytest  # noqa: E402


@pytest.fixture
def sync_jobs_store():
    """数据库幂等存储（SQLite 内存库，注册 sync_jobs 表）。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import shopstore_integration.sync_jobs  # noqa: F401  注册 SyncJob 模型
    from shopstore_integration.db import Base
    from shopstore_integration.sync_jobs import SyncJobsStore

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    store = SyncJobsStore(factory)
    yield store
    engine.dispose()


class MutableClock:
    """可控时钟，用于推进退避时间。"""

    def __init__(self, start=None):
        from datetime import datetime, timezone

        self.now = start or datetime(2026, 1, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, seconds):
        from datetime import timedelta

        self.now = self.now + timedelta(seconds=seconds)


@pytest.fixture
def clock():
    return MutableClock()


@pytest.fixture
def clock_store(clock):
    """带可控时钟的 SQLite 内存 SyncJobsStore（用于退避 / 死信测试）。"""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    import shopstore_integration.sync_jobs  # noqa: F401  注册 SyncJob 模型
    from shopstore_integration.db import Base
    from shopstore_integration.sync_jobs import SyncJobsStore

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    store = SyncJobsStore(factory, clock=clock)
    yield store
    engine.dispose()
