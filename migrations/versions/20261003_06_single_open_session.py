"""Allow at most one open game session."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_06"
down_revision: str | None = "20261003_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_one_open_game_session",
        "game_sessions",
        [sa.text("(ended_at IS NULL)")],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL"),
        sqlite_where=sa.text("ended_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_one_open_game_session", table_name="game_sessions")
