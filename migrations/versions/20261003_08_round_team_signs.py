"""Persist the four seat-based team signs for each round."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_08"
down_revision: str | None = "20261003_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VALID_TEAM_SIGNS = (
    "'+++-', '++-+', '++--', '+-++', '+-+-', '+--+', '+---', "
    "'-+++', '-++-', '-+-+', '-+--', '--++', '--+-', '---+'"
)


def upgrade() -> None:
    with op.batch_alter_table("rounds") as batch_op:
        batch_op.add_column(sa.Column("team_signs", sa.String(length=4), nullable=True))
        batch_op.create_check_constraint(
            "ck_round_team_signs",
            f"team_signs IS NULL OR team_signs IN ({_VALID_TEAM_SIGNS})",
        )


def downgrade() -> None:
    with op.batch_alter_table("rounds") as batch_op:
        batch_op.drop_constraint("ck_round_team_signs", type_="check")
        batch_op.drop_column("team_signs")
