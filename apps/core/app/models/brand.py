"""Brand（品牌）模型。"""

from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

from .base import TimestampMixin, new_uuid, sa_enum
from .enums import BrandStatus

__all__ = ["Brand"]


class Brand(TimestampMixin, Base):
    """品牌档案（Core 主权）。阶段一由运营代维护，后续 Vendor Portal 自助。"""

    __tablename__ = "brands"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    status: Mapped[BrandStatus] = mapped_column(
        sa_enum(BrandStatus, "brand_status"),
        nullable=False,
        default=BrandStatus.active,
    )

    products: Mapped[list["Product"]] = relationship(back_populates="brand")
