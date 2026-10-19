"""Bundle PostgreSQL round persistence and state return in one call."""
from alembic import op

from doppelkopf_app.infrastructure.bundled_save import SAVE_ROUND_SQL

revision = "20261013_12"
down_revision = "20261013_11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(SAVE_ROUND_SQL)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION save_round_v1(jsonb)")
