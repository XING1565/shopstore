"""initial baseline (empty)

阶段 0 基座：建立迁移基线，暂无业务表。后续业务模型迁移在此基线之上递增。

Revision ID: 0001
Revises:
Create Date: 2026-09-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
