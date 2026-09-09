"""数据库连接检查与迁移机制测试。"""

from __future__ import annotations


def test_check_database_returns_ok() -> None:
    from app.db import check_database

    result = check_database()
    assert result["status"] == "ok"
    assert isinstance(result["latency_ms"], int)


def test_database_url_override_takes_precedence(monkeypatch) -> None:
    from app.config import reset_settings, get_settings

    monkeypatch.setenv("DATABASE_URL", "sqlite:///override.db")
    reset_settings()
    settings = get_settings()
    url = settings.build_database_url()
    assert isinstance(url, str)
    assert url == "sqlite:///override.db"
    reset_settings()


def test_postgresql_url_assembled_from_parts(monkeypatch) -> None:
    from app.config import reset_settings, get_settings

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_HOST", "db.internal")
    monkeypatch.setenv("DB_PORT", "5433")
    monkeypatch.setenv("DB_DATABASE", "shopstore_core")
    monkeypatch.setenv("DB_USERNAME", "core")
    monkeypatch.setenv("DB_PASSWORD", "s3cret")
    reset_settings()
    settings = get_settings()
    url = settings.build_database_url()
    assert url.drivername == "postgresql+psycopg"
    assert url.host == "db.internal"
    assert url.port == 5433
    assert url.database == "shopstore_core"
    assert url.username == "core"
    assert url.password == "s3cret"
    reset_settings()
