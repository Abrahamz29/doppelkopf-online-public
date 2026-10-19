"""Add seating history, stable dealers, and round completion times."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261003_07"
down_revision: str | None = "20261003_06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    with op.batch_alter_table("game_sessions") as batch_op:
        batch_op.add_column(
            sa.Column("next_dealer_player_id", sa.Integer(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_game_sessions_next_dealer_player",
            "players",
            ["next_dealer_player_id"],
            ["id"],
        )
    index_exists = connection.execute(
        sa.text(
            "SELECT name FROM sqlite_master WHERE type = 'index' "
            "AND name = 'uq_one_open_game_session'"
        )
    ).scalar_one_or_none() if connection.dialect.name == "sqlite" else True
    if connection.dialect.name == "sqlite" and index_exists is None:
        op.create_index(
            "uq_one_open_game_session",
            "game_sessions",
            [sa.text("(ended_at IS NULL)")],
            unique=True,
            sqlite_where=sa.text("ended_at IS NULL"),
        )
    op.create_table(
        "seating_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("game_session_id", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("effective_from_sequence", sa.Integer(), nullable=False),
        sa.Column("changed_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "effective_from_sequence >= 1", name="ck_seating_effective_sequence"
        ),
        sa.ForeignKeyConstraint(["game_session_id"], ["game_sessions.id"]),
        sa.UniqueConstraint(
            "game_session_id", "revision", name="uq_seating_revision_number"
        ),
    )
    op.create_table(
        "seating_revision_players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("revision_id", sa.Integer(), nullable=False),
        sa.Column("player_id", sa.Integer(), nullable=False),
        sa.Column("seat", sa.Integer(), nullable=False),
        sa.CheckConstraint("seat BETWEEN 0 AND 3", name="ck_seating_revision_seat"),
        sa.ForeignKeyConstraint(["revision_id"], ["seating_revisions.id"]),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"]),
        sa.UniqueConstraint("revision_id", "seat", name="uq_seating_revision_seat"),
        sa.UniqueConstraint("revision_id", "player_id", name="uq_seating_revision_player"),
    )
    with op.batch_alter_table("rounds") as batch_op:
        batch_op.add_column(sa.Column("dealer_player_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("seating_revision_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("completed_at", sa.DateTime(), nullable=True))
        batch_op.create_foreign_key(
            "fk_rounds_dealer_player", "players", ["dealer_player_id"], ["id"]
        )
        batch_op.create_foreign_key(
            "fk_rounds_seating_revision",
            "seating_revisions",
            ["seating_revision_id"],
            ["id"],
        )

    sessions = connection.execute(
        sa.text(
            "SELECT id, start_dealer_position FROM game_sessions ORDER BY id"
        )
    ).mappings()
    for session in sessions:
        seats = list(
            connection.execute(
                sa.text(
                    "SELECT player_id, seat FROM game_session_players "
                    "WHERE game_session_id = :session_id ORDER BY seat"
                ),
                {"session_id": session["id"]},
            ).mappings()
        )
        if len(seats) != 4:
            continue
        revision_id = connection.execute(
            sa.text(
                "INSERT INTO seating_revisions "
                "(game_session_id, revision, effective_from_sequence, changed_at) "
                "VALUES (:session_id, 1, 1, CURRENT_TIMESTAMP) RETURNING id"
            ),
            {"session_id": session["id"]},
        ).scalar_one()
        for seat in seats:
            connection.execute(
                sa.text(
                    "INSERT INTO seating_revision_players (revision_id, player_id, seat) "
                    "VALUES (:revision_id, :player_id, :seat)"
                ),
                {
                    "revision_id": revision_id,
                    "player_id": seat["player_id"],
                    "seat": seat["seat"],
                },
            )
        start_position = session["start_dealer_position"]
        if start_position is not None and 0 <= start_position < 4:
            next_player_id = seats[start_position]["player_id"]
            round_count = connection.execute(
                sa.text("SELECT COUNT(*) FROM rounds WHERE game_session_id = :session_id"),
                {"session_id": session["id"]},
            ).scalar_one()
            next_player_id = seats[(start_position + round_count) % 4]["player_id"]
            connection.execute(
                sa.text(
                    "UPDATE game_sessions SET next_dealer_player_id = :player_id "
                    "WHERE id = :session_id"
                ),
                {"player_id": next_player_id, "session_id": session["id"]},
            )
        rounds = connection.execute(
            sa.text(
                "SELECT id, dealer_position FROM rounds WHERE game_session_id = :session_id"
            ),
            {"session_id": session["id"]},
        ).mappings()
        for item_round in rounds:
            dealer = seats[item_round["dealer_position"]]["player_id"]
            connection.execute(
                sa.text(
                    "UPDATE rounds SET dealer_player_id = :dealer, "
                    "seating_revision_id = :revision_id WHERE id = :round_id"
                ),
                {
                    "dealer": dealer,
                    "revision_id": revision_id,
                    "round_id": item_round["id"],
                },
            )


def downgrade() -> None:
    connection = op.get_bind()
    with op.batch_alter_table("rounds") as batch_op:
        batch_op.drop_constraint("fk_rounds_seating_revision", type_="foreignkey")
        batch_op.drop_constraint("fk_rounds_dealer_player", type_="foreignkey")
        batch_op.drop_column("completed_at")
        batch_op.drop_column("seating_revision_id")
        batch_op.drop_column("dealer_player_id")
    op.drop_table("seating_revision_players")
    op.drop_table("seating_revisions")
    with op.batch_alter_table("game_sessions") as batch_op:
        batch_op.drop_constraint("fk_game_sessions_next_dealer_player", type_="foreignkey")
        batch_op.drop_column("next_dealer_player_id")
    index_exists = connection.execute(
        sa.text(
            "SELECT name FROM sqlite_master WHERE type = 'index' "
            "AND name = 'uq_one_open_game_session'"
        )
    ).scalar_one_or_none() if connection.dialect.name == "sqlite" else True
    if connection.dialect.name == "sqlite" and index_exists is None:
        op.create_index(
            "uq_one_open_game_session",
            "game_sessions",
            [sa.text("(ended_at IS NULL)")],
            unique=True,
            sqlite_where=sa.text("ended_at IS NULL"),
        )
