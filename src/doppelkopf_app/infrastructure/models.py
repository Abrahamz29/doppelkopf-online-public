from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from doppelkopf_app.infrastructure.database import Base

PLAYER_COLOR_CHECK = (
    "chart_color IS NULL OR (length(chart_color) = 7 AND substr(chart_color, 1, 1) = '#' A"
    'ND replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(re'
    "place(replace(replace(replace(replace(replace(substr(chart_color, 2), '0', ''), '1', "
    "''), '2', ''), '3', ''), '4', ''), '5', ''), '6', ''), '7', ''), '8', ''), '9', ''), "
    "'A', ''), 'B', ''), 'C', ''), 'D', ''), 'E', ''), 'F', '') = '')"
)


class PlayerRecord(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    chart_color: Mapped[str | None] = mapped_column(
        String(7), CheckConstraint(PLAYER_COLOR_CHECK, name="ck_players_chart_color"),
        nullable=True,
    )
    chart_line: Mapped[str | None] = mapped_column(
        String(8), CheckConstraint(
            "chart_line IS NULL OR chart_line IN ('solid', 'dashed', 'dotted', 'dashdot')",
            name="ck_players_chart_line",
        ), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    session_seats: Mapped[list["GameSessionPlayerRecord"]] = relationship(
        back_populates="player"
    )
    scores: Mapped[list["ScoreRecord"]] = relationship(back_populates="player")


class GameSessionRecord(Base):
    __table_args__ = (
        CheckConstraint(
            "bock_counting IN ('additive', 'multiplicative', 'append')",
            name="ck_game_session_bock_counting",
        ),
        Index(
            "uq_one_open_game_session",
            text("(ended_at IS NULL)"),
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
            sqlite_where=text("ended_at IS NULL"),
        ),
    )
    __tablename__ = "game_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    played_on: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(200))
    bock_counting: Mapped[str] = mapped_column(String(20), default="additive")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tempo_reset_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    start_dealer_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    next_dealer_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("players.id"), nullable=True
    )
    source_reference: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    rounds: Mapped[list["RoundRecord"]] = relationship(
        back_populates="game_session", cascade="all, delete-orphan"
    )
    players: Mapped[list["GameSessionPlayerRecord"]] = relationship(
        back_populates="game_session", cascade="all, delete-orphan"
    )
    seating_revisions: Mapped[list["SeatingRevisionRecord"]] = relationship(
        back_populates="game_session", cascade="all, delete-orphan"
    )


class GameSessionPlayerRecord(Base):
    __tablename__ = "game_session_players"
    __table_args__ = (
        UniqueConstraint("game_session_id", "seat", name="uq_game_session_seat"),
        UniqueConstraint("game_session_id", "player_id", name="uq_game_session_player"),
        CheckConstraint("seat BETWEEN 0 AND 3", name="ck_game_session_seat"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_session_id: Mapped[int] = mapped_column(ForeignKey("game_sessions.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    seat: Mapped[int] = mapped_column(Integer)
    game_session: Mapped[GameSessionRecord] = relationship(back_populates="players")
    player: Mapped[PlayerRecord] = relationship(back_populates="session_seats")


class SeatingRevisionRecord(Base):
    __tablename__ = "seating_revisions"
    __table_args__ = (
        UniqueConstraint(
            "game_session_id", "revision", name="uq_seating_revision_number"
        ),
        CheckConstraint("effective_from_sequence >= 1", name="ck_seating_effective_sequence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_session_id: Mapped[int] = mapped_column(ForeignKey("game_sessions.id"))
    revision: Mapped[int] = mapped_column(Integer)
    effective_from_sequence: Mapped[int] = mapped_column(Integer)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    game_session: Mapped[GameSessionRecord] = relationship(back_populates="seating_revisions")
    seats: Mapped[list["SeatingRevisionPlayerRecord"]] = relationship(
        back_populates="revision_record", cascade="all, delete-orphan"
    )


class SeatingRevisionPlayerRecord(Base):
    __tablename__ = "seating_revision_players"
    __table_args__ = (
        UniqueConstraint("revision_id", "seat", name="uq_seating_revision_seat"),
        UniqueConstraint("revision_id", "player_id", name="uq_seating_revision_player"),
        CheckConstraint("seat BETWEEN 0 AND 3", name="ck_seating_revision_seat"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    revision_id: Mapped[int] = mapped_column(ForeignKey("seating_revisions.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    seat: Mapped[int] = mapped_column(Integer)
    revision_record: Mapped[SeatingRevisionRecord] = relationship(back_populates="seats")
    player: Mapped[PlayerRecord] = relationship()


class RoundRecord(Base):
    __tablename__ = "rounds"
    __table_args__ = (
        UniqueConstraint("game_session_id", "sequence", name="uq_round_sequence"),
        CheckConstraint(
            "team_signs IS NULL OR team_signs IN "
            "('+++-', '++-+', '++--', '+-++', '+-+-', '+--+', '+---', "
            "'-+++', '-++-', '-+-+', '-+--', '--++', '--+-', '---+')",
            name="ck_round_team_signs",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    game_session_id: Mapped[int] = mapped_column(ForeignKey("game_sessions.id"))
    sequence: Mapped[int] = mapped_column(Integer)
    dealer_position: Mapped[int] = mapped_column(Integer)
    dealer_player_id: Mapped[int | None] = mapped_column(ForeignKey("players.id"), nullable=True)
    seating_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("seating_revisions.id"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    entry: Mapped[str] = mapped_column(String(80))
    declaring_party: Mapped[str] = mapped_column(String(10))
    active_bocks: Mapped[int] = mapped_column(Integer, default=0)
    scheduled_bocks: Mapped[int] = mapped_column(Integer, default=0)
    team_signs: Mapped[str | None] = mapped_column(String(4), nullable=True)
    source_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_seat_order: Mapped[str | None] = mapped_column(String(500), nullable=True)
    game_session: Mapped[GameSessionRecord] = relationship(back_populates="rounds")
    scores: Mapped[list["ScoreRecord"]] = relationship(
        back_populates="round", cascade="all, delete-orphan"
    )


class ScoreRecord(Base):
    __tablename__ = "scores"
    __table_args__ = (
        UniqueConstraint("round_id", "player_id", name="uq_round_player"),
        CheckConstraint("points BETWEEN -999 AND 999", name="ck_reasonable_points"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id"))
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"))
    points: Mapped[int] = mapped_column(Integer)
    round: Mapped[RoundRecord] = relationship(back_populates="scores")
    player: Mapped[PlayerRecord] = relationship(back_populates="scores")


class TempoResetRecord(Base):
    __tablename__ = "tempo_resets"

    id: Mapped[int] = mapped_column(primary_key=True)
    game_session_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"), index=True
    )
    reset_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class IsarPlayerRecord(Base):
    __tablename__ = "isar_players"
    source_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id", ondelete="CASCADE"), unique=True
    )


class IsarSessionRecord(Base):
    __tablename__ = "isar_sessions"
    source_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("game_sessions.id", ondelete="CASCADE"), unique=True
    )
    sha256: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class IsarGameRecord(Base):
    __tablename__ = "isar_games"
    __table_args__ = (
        UniqueConstraint("source_session_id", "source_number"),
        CheckConstraint("source_number > 0", name="ck_isar_game_number"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    source_session_id: Mapped[str] = mapped_column(
        ForeignKey("isar_sessions.source_id", ondelete="CASCADE")
    )
    source_number: Mapped[int] = mapped_column(Integer)
    round_id: Mapped[int | None] = mapped_column(
        ForeignKey("rounds.id", ondelete="SET NULL"), unique=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
