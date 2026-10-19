"""Add an explicit end timestamp to game sessions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261002_02"
down_revision: str | None = "20261002_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("game_sessions", sa.Column("ended_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("game_sessions", "ended_at")
