"""Product（商品）模型。"""

from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

from .base import TimestampMixin, new_uuid, sa_enum
from .enums import ProductStatus
from .state_machine import PRODUCT_TRANSITIONS, InvalidStateTransitionError, logger

__all__ = ["Product"]


class Product(TimestampMixin, Base):
    """商品业务主实体（Core 主权）。

    批发价以最小单位整数存储（``wholesale_price_minor`` + ``wholesale_price_currency``），
    与 `packages/contracts/schemas/money.schema.json` 一致，禁止浮点数。
    外部 ID 映射（``woo_product_id`` / ``odoo_product_id``）为 NULL 时表示该投影尚未创建。
    """

    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    sku: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand_id: Mapped[str] = mapped_column(
        ForeignKey("brands.id"), nullable=False, index=True
    )
    brand: Mapped["Brand"] = relationship(back_populates="products")

    # 批发价（最小单位整数 + ISO 4217 货币）
    wholesale_price_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    wholesale_price_currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="USD"
    )

    # MOQ 最小起订量（>= 1）
    moq: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    status: Mapped[ProductStatus] = mapped_column(
        sa_enum(ProductStatus, "product_status"),
        nullable=False,
        default=ProductStatus.draft,
    )

    # 三系统外部 ID 映射（NULL = 投影尚未创建）
    woo_product_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )
    odoo_product_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )

    def transition_to(self, target: ProductStatus) -> None:
        """按商品状态机单向推进（draft -> published -> archived）；非法迁移被拒绝。"""
        target = ProductStatus(target)
        if target is self.status:
            return
        allowed = PRODUCT_TRANSITIONS.get(self.status, set())
        if target not in allowed:
            logger.warning(
                "拒绝非法商品状态迁移 product_id=%s from=%s to=%s",
                self.id,
                self.status.value,
                target.value,
            )
            raise InvalidStateTransitionError(
                "product",
                self.id,
                self.status.value,
                target.value,
                (a.value for a in allowed),
            )
        old = self.status
        self.status = target
        logger.info(
            "商品状态迁移 product_id=%s %s -> %s", self.id, old.value, target.value
        )
