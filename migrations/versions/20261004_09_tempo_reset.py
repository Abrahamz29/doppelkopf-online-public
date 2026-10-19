"""Persist the start of a new live tempo segment."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261004_09"
down_revision: str | None = "20261003_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("game_sessions") as batch_op:
        batch_op.add_column(sa.Column("tempo_reset_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("game_sessions") as batch_op:
        batch_op.drop_column("tempo_reset_at")
