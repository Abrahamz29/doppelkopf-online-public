"""Keep all tempo reset boundaries, seeding the last known reset."""
import sqlalchemy as sa
from alembic import op

revision = "20261014_13"
down_revision = "20261013_12"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tempo_resets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_session_id", sa.Integer(),
                  sa.ForeignKey("game_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reset_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_tempo_resets_game_session_id", "tempo_resets", ["game_session_id"])
    op.execute("INSERT INTO tempo_resets (game_session_id, reset_at) "
               "SELECT id, tempo_reset_at FROM game_sessions WHERE tempo_reset_at IS NOT NULL")


def downgrade() -> None:
    # The existing tempo_reset_at column retains the latest boundary for older code.
    op.drop_table("tempo_resets")
