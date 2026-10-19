"""Create the initial player, session, round and score tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261002_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "game_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("played_on", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "rounds",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_session_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["game_session_id"], ["game_sessions.id"]),
        sa.UniqueConstraint("game_session_id", "sequence", name="uq_round_sequence"),
    )
    op.create_table(
        "scores",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("round_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.CheckConstraint("points BETWEEN -999 AND 999", name="ck_reasonable_points"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"]),
        sa.ForeignKeyConstraint(["round_id"], ["rounds.id"]),
        sa.UniqueConstraint("round_id", "player_id", name="uq_round_player"),
    )


def downgrade() -> None:
    op.drop_table("scores")
    op.drop_table("rounds")
    op.drop_table("game_sessions")
    op.drop_table("players")
