"""Add assessment_data column to users

Revision ID: 002
Revises: 001
Create Date: 2026-03-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('assessment_data', JSONB, nullable=True, server_default='{}'))


def downgrade() -> None:
    op.drop_column('users', 'assessment_data')
