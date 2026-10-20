"""Preserve Isar source identities and complete game records alongside app results."""

import sqlalchemy as sa
from alembic import op

revision = "20261020_16"
down_revision = "20261018_15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "isar_players",
        sa.Column("source_id", sa.String(36), primary_key=True),
        sa.Column(
            "player_id", sa.Integer, sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False
        ),
        sa.UniqueConstraint("player_id"),
    )
    op.create_table(
        "isar_sessions",
        sa.Column("source_id", sa.String(36), primary_key=True),
        sa.Column(
            "session_id",
            sa.Integer,
            sa.ForeignKey("game_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.UniqueConstraint("session_id"),
    )
    op.create_table(
        "isar_games",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "source_session_id",
            sa.String(36),
            sa.ForeignKey("isar_sessions.source_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_number", sa.Integer, nullable=False),
        sa.Column(
            "round_id", sa.Integer, sa.ForeignKey("rounds.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("payload", sa.JSON, nullable=False),
        sa.UniqueConstraint("source_session_id", "source_number"),
        sa.UniqueConstraint("round_id"),
        sa.CheckConstraint("source_number > 0", name="ck_isar_game_number"),
    )


def downgrade() -> None:
    op.drop_table("isar_games")
    op.drop_table("isar_sessions")
    op.drop_table("isar_players")
