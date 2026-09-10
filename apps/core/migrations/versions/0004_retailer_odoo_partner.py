"""retailer odoo partner external id mapping

为 Retailer 增加 ``odoo_partner_ref`` / ``odoo_partner_id`` 两个外部 ID 映射字段，
用于把买家稳定映射到 Odoo ``res.partner``（``ref`` 匹配 canonical partner，如
``DEMO-RTL-001``）。映射由 Integration 导出订单时写回，避免同一买家多次下单
重复创建 Odoo partner（ISSUE-0112）。

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("retailers", sa.Column("odoo_partner_ref", sa.String(64), nullable=True))
    op.add_column("retailers", sa.Column("odoo_partner_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_retailers_odoo_partner_ref", "retailers", ["odoo_partner_ref"])
    op.create_index("ix_retailers_odoo_partner_id", "retailers", ["odoo_partner_id"])


def downgrade() -> None:
    op.drop_index("ix_retailers_odoo_partner_id", table_name="retailers")
    op.drop_index("ix_retailers_odoo_partner_ref", table_name="retailers")
    op.drop_column("retailers", "odoo_partner_id")
    op.drop_column("retailers", "odoo_partner_ref")
