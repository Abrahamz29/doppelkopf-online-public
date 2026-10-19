"""Add game-session revisions and portable live-state views."""
import sqlalchemy as sa
from alembic import op

from doppelkopf_app.infrastructure.state_views import ROUND_VIEW_SQL, SESSION_VIEW_SQL

revision = "20261013_11"
down_revision = "20261013_10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("game_sessions", sa.Column("revision", sa.Integer(), nullable=False,
                                            server_default=sa.text("0")))
    op.execute(SESSION_VIEW_SQL)
    op.execute(ROUND_VIEW_SQL)


def downgrade() -> None:
    op.execute("DROP VIEW round_state_v1")
    op.execute("DROP VIEW session_state_v1")
    op.drop_column("game_sessions", "revision")
