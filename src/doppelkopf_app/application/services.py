from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from re import fullmatch
from typing import Protocol, cast

from doppelkopf_app.domain.bocks import bock_levels, remaining_appended_bocks
from doppelkopf_app.domain.entities import BockCounting, GameSession, Player
from doppelkopf_app.domain.scoring import DeclaringParty, ParsedScoreEntry, parse_score_entry
from doppelkopf_app.domain.statistics import StatisticalRound, Statistics, calculate_statistics
from doppelkopf_app.domain.tempo import RoundTempo, calculate_round_tempos


class DuplicatePlayerError(Exception):
    """Raised when a player name is already present."""


class PlayerNotFoundError(Exception):
    """Raised when a requested player does not exist."""


class PlayerInUseError(Exception):
    """Raised when a player with historical references would be deleted."""


class GameSessionNotFoundError(Exception):
    """Raised when a requested game session does not exist."""


class GameSessionAlreadyEndedError(Exception):
    """Raised when an ended game session is ended again."""


class OpenGameSessionExistsError(ValueError):
    """Raised when a second open game session would be created."""


class GameSessionConfigurationError(ValueError):
    """Raised when a game session cannot be configured or played."""


class SaveOutcomeUnknownError(RuntimeError):
    """The connection failed during commit; the caller must reconcile before retrying."""


class RoundNotFoundError(ValueError):
    """Raised when a game session has no round to undo."""


@dataclass(frozen=True, slots=True)
class RoundReplacement:
    round_id: int
    expected_entry: str
    entry: str
    parsed: ParsedScoreEntry
    active_bocks: int


@dataclass(frozen=True, slots=True)
class GameSessionSummary:
    id: int
    played_on: date
    title: str
    ended_at: datetime | None
    bock_counting: BockCounting
    round_count: int = 0
    tempo_reset_at: datetime | None = None

    @property
    def is_ended(self) -> bool:
        return self.ended_at is not None


@dataclass(frozen=True, slots=True)
class OverviewCounts:
    players: int
    game_sessions: int


@dataclass(frozen=True, slots=True)
class PlayerSummary:
    id: int
    name: str
    chart_color: str | None = None
    chart_line: str | None = None


@dataclass(frozen=True, slots=True)
class SeatingRevisionSummary:
    revision: int
    effective_from_sequence: int
    changed_at: datetime
    players: tuple[PlayerSummary, PlayerSummary, PlayerSummary, PlayerSummary]


@dataclass(frozen=True, slots=True)
class RoundSummary:
    id: int
    sequence: int
    dealer_position: int
    entry: str
    declaring_party: DeclaringParty
    active_bocks: int
    scheduled_bocks: int
    points: tuple[int, int, int, int]
    bock_counting: BockCounting
    source_row: int | None = None
    source_seat_order: str | None = None
    dealer_player_id: int | None = None
    seating_players: tuple[PlayerSummary, ...] = ()
    completed_at: datetime | None = None
    team_signs: tuple[str, str, str, str] | None = None

    @property
    def bock_factor(self) -> int:
        return self.bock_counting.factor(self.active_bocks)


