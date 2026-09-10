"""Alembic 迁移环境。

连接地址从应用配置（环境变量）读取，不写死；支持在线 / 离线两种模式。
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# 确保 apps/core 在 sys.path 中，从而可导入 app 包（无论从何处运行 alembic）。
APP_DIR = Path(__file__).resolve().parent.parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from app.config import get_settings  # noqa: E402
from app.db import Base  # noqa: E402
import app.models  # noqa: E402,F401  确保业务模型注册进 Base.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    settings = get_settings()
    url = settings.build_database_url()
    if isinstance(url, str):
        return url
    return url.render_as_string(hide_password=False)


config.set_main_option("sqlalchemy.url", _database_url())


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 而不连接数据库。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库执行迁移。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
