"""merge avatar profile and public title serial migration branches

Revision ID: e7f8a9b0c1d2
Revises: b6e1f4a2c9d7, c1d2e3f4a5b6
Create Date: 2026-11-22 17:40:00.000000

"""
from typing import Sequence, Union

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = (
    "b6e1f4a2c9d7",
    "c1d2e3f4a5b6",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # This is a graph merge only. Both parent revisions perform their own DDL.
    pass


def downgrade() -> None:
    # A merge revision has no standalone schema change to reverse.
    pass
