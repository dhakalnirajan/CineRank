"""add permanent public title serial numbers

Revision ID: b6e1f4a2c9d7
Revises: 8f4c2a9d7b11
Create Date: 2026-11-21 01:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b6e1f4a2c9d7"
down_revision: Union[str, Sequence[str], None] = "8f4c2a9d7b11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if "title_serial_sequence" not in inspector.get_table_names():
        op.create_table(
            "title_serial_sequence",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("next_value", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    movie_columns = {column["name"] for column in sa.inspect(connection).get_columns("movies")}
    if "serial_number" not in movie_columns:
        op.add_column("movies", sa.Column("serial_number", sa.Integer(), nullable=True))

    rows = connection.execute(sa.text(
        "SELECT title_id FROM movies ORDER BY created_at ASC, title_id ASC"
    )).fetchall()
    for serial, (title_id,) in enumerate(rows, start=1):
        connection.execute(
            sa.text("UPDATE movies SET serial_number = :serial WHERE title_id = :title_id"),
            {"serial": serial, "title_id": title_id},
        )

    index_names = {index["name"] for index in sa.inspect(connection).get_indexes("movies")}
    if "ix_movies_serial_number" not in index_names:
        op.create_index(
            "ix_movies_serial_number", "movies", ["serial_number"], unique=True
        )
    if connection.dialect.name != "sqlite":
        op.alter_column("movies", "serial_number", existing_type=sa.Integer(), nullable=False)

    current_next = connection.execute(sa.text(
        "SELECT next_value FROM title_serial_sequence WHERE id = 1"
    )).scalar_one_or_none()
    next_value = max(int(current_next or 1), len(rows) + 1)
    if current_next is None:
        connection.execute(
            sa.text(
                "INSERT INTO title_serial_sequence (id, next_value) VALUES (1, :next_value)"
            ),
            {"next_value": next_value},
        )
    else:
        connection.execute(
            sa.text("UPDATE title_serial_sequence SET next_value = :next_value WHERE id = 1"),
            {"next_value": next_value},
        )


def downgrade() -> None:
    op.drop_index("ix_movies_serial_number", table_name="movies")
    op.drop_column("movies", "serial_number")
    op.drop_table("title_serial_sequence")
