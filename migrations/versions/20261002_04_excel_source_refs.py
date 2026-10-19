"""Add traceable references for imported Excel sessions and rounds."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261002_04"
down_revision: str | None = "20261002_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("game_sessions") as batch_op:
        batch_op.add_column(sa.Column("source_reference", sa.String(length=200), nullable=True))
        batch_op.create_unique_constraint(
            "uq_game_sessions_source_reference", ["source_reference"]
        )
    op.add_column("rounds", sa.Column("source_row", sa.Integer(), nullable=True))
    op.add_column("rounds", sa.Column("source_seat_order", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("rounds", "source_seat_order")
    op.drop_column("rounds", "source_row")
    with op.batch_alter_table("game_sessions") as batch_op:
        batch_op.drop_constraint("uq_game_sessions_source_reference", type_="unique")
        batch_op.drop_column("source_reference")
