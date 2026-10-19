"""Persist per-player chart colors without changing game data."""
import sqlalchemy as sa
from alembic import op

revision = "20261018_14"
down_revision = "20261014_13"
branch_labels = None
depends_on = None

COLOR_CHECK = (
    "chart_color IS NULL OR (length(chart_color) = 7 AND substr(chart_color, 1, 1) = '#' A"
    'ND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(re'
    "place(replace(replace(replace(replace(replace(substr(chart_color, 2), '0', ''), '1', "
    "''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), "
    "'A', ''), 'B', ''), 'C', ''), 'D', ''), 'E', ''), 'F', '') = '')"
)


def upgrade() -> None:
    # Column-level CHECK allows SQLite ADD/DROP COLUMN without rebuilding players
    # or disrupting the state views and foreign-key references.
    op.add_column("players", sa.Column(
        "chart_color", sa.String(7),
        sa.CheckConstraint(COLOR_CHECK, name="ck_players_chart_color"), nullable=True,
    ))


def downgrade() -> None:
    op.drop_column("players", "chart_color")
