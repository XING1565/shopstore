"""应用配置加载。

所有配置通过环境变量注入，代码中不写死任何环境相关值。
变量命名遵循仓库命名规范（见 docs/命名规范.md 与 infra/env/core.env.example）。
"""

from __future__ import annotations

from sqlalchemy.engine import URL
from pydantic_settings import BaseSettings, SettingsConfigDict

_POSTGRES_DIALECTS = {"postgresql", "postgres"}


class Settings(BaseSettings):
    """Core 服务配置，字段自动映射为同名大写环境变量（大小写不敏感）。"""

    model_config = SettingsConfigDict(
        env_file=(".env", "apps/core/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # 运行环境与基础信息
    app_name: str = "ShopVidi Marketplace Core API"
    app_env: str = "local"
    app_debug: bool = False
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    log_level: str = "INFO"

    # 数据库（Core 独立数据库，见 infra/env/core.env.example）
    db_connection: str = "postgresql"
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_database: str = "shopstore_core"
    db_username: str = "core"
    db_password: str = "change_me_in_env_file"

    # 跨系统地址（阶段 0 暂未使用，保留供后续 Integration 接入）
    woo_base_url: str = "http://localhost:8080"
    odoo_base_url: str = "http://localhost:8069"

    # API 版本前缀（唯一权威版本信号，见 packages/contracts/conventions.md 第 9 节）
    api_v1_prefix: str = "/api/v1"

    # 可选：完整 SQLAlchemy URL 覆盖（测试 / CI 使用，例如 sqlite:///...）
    database_url: str | None = None

    @property
    def sqlalchemy_drivername(self) -> str:
        """将 DB_CONNECTION 归一化为 SQLAlchemy 方言名。"""
        if self.db_connection.lower() in _POSTGRES_DIALECTS:
            return "postgresql+psycopg"
        return self.db_connection

    def build_database_url(self) -> URL | str:
        """构建 SQLAlchemy 连接地址；database_url 覆盖优先。"""
        if self.database_url:
            return self.database_url
        return URL.create(
            drivername=self.sqlalchemy_drivername,
            username=self.db_username,
            password=self.db_password,
            host=self.db_host,
            port=self.db_port,
            database=self.db_database,
        )


_settings: Settings | None = None


def get_settings() -> Settings:
    """返回进程级缓存的 Settings 实例。"""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reset_settings() -> None:
    """清除缓存（测试或热更新场景使用）。"""
    global _settings
    _settings = None