@dataclass(frozen=True, slots=True)
class GameSessionState:
    session: GameSessionSummary
    players: tuple[PlayerSummary, ...]
    start_dealer_position: int | None
    rounds: tuple[RoundSummary, ...]
    overall_totals: tuple[int, int, int, int]
    next_dealer_player_id: int | None = None
    revision: int = 0

    @property
    def day_totals(self) -> tuple[int, int, int, int]:
        totals = []
        for index, player in enumerate(self.players):
            value = 0
            for item in self.rounds:
                seating = item.seating_players or self.players
                seat_index = next(
                    (seat for seat, seated in enumerate(seating) if seated.id == player.id),
                    index,
                )
                value += item.points[seat_index]
            totals.append(value)
        return cast(tuple[int, int, int, int], tuple(totals))

    @property
    def last_round_points(self) -> tuple[int, int, int, int] | None:
        """Return the latest round points in the current player order."""
        if not self.rounds:
            return None
        latest = self.rounds[-1]
        seating = latest.seating_players or self.players
        points_by_player = {
            player.id: latest.points[index] for index, player in enumerate(seating)
        }
        return cast(
            tuple[int, int, int, int],
            tuple(points_by_player[player.id] for player in self.players),
        )

    @property
    def last_round_team_signs(self) -> tuple[str, str, str, str] | None:
        """Return recorded signs in current seating order, including zero rounds."""
        if not self.rounds or self.rounds[-1].team_signs is None:
            return None
        latest = self.rounds[-1]
        seating = latest.seating_players or self.players
        signs_by_player = dict(zip(
            (player.id for player in seating), self.rounds[-1].team_signs, strict=True
        ))
        return cast(
            tuple[str, str, str, str],
            tuple(signs_by_player[player.id] for player in self.players),
        )

    @property
    def next_dealer_position(self) -> int | None:
        if self.next_dealer_player_id is not None:
            return next(
                (
                    index
                    for index, player in enumerate(self.players)
                    if player.id == self.next_dealer_player_id
                ),
                None,
            )
        if self.start_dealer_position is None:
            return None
        return (self.start_dealer_position + len(self.rounds)) % 4

    @property
    def remaining_appended_bocks(self) -> int:
        """Return the entire remaining queue for the append counting mode."""
        return remaining_appended_bocks([item.scheduled_bocks for item in self.rounds])

    @property
    def pending_bocks(self) -> tuple[int, int, int, int]:
        levels = bock_levels(
            [item.scheduled_bocks for item in self.rounds], self.session.bock_counting
        )
        return cast(tuple[int, int, int, int], levels[-4:])


class DoppelkopfRepository(Protocol):
    def add_player(self, player: Player) -> None: ...
    def update_player(self, player_id: int, player: Player) -> None: ...
    def set_player_chart_color(self, player_id: int, color: str | None) -> None: ...
    def set_player_chart_line(self, player_id: int, line: str | None) -> None: ...
    def set_player_chart_style(
        self, player_id: int, color: str | None, line: str | None,
    ) -> None: ...
    def delete_player(self, player_id: int) -> None: ...
    def list_player_names(self) -> Sequence[str]: ...
    def list_players(self) -> Sequence[PlayerSummary]: ...
    def add_game_session(self, game_session: GameSession) -> None: ...
    def add_configured_game_session(
        self,
        game_session: GameSession,
        player_ids: tuple[int, int, int, int],
        dealer_position: int,
        changed_at: datetime,
    ) -> int: ...
    def list_game_sessions(self) -> Sequence[GameSessionSummary]: ...
    def end_game_session(self, game_session_id: int, ended_at: datetime) -> None: ...
    def configure_game_session(
        self, game_session_id: int, player_ids: tuple[int, int, int, int], dealer_position: int
    ) -> None: ...
    def change_seating(
        self, game_session_id: int, player_ids: tuple[int, int, int, int], changed_at: datetime
    ) -> None: ...
    def set_next_dealer(self, game_session_id: int, player_id: int) -> None: ...
    def reset_tempo(self, game_session_id: int, reset_at: datetime) -> None: ...
    def list_tempo_resets(self, game_session_id: int) -> tuple[datetime, ...]: ...
    def delete_game_session(self, game_session_id: int) -> None: ...
    def get_game_session_revision(self, game_session_id: int) -> int | None: ...
    def get_open_game_session_state(self) -> GameSessionState | None: ...
    def get_game_session_state(self, game_session_id: int) -> GameSessionState: ...
    def list_seating_revisions(
        self, game_session_id: int
    ) -> Sequence[SeatingRevisionSummary]: ...
    def list_game_session_states(
        self, game_session_ids: Sequence[int]
    ) -> Sequence[GameSessionState]: ...
    def add_round(
        self,
        game_session_id: int,
        parsed: ParsedScoreEntry,
        entry: str,
        dealer_position: int,
        active_bocks: int,
        completed_at: datetime,
        *,
        expected_sequence: int | None = None,
        expected_player_ids: tuple[int, int, int, int] | None = None,
        expected_dealer_player_id: int | None = None,
        expected_revision: int | None = None,
    ) -> GameSessionState: ...
    def delete_last_round(
        self, game_session_id: int, *, expected_revision: int | None = None
    ) -> None: ...
    def delete_round(
        self,
        game_session_id: int,
        round_id: int,
        expected_entry: str,
        replacements: Sequence[RoundReplacement],
        *, expected_revision: int | None = None,
    ) -> None: ...
    def replace_rounds(
        self, game_session_id: int, replacements: Sequence[RoundReplacement],
        *, expected_revision: int | None = None,
    ) -> None: ...
    def overview_counts(self) -> OverviewCounts: ...


