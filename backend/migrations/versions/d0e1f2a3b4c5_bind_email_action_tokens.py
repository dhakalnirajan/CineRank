"""bind email action tokens to the address they verify

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-11-23

"""
from alembic import op
import sqlalchemy as sa

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("email_action_tokens") as batch:
        batch.add_column(sa.Column("email", sa.String(length=254), nullable=True))
    op.execute(
        "UPDATE email_action_tokens SET email = COALESCE("
        "(SELECT lower(users.email) FROM users WHERE users.id = email_action_tokens.user_id), "
        "'')"
    )
    with op.batch_alter_table("email_action_tokens") as batch:
        batch.alter_column("email", existing_type=sa.String(length=254), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("email_action_tokens") as batch:
        batch.drop_column("email")
