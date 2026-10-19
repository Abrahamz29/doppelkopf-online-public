"""Allow queued Bock games without changing existing scoring modes."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261013_10"
down_revision: str | None = "20261004_09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("game_sessions") as batch_op:
        batch_op.drop_constraint("ck_game_session_bock_counting", type_="check")
        batch_op.create_check_constraint(
            "ck_game_session_bock_counting",
            "bock_counting IN ('additive', 'multiplicative', 'append')",
        )
    _restore_sqlite_open_session_index()


def downgrade() -> None:
    if op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM game_sessions WHERE bock_counting = 'append'")
    ).scalar_one():
        raise RuntimeError("Downgrade nicht möglich: Spieltage mit Bockzählung Anhängen vorhanden.")
    with op.batch_alter_table("game_sessions") as batch_op:
        batch_op.drop_constraint("ck_game_session_bock_counting", type_="check")
        batch_op.create_check_constraint(
            "ck_game_session_bock_counting",
            "bock_counting IN ('additive', 'multiplicative')",
        )
    _restore_sqlite_open_session_index()


def _restore_sqlite_open_session_index() -> None:
    # SQLite batch recreation cannot reflect expression-based indexes.
    if op.get_bind().dialect.name == "sqlite":
        op.execute(sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_one_open_game_session "
            "ON game_sessions ((ended_at IS NULL)) WHERE ended_at IS NULL"
        ))