class DoppelkopfService:
    """Application use cases independent of Streamlit and SQLAlchemy."""

    def __init__(
        self,
        repository: DoppelkopfRepository,
        clock: Callable[[], datetime] = datetime.utcnow,
    ) -> None:
        self._repository = repository
        self._clock = clock

    def create_player(self, name: str) -> None:
        self._repository.add_player(Player(name))

    def update_player(self, player_id: int, name: str) -> None:
        if player_id <= 0:
            raise ValueError("Die Spieler-ID muss positiv sein.")
        self._repository.update_player(player_id, Player(name))

    def set_player_chart_color(self, player_id: int, color: str | None) -> None:
        """Save a player's color globally; None restores automatic chart colors."""
        if player_id <= 0:
            raise ValueError("Die Spieler-ID muss positiv sein.")
        self._repository.set_player_chart_color(player_id, self._normalize_chart_color(color))

    def set_player_chart_line(self, player_id: int, line: str | None) -> None:
        """Save a player's line pattern globally; None restores automatic styling."""
        if player_id <= 0:
            raise ValueError("Die Spieler-ID muss positiv sein.")
        self._validate_chart_line(line)
        self._repository.set_player_chart_line(player_id, line)

    def set_player_chart_style(
        self, player_id: int, color: str | None, line: str | None,
    ) -> None:
        """Validate and save color and line together; None restores either automatic value."""
        if player_id <= 0:
            raise ValueError("Die Spieler-ID muss positiv sein.")
        color = self._normalize_chart_color(color)
        self._validate_chart_line(line)
        self._repository.set_player_chart_style(player_id, color, line)

    @staticmethod
    def _normalize_chart_color(color: str | None) -> str | None:
        if color is None:
            return None
        if not fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("Die Farbe muss ein Hex-Code im Format #RRGGBB sein.")
        return color.upper()

    @staticmethod
    def _validate_chart_line(line: str | None) -> None:
        if line not in (None, "solid", "dashed", "dotted", "dashdot"):
            raise ValueError("Unbekannter Linientyp.")

    def delete_player(self, player_id: int, confirmation: str) -> None:
        if player_id <= 0:
            raise ValueError("Die Spieler-ID muss positiv sein.")
        player = next(
            (item for item in self._repository.list_players() if item.id == player_id),
            None,
        )
        if player is None:
            raise PlayerNotFoundError(player_id)
        if confirmation.strip() != player.name:
            raise ValueError("Der eingegebene Spielername stimmt nicht überein.")
        self._repository.delete_player(player_id)

    def list_player_names(self) -> Sequence[str]:
        return self._repository.list_player_names()

    def list_players(self) -> Sequence[PlayerSummary]:
        return self._repository.list_players()

    def create_game_session(
        self,
        played_on: date,
        title: str,
        bock_counting: BockCounting = BockCounting.ADDITIVE,
    ) -> None:
        if any(not item.is_ended for item in self._repository.list_game_sessions()):
            raise OpenGameSessionExistsError(
                "Beende zuerst den offenen Spieltag, bevor du einen neuen anlegst."
            )
        self._repository.add_game_session(
            GameSession(
                played_on=played_on,
                title=title,
                bock_counting=bock_counting,
            )
        )

    def create_configured_game_session(
        self,
        played_on: date,
        title: str,
        player_ids: Sequence[int],
        dealer_position: int,
        bock_counting: BockCounting = BockCounting.ADDITIVE,
        changed_at: datetime | None = None,
    ) -> int:
        if any(not item.is_ended for item in self._repository.list_game_sessions()):
            raise OpenGameSessionExistsError(
                "Beende zuerst den offenen Spieltag, bevor du einen neuen anlegst."
            )
        normalized = self._validate_configuration(player_ids, dealer_position)
        return self._repository.add_configured_game_session(
            GameSession(played_on, title, bock_counting),
            normalized,
            dealer_position,
            changed_at or self._clock(),
        )

    def list_game_sessions(self) -> Sequence[GameSessionSummary]:
        return self._repository.list_game_sessions()

    def end_game_session(self, game_session_id: int, ended_at: datetime | None = None) -> None:
        if game_session_id <= 0:
            raise ValueError("Die Spieltag-ID muss positiv sein.")
        self._repository.end_game_session(game_session_id, ended_at or self._clock())

    def configure_game_session(
        self, game_session_id: int, player_ids: Sequence[int], dealer_position: int
    ) -> None:
        normalized = self._validate_configuration(player_ids, dealer_position)
        self._repository.configure_game_session(game_session_id, normalized, dealer_position)

    @staticmethod
    def _validate_configuration(
        player_ids: Sequence[int], dealer_position: int
    ) -> tuple[int, int, int, int]:
        normalized = tuple(player_ids)
        if len(normalized) != 4 or len(set(normalized)) != 4:
            raise GameSessionConfigurationError(
                "Es müssen genau vier verschiedene Spieler gewählt werden."
            )
        if any(player_id <= 0 for player_id in normalized):
            raise GameSessionConfigurationError("Die Spieler-IDs müssen positiv sein.")
        if dealer_position not in range(4):
            raise GameSessionConfigurationError(
                "Der Geber muss einem der vier Sitzplätze entsprechen."
            )
        return normalized[0], normalized[1], normalized[2], normalized[3]

    def change_seating(self, game_session_id: int, player_ids: Sequence[int]) -> None:
        normalized = self._validate_configuration(player_ids, 0)
        self._repository.change_seating(game_session_id, normalized, self._clock())

    def set_next_dealer(self, game_session_id: int, player_id: int) -> None:
        if game_session_id <= 0 or player_id <= 0:
            raise ValueError("Spieltag- und Spieler-ID müssen positiv sein.")
        self._repository.set_next_dealer(game_session_id, player_id)

    def reset_tempo(self, game_session_id: int, reset_at: datetime | None = None) -> None:
        """Start a new live tempo segment without discarding round timestamps."""
        if game_session_id <= 0:
            raise ValueError("Die Spieltag-ID muss positiv sein.")
        self._repository.reset_tempo(game_session_id, reset_at or self._clock())

    def delete_game_session(self, game_session_id: int, confirmation: str) -> None:
        summary = next(
            (item for item in self._repository.list_game_sessions() if item.id == game_session_id),
            None,
        )
        if summary is None:
            raise GameSessionNotFoundError(game_session_id)
        if confirmation != summary.title:
            raise ValueError("Die eingegebene Bezeichnung stimmt nicht überein.")
        self._repository.delete_game_session(game_session_id)

    def get_game_session_revision(self, game_session_id: int) -> int | None:
        """Return the persisted change token, or None after deletion."""
        return self._repository.get_game_session_revision(game_session_id)

    def get_open_game_session_state(self) -> GameSessionState | None:
        return self._repository.get_open_game_session_state()

    def get_game_session_state(self, game_session_id: int) -> GameSessionState:
        return self._repository.get_game_session_state(game_session_id)

    def list_seating_revisions(
        self, game_session_id: int
    ) -> Sequence[SeatingRevisionSummary]:
        return self._repository.list_seating_revisions(game_session_id)

    def record_round(
        self,
        game_session_id: int,
        entry: str,
        *,
        state: GameSessionState | None = None,
    ) -> GameSessionState:
        """Record a round, optionally reusing the state already rendered by the UI."""
        if state is None:
            state = self._repository.get_game_session_state(game_session_id)
        elif state.session.id != game_session_id:
            raise ValueError("Der geladene Spieltag passt nicht zur angeforderten ID.")
        if state.session.is_ended:
            raise GameSessionAlreadyEndedError(game_session_id)
        if len(state.players) != 4 or state.next_dealer_position is None:
            raise GameSessionConfigurationError(
                "Vor dem ersten Spiel müssen Spieler und Geber festgelegt werden."
            )
        parsed = parse_score_entry(entry)
        active_bocks = state.pending_bocks[0]
        factor = state.session.bock_counting.factor(active_bocks)
        points = tuple(point * factor for point in parsed.points)
        factored = ParsedScoreEntry(
            cast(tuple[int, int, int, int], points),
            parsed.declaring_party,
            parsed.scheduled_bocks,
            parsed.team_signs,
        )
        return self._repository.add_round(
            game_session_id,
            factored,
            entry.strip(),
            state.next_dealer_position,
            active_bocks,
            self._clock(),
            expected_revision=state.revision,
            expected_sequence=len(state.rounds) + 1,
            expected_player_ids=cast(
                tuple[int, int, int, int], tuple(player.id for player in state.players)
            ),
            expected_dealer_player_id=state.next_dealer_player_id,
        )

    def undo_last_round(self, game_session_id: int) -> None:
        state = self._repository.get_game_session_state(game_session_id)
        if state.session.is_ended:
            raise GameSessionAlreadyEndedError(game_session_id)
        if not state.rounds:
            raise RoundNotFoundError(game_session_id)
        self._repository.delete_last_round(game_session_id, expected_revision=state.revision)

    def delete_round(self, game_session_id: int, round_id: int) -> None:
        """Delete one round and consistently recalculate all remaining rounds."""
        state = self._repository.get_game_session_state(game_session_id)
        if state.session.is_ended:
            raise GameSessionAlreadyEndedError(game_session_id)
        deleted_round = next((item for item in state.rounds if item.id == round_id), None)
        if deleted_round is None:
            raise RoundNotFoundError(round_id)

        remaining_rounds = [item for item in state.rounds if item.id != round_id]
        parsed_entries = [parse_score_entry(item.entry) for item in remaining_rounds]
        levels = bock_levels(
            [item.scheduled_bocks for item in parsed_entries], state.session.bock_counting
        )
        replacements: list[RoundReplacement] = []
        for index, (item, parsed) in enumerate(
            zip(remaining_rounds, parsed_entries, strict=True)
        ):
            active_bocks = levels[index]
            factor = state.session.bock_counting.factor(active_bocks)
            points = tuple(point * factor for point in parsed.points)
            replacements.append(
                RoundReplacement(
                    round_id=item.id,
                    expected_entry=item.entry,
                    entry=item.entry,
                    parsed=ParsedScoreEntry(
                        cast(tuple[int, int, int, int], points),
                        parsed.declaring_party,
                        parsed.scheduled_bocks,
                        parsed.team_signs,
                    ),
                    active_bocks=active_bocks,
                )
            )
        self._repository.delete_round(
            game_session_id,
            round_id,
            deleted_round.entry,
            replacements,
            expected_revision=state.revision,
        )

    def correct_round(self, game_session_id: int, round_id: int, entry: str) -> None:
        """Correct one entry and consistently recalculate all Bock-dependent rounds."""
        state = self._repository.get_game_session_state(game_session_id)
        if state.session.is_ended:
            raise GameSessionAlreadyEndedError(game_session_id)
        if not any(item.id == round_id for item in state.rounds):
            raise RoundNotFoundError(round_id)

        parsed_entries = [
            parse_score_entry(entry if item.id == round_id else item.entry)
            for item in state.rounds
        ]
        levels = bock_levels(
            [item.scheduled_bocks for item in parsed_entries], state.session.bock_counting
        )
        replacements: list[RoundReplacement] = []
        for index, (item, parsed) in enumerate(
            zip(state.rounds, parsed_entries, strict=True)
        ):
            active_bocks = levels[index]
            factor = state.session.bock_counting.factor(active_bocks)
            points = tuple(point * factor for point in parsed.points)
            replacements.append(
                RoundReplacement(
                    round_id=item.id,
                    expected_entry=item.entry,
                    entry=(entry.strip() if item.id == round_id else item.entry),
                    parsed=ParsedScoreEntry(
                        cast(tuple[int, int, int, int], points),
                        parsed.declaring_party,
                        parsed.scheduled_bocks,
                        parsed.team_signs,
                    ),
                    active_bocks=active_bocks,
                )
            )
        self._repository.replace_rounds(
            game_session_id, replacements, expected_revision=state.revision
        )

    def overview_counts(self) -> OverviewCounts:
        return self._repository.overview_counts()

    def statistics(
        self,
        game_session_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> Statistics:
        """Calculate overall or single-session statistics without UI or SQL concerns."""
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValueError("Das Von-Datum darf nicht nach dem Bis-Datum liegen.")
        summaries = list(self._repository.list_game_sessions())
        summaries.sort(key=lambda item: (item.played_on, item.id))
        if game_session_id is not None:
            summaries = [item for item in summaries if item.id == game_session_id]
            if not summaries:
                raise GameSessionNotFoundError(game_session_id)
        else:
            summaries = [
                item
                for item in summaries
                if (date_from is None or item.played_on >= date_from)
                and (date_to is None or item.played_on <= date_to)
            ]

        states = self._repository.list_game_session_states([item.id for item in summaries])
        player_order: list[str] = []
        statistical_rounds: list[StatisticalRound] = []
        sequence = 0
        for state in states:
            for player in state.players:
                if player.name not in player_order:
                    player_order.append(player.name)
            for item_round in state.rounds:
                sequence += 1
                statistical_rounds.append(
                    StatisticalRound(
                        sequence=sequence,
                        declaring_party=item_round.declaring_party,
                        points=tuple(
                            (player.name, item_round.points[index])
                            for index, player in enumerate(
                                item_round.seating_players or state.players
                            )
                        ),
                        active_bocks=item_round.active_bocks,
                        team_signs=item_round.team_signs,
                    )
                )
        return calculate_statistics(tuple(player_order), tuple(statistical_rounds))

    def tempo(
        self,
        game_session_id: int,
        window_minutes: int = 30,
        *,
        state: GameSessionState | None = None,
        since: datetime | None = None,
        live_only: bool = False,
    ) -> tuple[RoundTempo, ...]:
        if state is None:
            state = self.get_game_session_state(game_session_id)
        elif state.session.id != game_session_id:
            raise ValueError("Der geladene Spieltag passt nicht zur angeforderten ID.")
        return calculate_round_tempos(
            tuple(
                (item.sequence, item.completed_at)
                for item in state.rounds
                if since is None
                or (item.completed_at is not None and item.completed_at >= since)
            ),
            window_minutes,
            live_only=live_only,
            reset_times=(
                self._repository.list_tempo_resets(game_session_id) if since is None else ()
            ),
        )
