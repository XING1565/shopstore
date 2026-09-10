"""retailer / brand / product / order models

阶段 1 业务地基：买家、品牌、商品、订单四类核心模型与订单状态机。
外部 ID 映射字段：Product(woo_product_id / odoo_product_id)、
Order(woo_order_id / odoo_sale_order_id / odoo_delivery_id)。

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


retailer_status = sa.Enum(
    "pending", "approved", "rejected", "suspended",
    name="retailer_status", native_enum=False,
)
brand_status = sa.Enum(
    "active", "inactive",
    name="brand_status", native_enum=False,
)
product_status = sa.Enum(
    "draft", "published", "archived",
    name="product_status", native_enum=False,
)
order_status = sa.Enum(
    "draft", "submitted", "sent_to_odoo", "odoo_confirmed", "inventory_reserved",
    "picking_ready", "shipped", "completed", "cancelled", "sync_failed",
    name="order_status", native_enum=False,
)


def upgrade() -> None:
    op.create_table(
        "retailers",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("contact_name", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("status", retailer_status, nullable=False),
        sa.Column("reviewed_by", sa.String(255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_retailers_email", "retailers", ["email"], unique=True)

    op.create_table(
        "brands",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("logo_url", sa.String(2048), nullable=True),
        sa.Column("status", brand_status, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_brands_name", "brands", ["name"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("brand_id", sa.String(36), sa.ForeignKey("brands.id"), nullable=False),
        sa.Column("wholesale_price_minor", sa.BigInteger(), nullable=False),
        sa.Column("wholesale_price_currency", sa.String(3), nullable=False),
        sa.Column("moq", sa.Integer(), nullable=False),
        sa.Column("status", product_status, nullable=False),
        sa.Column("woo_product_id", sa.BigInteger(), nullable=True),
        sa.Column("odoo_product_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_products_sku", "products", ["sku"], unique=True)
    op.create_index("ix_products_brand_id", "products", ["brand_id"])
    op.create_index("ix_products_woo_product_id", "products", ["woo_product_id"])
    op.create_index("ix_products_odoo_product_id", "products", ["odoo_product_id"])

    op.create_table(
        "orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("retailer_id", sa.String(36), sa.ForeignKey("retailers.id"), nullable=False),
        sa.Column("status", order_status, nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("woo_order_id", sa.BigInteger(), nullable=True),
        sa.Column("odoo_sale_order_id", sa.BigInteger(), nullable=True),
        sa.Column("odoo_delivery_id", sa.BigInteger(), nullable=True),
        sa.Column("sync_failed_from", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_orders_retailer_id", "orders", ["retailer_id"])
    op.create_index("ix_orders_woo_order_id", "orders", ["woo_order_id"])
    op.create_index("ix_orders_odoo_sale_order_id", "orders", ["odoo_sale_order_id"])
    op.create_index("ix_orders_odoo_delivery_id", "orders", ["odoo_delivery_id"])

    op.create_table(
        "order_lines",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "order_id",
            sa.String(36),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sku", sa.String(64), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price_minor", sa.BigInteger(), nullable=False),
        sa.Column("unit_price_currency", sa.String(3), nullable=False),
    )
    op.create_index("ix_order_lines_order_id", "order_lines", ["order_id"])

    op.create_table(
        "order_status_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "order_id",
            sa.String(36),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(32), nullable=False),
        sa.Column("to_status", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(255), nullable=True),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_order_status_events_order_id", "order_status_events", ["order_id"])


def downgrade() -> None:
    op.drop_table("order_status_events")
    op.drop_table("order_lines")
    op.drop_table("orders")
    op.drop_table("products")
    op.drop_table("brands")
    op.drop_table("retailers")
