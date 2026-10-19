"""Add the per-session Bock counting mode."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_05"
down_revision: str | None = "20261002_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("game_sessions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "bock_counting",
                sa.String(length=20),
                nullable=False,
                server_default="multiplicative",
            )
        )
        batch_op.create_check_constraint(
            "ck_game_session_bock_counting",
            "bock_counting IN ('additive', 'multiplicative')",
        )


def downgrade() -> None:
    with op.batch_alter_table("game_sessions") as batch_op:
        batch_op.drop_constraint("ck_game_session_bock_counting", type_="check")
        batch_op.drop_column("bock_counting")
