"""模型基类与通用类型。

- 主键：Core 自生成 ID，UUID v4，以字符串存储（对应契约的 `*_id` 字段）。
- 时间戳：统一 `created_at` / `updated_at`，UTC。
- 枚举列：非原生枚举（VARCHAR + CHECK），便于后续增量扩展状态值（见版本清单的
  "可稳定升级"目标）。
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

__all__ = ["Base", "TimestampMixin", "new_uuid", "utcnow", "sa_enum"]


def new_uuid() -> str:
    """生成 UUID v4 字符串（不透明主键）。"""
    return str(uuid.uuid4())


def utcnow() -> datetime:
    """返回当前 UTC 时间。"""
    return datetime.now(timezone.utc)


def sa_enum(enum_cls: type[enum.Enum], name: str, length: int = 32) -> SAEnum:
    """构造存储枚举 `.value`（snake_case 字符串）的非原生枚举列类型。

    返回的 SAEnum 使用 ``native_enum=False``：数据库侧生成 ``VARCHAR`` + ``CHECK``
    约束而非 PostgreSQL 原生 enum 类型，新增状态值时只需更新约束，无需 ``ALTER TYPE``，
    契合"可稳定升级"目标。
    """
    return SAEnum(
        enum_cls,
        name=name,
        values_callable=lambda e: [m.value for m in e],
        native_enum=False,
        validate_strings=True,
        length=length,
    )


class TimestampMixin:
    """统一的创建 / 更新时间戳。"""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
