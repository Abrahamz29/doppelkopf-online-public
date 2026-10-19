"""Persist per-player chart line patterns."""
import sqlalchemy as sa
from alembic import op

revision = "20261018_15"
down_revision = "20261018_14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column(
        "chart_line", sa.String(8), sa.CheckConstraint(
            "chart_line IS NULL OR chart_line IN ('solid', 'dashed', 'dotted', 'dashdot')",
            name="ck_players_chart_line",
        ), nullable=True,
    ))


def downgrade() -> None:
    op.drop_column("players", "chart_line")
