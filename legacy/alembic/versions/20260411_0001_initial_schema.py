"""Initial user and transaction schema.

Revision ID: 0001
Revises:
Create Date: 2026-04-11

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("external_user_id", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column(
            "preferences",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("memory_summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_user_profiles_external_user_id"),
        "user_profiles",
        ["external_user_id"],
        unique=True,
    )

    op.create_table(
        "transaction_records",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("txn_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=8),
            server_default="USD",
            nullable=False,
        ),
        sa.Column("merchant", sa.String(length=512), nullable=True),
        sa.Column("category", sa.String(length=128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "source",
            sa.String(length=64),
            server_default="csv_upload",
            nullable=False,
        ),
        sa.Column("fraud_score", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["user_profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_transaction_records_user_id"),
        "transaction_records",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_transaction_records_txn_date"),
        "transaction_records",
        ["txn_date"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_transaction_records_txn_date"), table_name="transaction_records")
    op.drop_index(op.f("ix_transaction_records_user_id"), table_name="transaction_records")
    op.drop_table("transaction_records")
    op.drop_index(op.f("ix_user_profiles_external_user_id"), table_name="user_profiles")
    op.drop_table("user_profiles")
