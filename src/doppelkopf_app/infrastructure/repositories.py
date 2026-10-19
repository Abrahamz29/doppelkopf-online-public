from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from types import SimpleNamespace
from typing import Any, Literal, cast

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from doppelkopf_app.application.services import (
    DuplicatePlayerError,
    GameSessionAlreadyEndedError,
    GameSessionConfigurationError,
    GameSessionNotFoundError,
    GameSessionState,
    GameSessionSummary,
    OpenGameSessionExistsError,
    OverviewCounts,
    PlayerInUseError,
    PlayerNotFoundError,
    PlayerSummary,
    RoundNotFoundError,
    RoundReplacement,
    RoundSummary,
    SaveOutcomeUnknownError,
    SeatingRevisionSummary,
)
from doppelkopf_app.domain.entities import BockCounting, GameSession, Player
from doppelkopf_app.domain.scoring import DeclaringParty, ParsedScoreEntry
from doppelkopf_app.infrastructure.database import transaction
from doppelkopf_app.infrastructure.models import (
    GameSessionPlayerRecord,
    GameSessionRecord,
    PlayerRecord,
    RoundRecord,
    ScoreRecord,
    SeatingRevisionPlayerRecord,
    SeatingRevisionRecord,
    TempoResetRecord,
)
from doppelkopf_app.infrastructure.postgres_pipeline import save_round_pipeline
from doppelkopf_app.infrastructure.state_views import round_view, session_view


