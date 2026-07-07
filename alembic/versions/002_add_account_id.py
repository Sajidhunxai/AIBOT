"""Add account_id to trades and signals

Revision ID: 002
Revises: 001
Create Date: 2026-07-08
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("account_id", sa.Integer(), nullable=True))
    op.create_index("ix_trades_account_id", "trades", ["account_id"], unique=False)
    op.add_column("signals", sa.Column("account_id", sa.Integer(), nullable=True))
    op.create_index("ix_signals_account_id", "signals", ["account_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_signals_account_id", table_name="signals")
    op.drop_column("signals", "account_id")
    op.drop_index("ix_trades_account_id", table_name="trades")
    op.drop_column("trades", "account_id")
