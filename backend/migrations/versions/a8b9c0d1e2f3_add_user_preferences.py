"""add explicit user recommendation preferences

Revision ID: a8b9c0d1e2f3
Revises: f2c8d4a6b0e1
Create Date: 2026-11-23

"""
from alembic import op
import sqlalchemy as sa

revision = "a8b9c0d1e2f3"
down_revision = "f2c8d4a6b0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("preferred_genres_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("excluded_genres_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("include_adult", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("min_year", sa.Integer(), nullable=True),
        sa.Column("max_runtime", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("min_year IS NULL OR min_year BETWEEN 1888 AND 2100", name="ck_user_preferences_min_year"),
        sa.CheckConstraint("max_runtime IS NULL OR max_runtime BETWEEN 30 AND 600", name="ck_user_preferences_max_runtime"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

def downgrade() -> None:
    op.drop_table("user_preferences")