class SqlAlchemyDoppelkopfRepository:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def add_player(self, player: Player) -> None:
        try:
            with transaction(self._factory) as db:
                db.add(PlayerRecord(name=player.name))
        except IntegrityError as error:
            raise DuplicatePlayerError(player.name) from error

    def update_player(self, player_id: int, player: Player) -> None:
        try:
            with transaction(self._factory) as db:
                record = db.get(PlayerRecord, player_id)
                if record is None:
                    raise PlayerNotFoundError(player_id)
                if record.name == player.name:
                    return
                self._invalidate_player_sessions(db, player_id)
                record.name = player.name
        except IntegrityError as error:
            raise DuplicatePlayerError(player.name) from error

    def set_player_chart_color(self, player_id: int, color: str | None) -> None:
        """Save a player color without changing their line preference."""
        self._set_player_chart_preference(player_id, "chart_color", color)

    def set_player_chart_line(self, player_id: int, line: str | None) -> None:
        """Save a player line preference without changing their color."""
        self._set_player_chart_preference(player_id, "chart_line", line)

    def set_player_chart_style(
        self, player_id: int, color: str | None, line: str | None,
    ) -> None:
        """Save both preferences and invalidate affected live sessions atomically."""
        with transaction(self._factory) as db:
            player = db.get(PlayerRecord, player_id)
            if player is None:
                raise PlayerNotFoundError(player_id)
            if (player.chart_color, player.chart_line) == (color, line):
                return
            self._invalidate_player_sessions(db, player_id)
            player.chart_color = color
            player.chart_line = line

    def _set_player_chart_preference(
        self, player_id: int, field: Literal["chart_color", "chart_line"], value: str | None,
    ) -> None:
        """Invalidate affected live sessions in the same preference transaction."""
        with transaction(self._factory) as db:
            player = db.get(PlayerRecord, player_id)
            if player is None:
                raise PlayerNotFoundError(player_id)
            if getattr(player, field) == value:
                return
            self._invalidate_player_sessions(db, player_id)
            setattr(player, field, value)

    @staticmethod
    def _invalidate_player_sessions(db: Session, player_id: int) -> None:
        """Lock and invalidate open sessions displaying this player's data."""
        current_seats = select(GameSessionPlayerRecord.game_session_id).where(
            GameSessionPlayerRecord.player_id == player_id
        )
        previous_seats = (
            select(SeatingRevisionRecord.game_session_id)
            .join(SeatingRevisionPlayerRecord)
            .where(SeatingRevisionPlayerRecord.player_id == player_id)
        )
        db.execute(
            update(GameSessionRecord).where(
                GameSessionRecord.ended_at.is_(None),
                GameSessionRecord.id.in_(current_seats.union(previous_seats)),
            ).values(revision=GameSessionRecord.revision + 1)
        )

    def delete_player(self, player_id: int) -> None:
        with transaction(self._factory) as db:
            if db.get(PlayerRecord, player_id) is None:
                raise PlayerNotFoundError(player_id)
            references = (
                db.scalar(
                    select(func.count()).select_from(GameSessionPlayerRecord).where(
                        GameSessionPlayerRecord.player_id == player_id
                    )
                )
                or db.scalar(
                    select(func.count()).select_from(SeatingRevisionPlayerRecord).where(
                        SeatingRevisionPlayerRecord.player_id == player_id
                    )
                )
                or db.scalar(
                    select(func.count()).select_from(ScoreRecord).where(
                        ScoreRecord.player_id == player_id
                    )
                )
                or db.scalar(
                    select(func.count()).select_from(RoundRecord).where(
                        RoundRecord.dealer_player_id == player_id
                    )
                )
                or db.scalar(
                    select(func.count()).select_from(GameSessionRecord).where(
                        GameSessionRecord.next_dealer_player_id == player_id
                    )
                )
            )
            if references:
                raise PlayerInUseError(player_id)
            db.execute(delete(PlayerRecord).where(PlayerRecord.id == player_id))

    def list_player_names(self) -> list[str]:
        with transaction(self._factory) as db:
            return list(db.scalars(select(PlayerRecord.name).order_by(PlayerRecord.name)))

    def list_players(self) -> list[PlayerSummary]:
        with transaction(self._factory) as db:
            rows = db.execute(
                select(PlayerRecord.id, PlayerRecord.name,
                       PlayerRecord.chart_color, PlayerRecord.chart_line)
                .order_by(PlayerRecord.name)
            )
            return [
                PlayerSummary(row.id, row.name, row.chart_color, row.chart_line) for row in rows
            ]

    def add_game_session(self, game_session: GameSession) -> None:
        try:
            with transaction(self._factory) as db:
                db.add(
                    GameSessionRecord(
                        played_on=game_session.played_on,
                        title=game_session.title,
                        bock_counting=game_session.bock_counting.value,
                    )
                )
        except IntegrityError as error:
            raise OpenGameSessionExistsError(
                "Beende zuerst den offenen Spieltag, bevor du einen neuen anlegst."
            ) from error

    def add_configured_game_session(
        self,
        game_session: GameSession,
        player_ids: tuple[int, int, int, int],
        dealer_position: int,
        changed_at: datetime,
    ) -> int:
        try:
            with transaction(self._factory) as db:
                record = GameSessionRecord(
                    played_on=game_session.played_on,
                    title=game_session.title,
                    bock_counting=game_session.bock_counting.value,
                )
                db.add(record)
                db.flush()
                self._write_seating(
                    db, record, player_ids, dealer_position, changed_at, allow_player_change=True
                )
                return record.id
        except IntegrityError as error:
            raise OpenGameSessionExistsError(
                "Beende zuerst den offenen Spieltag, bevor du einen neuen anlegst."
            ) from error

    def list_game_sessions(self) -> list[GameSessionSummary]:
        with transaction(self._factory) as db:
            round_count = (
                select(func.count(RoundRecord.id))
                .where(RoundRecord.game_session_id == GameSessionRecord.id)
                .correlate(GameSessionRecord)
                .scalar_subquery()
            )
            rows = db.execute(
                select(
                    GameSessionRecord.id,
                    GameSessionRecord.played_on,
                    GameSessionRecord.title,
                    GameSessionRecord.ended_at,
                    GameSessionRecord.bock_counting,
                    round_count.label("round_count"),
                    GameSessionRecord.tempo_reset_at,
                ).order_by(
                    GameSessionRecord.played_on.desc()
                )
            )
            return [
                GameSessionSummary(
                    row.id,
                    row.played_on,
                    row.title,
                    row.ended_at,
                    BockCounting(row.bock_counting),
                    int(row.round_count),
                    row.tempo_reset_at,
                )
                for row in rows
            ]

    def end_game_session(self, game_session_id: int, ended_at: datetime) -> None:
        with transaction(self._factory) as db:
            result = cast(
                CursorResult[Any],
                db.execute(
                    update(GameSessionRecord)
                    .where(
                        GameSessionRecord.id == game_session_id,
                        GameSessionRecord.ended_at.is_(None),
                    )
                    .values(ended_at=ended_at, revision=GameSessionRecord.revision + 1)
                ),
            )
            if result.rowcount == 1:
                return
            existing = db.scalar(
                select(GameSessionRecord.ended_at).where(GameSessionRecord.id == game_session_id)
            )
            if existing is None:
                exists = db.scalar(
                    select(GameSessionRecord.id).where(GameSessionRecord.id == game_session_id)
                )
                if exists is None:
                    raise GameSessionNotFoundError(game_session_id)
            raise GameSessionAlreadyEndedError(game_session_id)

    def configure_game_session(
        self, game_session_id: int, player_ids: tuple[int, int, int, int], dealer_position: int
    ) -> None:
        with transaction(self._factory) as db:
            session = self._claim_session(db, game_session_id)
            if session is None:
                raise GameSessionNotFoundError(game_session_id)
            if session.ended_at is not None:
                raise GameSessionAlreadyEndedError(game_session_id)
            if db.scalar(
                select(func.count()).select_from(RoundRecord).where(
                    RoundRecord.game_session_id == game_session_id
                )
            ):
                raise GameSessionConfigurationError(
                    "Die Sitzordnung kann nach dem ersten Spiel nicht mehr geändert werden."
                )
            self._write_seating(
                db, session, player_ids, dealer_position, datetime.utcnow(), True
            )

    def change_seating(
        self,
        game_session_id: int,
        player_ids: tuple[int, int, int, int],
        changed_at: datetime,
    ) -> None:
        with transaction(self._factory) as db:
            session = self._claim_session(db, game_session_id)
            if session is None:
                raise GameSessionNotFoundError(game_session_id)
            if session.ended_at is not None:
                raise GameSessionAlreadyEndedError(game_session_id)
            current = tuple(
                db.scalars(
                    select(GameSessionPlayerRecord.player_id)
                    .where(GameSessionPlayerRecord.game_session_id == game_session_id)
                    .order_by(GameSessionPlayerRecord.seat)
                )
            )
            has_rounds = bool(
                db.scalar(
                    select(func.count()).select_from(RoundRecord).where(
                        RoundRecord.game_session_id == game_session_id
                    )
                )
            )
            if has_rounds and set(current) != set(player_ids):
                raise GameSessionConfigurationError(
                    "Nach dem ersten Spiel dürfen nur die vorhandenen Spieler umsortiert werden."
                )
            dealer_position = (
                player_ids.index(session.next_dealer_player_id)
                if session.next_dealer_player_id in player_ids
                else 0
            )
            self._write_seating(
                db, session, player_ids, dealer_position, changed_at, not has_rounds
            )

    def set_next_dealer(self, game_session_id: int, player_id: int) -> None:
        with transaction(self._factory) as db:
            session = self._claim_session(db, game_session_id)
            if session is None:
                raise GameSessionNotFoundError(game_session_id)
            if session.ended_at is not None:
                raise GameSessionAlreadyEndedError(game_session_id)
            participants = set(
                db.scalars(
                    select(GameSessionPlayerRecord.player_id).where(
                        GameSessionPlayerRecord.game_session_id == game_session_id
                    )
                )
            )
            if player_id not in participants:
                raise GameSessionConfigurationError("Der Geber muss am Spieltag teilnehmen.")
            session.next_dealer_player_id = player_id

    def list_tempo_resets(self, game_session_id: int) -> tuple[datetime, ...]:
        """Load recorded tempo boundaries in chronological order."""
        with self._factory() as db:
            return tuple(db.scalars(
                select(TempoResetRecord.reset_at)
                .where(TempoResetRecord.game_session_id == game_session_id)
                .order_by(TempoResetRecord.reset_at)
            ))

    def reset_tempo(self, game_session_id: int, reset_at: datetime) -> None:
        with transaction(self._factory) as db:
            result = cast(
                CursorResult[Any],
                db.execute(
                    update(GameSessionRecord)
                    .where(
                        GameSessionRecord.id == game_session_id,
                        GameSessionRecord.ended_at.is_(None),
                    )
                    .values(tempo_reset_at=reset_at, revision=GameSessionRecord.revision + 1)
                ),
            )
            if result.rowcount == 1:
                db.add(TempoResetRecord(game_session_id=game_session_id, reset_at=reset_at))
                return
            existing = db.scalar(
                select(GameSessionRecord.ended_at).where(
                    GameSessionRecord.id == game_session_id
                )
            )
            if existing is None:
                exists = db.scalar(
                    select(GameSessionRecord.id).where(
                        GameSessionRecord.id == game_session_id
                    )
                )
                if exists is None:
                    raise GameSessionNotFoundError(game_session_id)
            raise GameSessionAlreadyEndedError(game_session_id)

    def delete_game_session(self, game_session_id: int) -> None:
        with transaction(self._factory) as db:
            session = self._claim_session(db, game_session_id)
            if session is None:
                raise GameSessionNotFoundError(game_session_id)
            round_ids = list(
                db.scalars(
                    select(RoundRecord.id).where(
                        RoundRecord.game_session_id == game_session_id
                    )
                )
            )
            if round_ids:
                changed_totals = (
                    select(ScoreRecord.player_id)
                    .where(ScoreRecord.round_id.in_(round_ids))
                    .group_by(ScoreRecord.player_id)
                    .having(func.sum(ScoreRecord.points) != 0)
                )
                affected_sessions = select(GameSessionPlayerRecord.game_session_id).where(
                    GameSessionPlayerRecord.player_id.in_(changed_totals)
                )
                db.execute(
                    update(GameSessionRecord).where(
                        GameSessionRecord.ended_at.is_(None),
                        GameSessionRecord.id != game_session_id,
                        GameSessionRecord.id.in_(affected_sessions),
                    ).values(revision=GameSessionRecord.revision + 1)
                )
                db.execute(delete(ScoreRecord).where(ScoreRecord.round_id.in_(round_ids)))
                db.execute(delete(RoundRecord).where(RoundRecord.id.in_(round_ids)))
            revision_ids = list(
                db.scalars(
                    select(SeatingRevisionRecord.id).where(
                        SeatingRevisionRecord.game_session_id == game_session_id
                    )
                )
            )
            if revision_ids:
                db.execute(
                    delete(SeatingRevisionPlayerRecord).where(
                        SeatingRevisionPlayerRecord.revision_id.in_(revision_ids)
                    )
                )
                db.execute(
                    delete(SeatingRevisionRecord).where(
                        SeatingRevisionRecord.id.in_(revision_ids)
                    )
                )
            db.execute(
                delete(GameSessionPlayerRecord).where(
                    GameSessionPlayerRecord.game_session_id == game_session_id
                )
            )
            db.execute(delete(TempoResetRecord).where(
                TempoResetRecord.game_session_id == game_session_id
            ))
            db.delete(session)

    @staticmethod
    def _write_seating(
        db: Session,
        session: GameSessionRecord,
        player_ids: tuple[int, int, int, int],
        dealer_position: int,
        changed_at: datetime,
        allow_player_change: bool,
    ) -> None:
        existing_players = set(
            db.scalars(select(PlayerRecord.id).where(PlayerRecord.id.in_(player_ids)))
        )
        if existing_players != set(player_ids):
            raise GameSessionConfigurationError("Mindestens ein gewählter Spieler existiert nicht.")
        current = set(
            db.scalars(
                select(GameSessionPlayerRecord.player_id).where(
                    GameSessionPlayerRecord.game_session_id == session.id
                )
            )
        )
        if current and not allow_player_change and current != set(player_ids):
            raise GameSessionConfigurationError(
                "Nach dem ersten Spiel dürfen nur die vorhandenen Spieler umsortiert werden."
            )
        db.execute(
            delete(GameSessionPlayerRecord).where(
                GameSessionPlayerRecord.game_session_id == session.id
            )
        )
        db.add_all(
            GameSessionPlayerRecord(game_session_id=session.id, player_id=player_id, seat=seat)
            for seat, player_id in enumerate(player_ids)
        )
        revision_number = (
            db.scalar(
                select(func.max(SeatingRevisionRecord.revision)).where(
                    SeatingRevisionRecord.game_session_id == session.id
                )
            )
            or 0
        ) + 1
        sequence = (
            db.scalar(
                select(func.max(RoundRecord.sequence)).where(
                    RoundRecord.game_session_id == session.id
                )
            )
            or 0
        ) + 1
        revision = SeatingRevisionRecord(
            game_session_id=session.id,
            revision=revision_number,
            effective_from_sequence=sequence,
            changed_at=changed_at,
        )
        db.add(revision)
        db.flush()
        db.add_all(
            SeatingRevisionPlayerRecord(
                revision_id=revision.id, player_id=player_id, seat=seat
            )
            for seat, player_id in enumerate(player_ids)
        )
        session.start_dealer_position = dealer_position
        session.next_dealer_player_id = player_ids[dealer_position]

    def get_game_session_state(self, game_session_id: int) -> GameSessionState:
        states = self.list_game_session_states((game_session_id,))
        if not states:
            raise GameSessionNotFoundError(game_session_id)
        return states[0]

    def list_seating_revisions(
        self, game_session_id: int
    ) -> list[SeatingRevisionSummary]:
        with transaction(self._factory) as db:
            rows = list(
                db.execute(
                    select(
                        SeatingRevisionRecord.id.label("revision_id"),
                        SeatingRevisionRecord.revision,
                        SeatingRevisionRecord.effective_from_sequence,
                        SeatingRevisionRecord.changed_at,
                        SeatingRevisionPlayerRecord.seat,
                        PlayerRecord.id.label("player_id"),
                        PlayerRecord.name,
                    )
                    .join(
                        SeatingRevisionPlayerRecord,
                        SeatingRevisionPlayerRecord.revision_id == SeatingRevisionRecord.id,
                    )
                    .join(PlayerRecord, PlayerRecord.id == SeatingRevisionPlayerRecord.player_id)
                    .where(SeatingRevisionRecord.game_session_id == game_session_id)
                    .order_by(
                        SeatingRevisionRecord.revision,
                        SeatingRevisionPlayerRecord.seat,
                    )
                )
            )
            grouped: dict[int, list[Any]] = defaultdict(list)
            for row in rows:
                grouped[row.revision_id].append(row)
            result: list[SeatingRevisionSummary] = []
            for revision_rows in grouped.values():
                if len(revision_rows) != 4:
                    continue
                first = revision_rows[0]
                players = tuple(
                    PlayerSummary(row.player_id, row.name) for row in revision_rows
                )
                result.append(
                    SeatingRevisionSummary(
                        first.revision,
                        first.effective_from_sequence,
                        first.changed_at,
                        cast(
                            tuple[
                                PlayerSummary,
                                PlayerSummary,
                                PlayerSummary,
                                PlayerSummary,
                            ],
                            players,
                        ),
                    )
                )
            return result

    def get_game_session_revision(self, game_session_id: int) -> int | None:
        """Read only the change token; absence also invalidates a rendered state."""
        statement = select(GameSessionRecord.revision).where(
            GameSessionRecord.id == game_session_id
        )
        engine = self._factory.kw["bind"]
        if engine.dialect.name == "postgresql":
            # A single read needs no multi-statement snapshot transaction.
            with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
                return cast(int | None, connection.scalar(statement))
        with transaction(self._factory) as db:
            return db.scalar(statement)

    def get_open_game_session_state(self) -> GameSessionState | None:
        """Load the open session directly, without a separate session-list transaction."""
        with transaction(self._factory, snapshot=True) as db:
            states = self._load_states(db, None)
            if len(states) > 1:
                raise GameSessionConfigurationError("Es gibt mehrere offene Spieltage.")
            return states[0] if states else None

    def list_game_session_states(
        self, game_session_ids: Sequence[int]
    ) -> list[GameSessionState]:
        """Read both views in a consistent database snapshot."""
        ids = tuple(dict.fromkeys(game_session_ids))
        if not ids:
            return []
        with transaction(self._factory, snapshot=True) as db:
            return self._load_states(db, ids)

    @staticmethod
    def _load_states(db: Session, ids: tuple[int, ...] | None) -> list[GameSessionState]:
        headers = list(db.execute(
            select(session_view).where(
                session_view.c.ended_at.is_(None) if ids is None
                else session_view.c.session_id.in_(ids)
            ).order_by(session_view.c.session_id, session_view.c.seat)
        ).mappings())
        requested = tuple(dict.fromkeys(r.session_id for r in headers)) if ids is None else ids
        if not requested:
            return []
        rows = list(db.execute(select(round_view).where(
            round_view.c.session_id.in_(requested)
        ).order_by(round_view.c.session_id, round_view.c.sequence, round_view.c.seat)).mappings())
        return SqlAlchemyDoppelkopfRepository._states_from_rows(headers, rows, requested)

    @staticmethod
    def _states_from_rows(
        headers: Sequence[Any], rows: Sequence[Any], requested: tuple[int, ...],
    ) -> list[GameSessionState]:
        by_session: dict[int, list[Any]] = defaultdict(list)
        for row in headers:
            by_session[row.session_id].append(row)
        for session_id in requested:
            if session_id not in by_session:
                raise GameSessionNotFoundError(session_id)
        by_round: dict[int, list[Any]] = defaultdict(list)
        for row in rows:
            by_round[row.round_id].append(row)
        rounds: dict[int, list[RoundSummary]] = defaultdict(list)
        for group in by_round.values():
            row = group[0]
            players = tuple(PlayerSummary(r.player_id, r.player_name)
                            for r in group if r.player_id is not None)
            points = [0, 0, 0, 0]
            for r in group:
                if r.seat is not None:
                    points[r.seat] = int(r.points)
            rounds[row.session_id].append(RoundSummary(
                row.round_id, row.sequence, row.dealer_position, row.entry,
                DeclaringParty(row.declaring_party), row.active_bocks, row.scheduled_bocks,
                cast(tuple[int, int, int, int], tuple(points)),
                BockCounting(by_session[row.session_id][0].bock_counting),
                row.source_row, row.source_seat_order, row.dealer_player_id, players,
                row.completed_at,
                cast(tuple[str, str, str, str], tuple(row.team_signs)) if row.team_signs else None,
            ))
        result = []
        for session_id in requested:
            group = by_session[session_id]
            row = group[0]
            players = tuple(PlayerSummary(r.player_id, r.player_name)
                            for r in group if r.player_id is not None)
            totals = [int(r.overall_points) for r in group if r.player_id is not None]
            totals += [0] * (4 - len(totals))
            result.append(GameSessionState(
                GameSessionSummary(row.session_id, row.played_on, row.title, row.ended_at,
                                   BockCounting(row.bock_counting),
                                   tempo_reset_at=row.tempo_reset_at),
                players, row.start_dealer_position, tuple(rounds[session_id]),
                cast(tuple[int, int, int, int], tuple(totals)), row.next_dealer_player_id,
                revision=row.revision,
            ))
        return result

    @staticmethod
    def _claim_session(
        db: Session, game_session_id: int, expected_revision: int | None = None,
    ) -> GameSessionRecord:
        """Lock the parent row and invalidate stale readers before changing children."""
        statement = update(GameSessionRecord).where(GameSessionRecord.id == game_session_id)
        if expected_revision is not None:
            statement = statement.where(GameSessionRecord.revision == expected_revision)
        record = db.scalar(statement.values(revision=GameSessionRecord.revision + 1)
                           .returning(GameSessionRecord))
        if record is None:
            if db.get(GameSessionRecord, game_session_id) is None:
                raise GameSessionNotFoundError(game_session_id)
            raise GameSessionConfigurationError(
                "Der Spielstand wurde zwischenzeitlich aktualisiert. "
                "Bitte prüfe die aktuelle Anzeige und speichere erneut."
            )
        return record

    def add_round(
        self,
        game_session_id: int,
        parsed: ParsedScoreEntry,
        entry: str,
        dealer_position: int,
        active_bocks: int,
        completed_at: datetime | None = None,
        *,
        expected_sequence: int | None = None,
        expected_player_ids: tuple[int, int, int, int] | None = None,
        expected_dealer_player_id: int | None = None,
        expected_revision: int | None = None,
    ) -> GameSessionState:
        if self._factory.kw["bind"].dialect.name == "postgresql":
            return self._add_round_postgres({
                "session_id": game_session_id, "revision": expected_revision,
                "sequence": expected_sequence, "player_ids": expected_player_ids,
                "dealer_id": expected_dealer_player_id, "dealer_position": dealer_position,
                "completed_at": (completed_at or datetime.utcnow()).isoformat(),
                "entry": entry, "declaring_party": parsed.declaring_party.value,
                "active_bocks": active_bocks, "scheduled_bocks": parsed.scheduled_bocks,
                "team_signs": "".join(parsed.team_signs) if parsed.team_signs else None,
                "points": parsed.points,
            })
        with transaction(self._factory, snapshot=True) as db:
            session = self._claim_session(db, game_session_id, expected_revision)
            next_sequence = (
                select(func.coalesce(func.max(RoundRecord.sequence), 0) + 1)
                .where(RoundRecord.game_session_id == game_session_id)
                .scalar_subquery()
            )
            latest_revision = (
                select(SeatingRevisionRecord.id)
                .where(SeatingRevisionRecord.game_session_id == game_session_id)
                .order_by(SeatingRevisionRecord.revision.desc())
                .limit(1)
                .scalar_subquery()
            )
            context_rows = list(
                db.execute(
                    select(
                        GameSessionRecord,
                        GameSessionPlayerRecord.player_id,
                        next_sequence.label("next_sequence"),
                        latest_revision.label("seating_revision_id"),
                    )
                    .outerjoin(
                        GameSessionPlayerRecord,
                        GameSessionPlayerRecord.game_session_id == GameSessionRecord.id,
                    )
                    .where(GameSessionRecord.id == game_session_id)
                    .order_by(GameSessionPlayerRecord.seat)
                )
            )
            if not context_rows:
                raise GameSessionNotFoundError(game_session_id)
            if session.ended_at is not None:
                raise GameSessionAlreadyEndedError(game_session_id)
            player_ids = [row.player_id for row in context_rows if row.player_id is not None]
            if len(player_ids) != 4:
                raise GameSessionConfigurationError(
                    "Der Spieltag hat keine vollständige Sitzordnung."
                )
            sequence = int(context_rows[0].next_sequence)
            seating_revision_id = context_rows[0].seating_revision_id
            dealer_player_id = session.next_dealer_player_id
            if dealer_player_id not in player_ids:
                dealer_player_id = player_ids[dealer_position]
            if (
                (expected_sequence is not None and sequence != expected_sequence)
                or (
                    expected_player_ids is not None
                    and tuple(player_ids) != expected_player_ids
                )
                or (
                    expected_dealer_player_id is not None
                    and dealer_player_id != expected_dealer_player_id
                )
            ):
                raise GameSessionConfigurationError(
                    "Der Spielstand wurde zwischenzeitlich aktualisiert. "
                    "Bitte prüfe die aktuelle Anzeige und speichere erneut."
                )
            actual_dealer_position = player_ids.index(dealer_player_id)
            round_record = RoundRecord(
                game_session_id=game_session_id,
                sequence=sequence,
                dealer_position=actual_dealer_position,
                dealer_player_id=dealer_player_id,
                seating_revision_id=seating_revision_id,
                completed_at=completed_at or datetime.utcnow(),
                entry=entry,
                declaring_party=parsed.declaring_party.value,
                active_bocks=active_bocks,
                scheduled_bocks=parsed.scheduled_bocks,
                team_signs=("".join(parsed.team_signs) if parsed.team_signs else None),
            )
            db.add(round_record)
            db.flush()
            db.execute(
                insert(ScoreRecord),
                [
                    {"round_id": round_record.id, "player_id": player_id, "points": points}
                    for player_id, points in zip(player_ids, parsed.points, strict=True)
                ],
            )
            session.next_dealer_player_id = player_ids[(actual_dealer_position + 1) % 4]
            db.flush()
            result = self._load_states(db, (game_session_id,))[0]
        return result

    def _add_round_postgres(self, payload: dict[str, Any]) -> GameSessionState:
        """Return the bundled snapshot only after the transaction is committed."""
        sid = int(payload["session_id"])
        try:
            data = save_round_pipeline(self._factory.kw["bind"], payload)
        except DBAPIError as error:
            code = getattr(error.orig, "sqlstate", None)
            if code == "DK001":
                raise GameSessionNotFoundError(sid) from error
            if code == "DK002":
                raise GameSessionAlreadyEndedError(sid) from error
            if code in {"DK003", "40001", "40P01"}:
                raise GameSessionConfigurationError(
                    "Der Spielstand wurde zwischenzeitlich aktualisiert oder ist unvollständig. "
                    "Bitte prüfe die aktuelle Anzeige und speichere erneut."
                ) from error
            raise
        try:
            groups = []
            for key in ("headers", "rounds"):
                values = []
                for row in data[key]:
                    for column in ("ended_at", "tempo_reset_at", "completed_at"):
                        if row.get(column) is not None:
                            row[column] = datetime.fromisoformat(row[column])
                    if row.get("played_on") is not None:
                        row["played_on"] = date.fromisoformat(row["played_on"])
                    values.append(SimpleNamespace(**row))
                groups.append(values)
            return self._states_from_rows(groups[0], groups[1], (sid,))[0]
        except (KeyError, TypeError, ValueError, IndexError, GameSessionNotFoundError) as error:
            raise SaveOutcomeUnknownError(
                "Das Spiel wurde gespeichert, aber der Rückgabestand konnte nicht "
                "angezeigt werden. "
                "Bitte prüfe die aktualisierte Spielliste und speichere nicht erneut."
            ) from error

    def delete_last_round(
        self, game_session_id: int, *, expected_revision: int | None = None
    ) -> None:
        with transaction(self._factory) as db:
            session = self._claim_session(db, game_session_id, expected_revision)
            if session is None:
                raise GameSessionNotFoundError(game_session_id)
            if session.ended_at is not None:
                raise GameSessionAlreadyEndedError(game_session_id)
            last_round = db.scalar(
                select(RoundRecord)
                .where(RoundRecord.game_session_id == game_session_id)
                .order_by(RoundRecord.sequence.desc())
                .limit(1)
            )
            if last_round is None:
                raise RoundNotFoundError(game_session_id)
            session.next_dealer_player_id = (
                last_round.dealer_player_id
                or list(
                    db.scalars(
                        select(GameSessionPlayerRecord.player_id)
                        .where(GameSessionPlayerRecord.game_session_id == game_session_id)
                        .order_by(GameSessionPlayerRecord.seat)
                    )
                )[last_round.dealer_position]
            )
            db.delete(last_round)

    def delete_round(
        self,
        game_session_id: int,
        round_id: int,
        expected_entry: str,
        replacements: Sequence[RoundReplacement],
        *, expected_revision: int | None = None,
    ) -> None:
        """Delete and recalculate a round history atomically."""
        with transaction(self._factory) as db:
            game_session = self._claim_session(db, game_session_id, expected_revision)
            if game_session is None:
                raise GameSessionNotFoundError(game_session_id)
            if game_session.ended_at is not None:
                raise GameSessionAlreadyEndedError(game_session_id)

            ordered_rounds = list(
                db.scalars(
                    select(RoundRecord)
                    .where(RoundRecord.game_session_id == game_session_id)
                    .order_by(RoundRecord.sequence)
                )
            )
            round_records = {item.id: item for item in ordered_rounds}
            deleted_round = round_records.get(round_id)
            replacement_ids = {item.round_id for item in replacements}
            entries_are_current = all(
                round_records[item.round_id].entry == item.expected_entry
                for item in replacements
                if item.round_id in round_records
            )
            if (
                deleted_round is None
                or deleted_round.entry != expected_entry
                or replacement_ids | {round_id} != set(round_records)
                or not entries_are_current
            ):
                raise GameSessionConfigurationError(
                    "Der Spieltag hat sich während des Löschens geändert."
                )

            was_last_round = deleted_round.sequence == ordered_rounds[-1].sequence
            if was_last_round:
                game_session.next_dealer_player_id = (
                    deleted_round.dealer_player_id
                    or list(
                        db.scalars(
                            select(GameSessionPlayerRecord.player_id)
                            .where(
                                GameSessionPlayerRecord.game_session_id
                                == game_session_id
                            )
                            .order_by(GameSessionPlayerRecord.seat)
                        )
                    )[deleted_round.dealer_position]
                )

            deleted_sequence = deleted_round.sequence
            db.delete(deleted_round)
            db.flush()
            for item in ordered_rounds:
                if item.id != round_id and item.sequence > deleted_sequence:
                    item.sequence -= 1
                    db.flush()
            for revision in db.scalars(
                select(SeatingRevisionRecord).where(
                    SeatingRevisionRecord.game_session_id == game_session_id,
                    SeatingRevisionRecord.effective_from_sequence > deleted_sequence,
                )
            ):
                revision.effective_from_sequence -= 1

            if not replacements:
                return
            score_records = {
                (score.round_id, score.player_id): score
                for score in db.scalars(
                    select(ScoreRecord).where(ScoreRecord.round_id.in_(replacement_ids))
                )
            }
            for replacement in replacements:
                round_record = round_records[replacement.round_id]
                player_ids = list(
                    db.scalars(
                        select(SeatingRevisionPlayerRecord.player_id)
                        .where(
                            SeatingRevisionPlayerRecord.revision_id
                            == round_record.seating_revision_id
                        )
                        .order_by(SeatingRevisionPlayerRecord.seat)
                    )
                )
                if len(player_ids) != 4:
                    player_ids = list(
                        db.scalars(
                            select(GameSessionPlayerRecord.player_id)
                            .where(
                                GameSessionPlayerRecord.game_session_id == game_session_id
                            )
                            .order_by(GameSessionPlayerRecord.seat)
                        )
                    )
                if len(player_ids) != 4:
                    raise GameSessionConfigurationError(
                        "Der Spieltag hat keine vollständige Sitzordnung."
                    )
                round_record.entry = replacement.entry
                round_record.declaring_party = replacement.parsed.declaring_party.value
                round_record.active_bocks = replacement.active_bocks
                round_record.scheduled_bocks = replacement.parsed.scheduled_bocks
                round_record.team_signs = (
                    "".join(replacement.parsed.team_signs)
                    if replacement.parsed.team_signs
                    else None
                )
                for player_id, points in zip(
                    player_ids, replacement.parsed.points, strict=True
                ):
                    score = score_records.get((replacement.round_id, player_id))
                    if score is None:
                        raise GameSessionConfigurationError(
                            "Mindestens eine Punktebuchung fehlt."
                        )
                    score.points = points

    def replace_rounds(
        self, game_session_id: int, replacements: Sequence[RoundReplacement],
        *, expected_revision: int | None = None,
    ) -> None:
        """Apply a validated round recalculation atomically."""
        with transaction(self._factory) as db:
            game_session = self._claim_session(db, game_session_id, expected_revision)
            if game_session is None:
                raise GameSessionNotFoundError(game_session_id)
            if game_session.ended_at is not None:
                raise GameSessionAlreadyEndedError(game_session_id)

            round_records = {
                item.id: item
                for item in db.scalars(
                    select(RoundRecord).where(
                        RoundRecord.game_session_id == game_session_id
                    )
                )
            }
            replacement_ids = {item.round_id for item in replacements}
            entries_are_current = all(
                round_records[item.round_id].entry == item.expected_entry
                for item in replacements
                if item.round_id in round_records
            )
            if (
                replacement_ids != set(round_records)
                or not entries_are_current
            ):
                raise GameSessionConfigurationError(
                    "Der Spieltag hat sich während der Korrektur geändert."
                )

            score_records = {
                (score.round_id, score.player_id): score
                for score in db.scalars(
                    select(ScoreRecord).where(ScoreRecord.round_id.in_(replacement_ids))
                )
            }
            for replacement in replacements:
                round_record = round_records[replacement.round_id]
                player_ids = list(
                    db.scalars(
                        select(SeatingRevisionPlayerRecord.player_id)
                        .where(
                            SeatingRevisionPlayerRecord.revision_id
                            == round_record.seating_revision_id
                        )
                        .order_by(SeatingRevisionPlayerRecord.seat)
                    )
                )
                if len(player_ids) != 4:
                    player_ids = list(
                        db.scalars(
                            select(GameSessionPlayerRecord.player_id)
                            .where(
                                GameSessionPlayerRecord.game_session_id == game_session_id
                            )
                            .order_by(GameSessionPlayerRecord.seat)
                        )
                    )
                if len(player_ids) != 4:
                    raise GameSessionConfigurationError(
                        "Der Spieltag hat keine vollständige Sitzordnung."
                    )
                round_record.entry = replacement.entry
                round_record.declaring_party = replacement.parsed.declaring_party.value
                round_record.active_bocks = replacement.active_bocks
                round_record.scheduled_bocks = replacement.parsed.scheduled_bocks
                round_record.team_signs = (
                    "".join(replacement.parsed.team_signs)
                    if replacement.parsed.team_signs
                    else None
                )
                for player_id, points in zip(
                    player_ids, replacement.parsed.points, strict=True
                ):
                    score = score_records.get((replacement.round_id, player_id))
                    if score is None:
                        raise GameSessionConfigurationError(
                            "Mindestens eine Punktebuchung fehlt."
                        )
                    score.points = points

    def overview_counts(self) -> OverviewCounts:
        with transaction(self._factory) as db:
            players = db.scalar(select(func.count()).select_from(PlayerRecord)) or 0
            sessions = db.scalar(select(func.count()).select_from(GameSessionRecord)) or 0
        return OverviewCounts(players=players, game_sessions=sessions)
