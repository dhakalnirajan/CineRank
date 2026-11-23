"""enforce non-null permanent movie serial numbers on SQLite

Revision ID: f2c8d4a6b0e1
Revises: e7f8a9b0c1d2
Create Date: 2026-11-22 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2c8d4a6b0e1"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = {column["name"]: column for column in inspector.get_columns("movies")}
    if "serial_number" not in columns:
        raise RuntimeError("movies.serial_number must exist before enforcing its nullability")

    nullable = bool(columns["serial_number"]["nullable"])
    if not nullable:
        return

    null_count = connection.execute(
        sa.text("SELECT COUNT(*) FROM movies WHERE serial_number IS NULL")
    ).scalar_one()
    if int(null_count):
        raise RuntimeError(
            f"Cannot enforce movies.serial_number NOT NULL: {null_count} rows have no serial number"
        )

    if connection.dialect.name == "sqlite":
        # SQLite cannot ALTER COLUMN nullability. Alembic batch mode recreates the
        # table and preserves its reflected indexes and constraints. Alembic's
        # migration connection has foreign_keys disabled while the batch runs.
        with op.batch_alter_table("movies", recreate="always") as batch:
            batch.alter_column(
                "serial_number",
                existing_type=sa.Integer(),
                nullable=False,
            )
    else:
        op.alter_column(
            "movies",
            "serial_number",
            existing_type=sa.Integer(),
            nullable=False,
        )


def downgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = {column["name"]: column for column in inspector.get_columns("movies")}
    if "serial_number" not in columns or columns["serial_number"]["nullable"]:
        return
    if connection.dialect.name == "sqlite":
        with op.batch_alter_table("movies", recreate="always") as batch:
            batch.alter_column(
                "serial_number",
                existing_type=sa.Integer(),
                nullable=True,
            )
    else:
        op.alter_column(
            "movies",
            "serial_number",
            existing_type=sa.Integer(),
            nullable=True,
        )
