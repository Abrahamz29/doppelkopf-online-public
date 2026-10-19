"""Add seats and round metadata for live game entry."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261002_03"
down_revision: str | None = "20261002_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "game_sessions", sa.Column("start_dealer_position", sa.Integer(), nullable=True)
    )
    op.create_table(
        "game_session_players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_session_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("seat", sa.Integer(), nullable=False),
        sa.CheckConstraint("seat BETWEEN 0 AND 3", name="ck_game_session_seat"),
        sa.ForeignKeyConstraint(["game_session_id"], ["game_sessions.id"]),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"]),
        sa.UniqueConstraint("game_session_id", "seat", name="uq_game_session_seat"),
        sa.UniqueConstraint("game_session_id", "player_id", name="uq_game_session_player"),
    )
    with op.batch_alter_table("rounds") as batch_op:
        batch_op.add_column(sa.Column("dealer_position", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("entry", sa.String(length=80), nullable=True))
        batch_op.add_column(sa.Column("declaring_party", sa.String(length=10), nullable=True))
        batch_op.add_column(
            sa.Column("active_bocks", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("scheduled_bocks", sa.Integer(), nullable=False, server_default="0")
        )
    op.execute("UPDATE rounds SET dealer_position = 0, entry = '', declaring_party = 'Re'")
    with op.batch_alter_table("rounds") as batch_op:
        batch_op.alter_column("dealer_position", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("entry", existing_type=sa.String(length=80), nullable=False)
        batch_op.alter_column(
            "declaring_party", existing_type=sa.String(length=10), nullable=False
        )


def downgrade() -> None:
    with op.batch_alter_table("rounds") as batch_op:
        batch_op.drop_column("scheduled_bocks")
        batch_op.drop_column("active_bocks")
        batch_op.drop_column("declaring_party")
        batch_op.drop_column("entry")
        batch_op.drop_column("dealer_position")
    op.drop_table("game_session_players")
    op.drop_column("game_sessions", "start_dealer_position")
