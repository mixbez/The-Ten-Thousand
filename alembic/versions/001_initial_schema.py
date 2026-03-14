"""Initial schema - users and interactions tables

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("telegram_id", sa.String(), unique=True, nullable=True),
        sa.Column("personality", sa.String(50), nullable=True),
        sa.Column("coaching_style", sa.String(50), nullable=True),
        sa.Column("motivation", sa.String(200), nullable=True),
        sa.Column(
            "health_scores",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("timezone_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("timezone_name", sa.String(50), nullable=False, server_default="UTC"),
        sa.Column("fsm_state", sa.String(100), nullable=True),
        sa.Column("fsm_phase", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_monthly_audit", sa.DateTime(), nullable=True),
        sa.Column("block_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("block_reset_at", sa.DateTime(), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("message_window_start", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Index on telegram_id for fast lookups
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    # Create interactions table
    op.create_table(
        "interactions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("nudge_text", sa.Text(), nullable=True),
        sa.Column("response_text", sa.Text(), nullable=True),
        sa.Column("completed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("category", sa.String(50), nullable=True),
        sa.Column("delivery_time", sa.String(10), nullable=True),
        sa.Column("scheduled_time", sa.DateTime(), nullable=True),
        sa.Column("responded_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # Index on user_id for fast lookups
    op.create_index("ix_interactions_user_id", "interactions", ["user_id"])
    # Index on scheduled_time for scheduler queries
    op.create_index("ix_interactions_scheduled_time", "interactions", ["scheduled_time"])


def downgrade() -> None:
    op.drop_index("ix_interactions_scheduled_time", table_name="interactions")
    op.drop_index("ix_interactions_user_id", table_name="interactions")
    op.drop_table("interactions")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")
