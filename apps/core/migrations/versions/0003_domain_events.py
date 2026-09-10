"""domain_events outbox

Core 发布领域事件（outbox 模式），Integration 消费后投影 Woo / Odoo。
事件信封结构见 packages/contracts/events/envelope.schema.json。

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "domain_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("event_type", sa.String(255), nullable=False),
        sa.Column("event_version", sa.String(8), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("trace_id", sa.String(36), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("published", sa.Boolean(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_domain_events_event_type", "domain_events", ["event_type"])
    op.create_index("ix_domain_events_published", "domain_events", ["published"])


def downgrade() -> None:
    op.drop_index("ix_domain_events_published", table_name="domain_events")
    op.drop_index("ix_domain_events_event_type", table_name="domain_events")
    op.drop_table("domain_events")
