from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal

from doppelkopf_app.domain.scoring import DeclaringParty


@dataclass(frozen=True, slots=True)
class StatisticalRound:
    sequence: int
    declaring_party: DeclaringParty
    points: tuple[tuple[str, int], ...]
    active_bocks: int = 0
    team_signs: tuple[str, str, str, str] | None = None


@dataclass(frozen=True, slots=True)
class PlayerStatistics:
    name: str
    total_points: int
    highest_win: int
    highest_loss: int
    games_won: int
    games_lost: int
    average_win_points: Decimal
    average_loss_points: Decimal
    solos_played: int
    solos_won: int
    solos_lost: int
    solo_points: int
    points_without_solos: int
    foreign_solo_points: int
    re_won: int
    re_lost: int
    kontra_won: int
    kontra_lost: int
    partnership_games: int
    re_games: int
    kontra_games: int
    average_re_win_points: Decimal
    average_kontra_win_points: Decimal
    average_re_loss_points: Decimal
    average_kontra_loss_points: Decimal

    @property
    def solo_balance(self) -> int:
        return self.solo_points + self.foreign_solo_points

    @property
    def re_win_rate(self) -> Decimal:
        return _ratio(self.re_won, self.re_won + self.re_lost)

    @property
    def re_play_rate(self) -> Decimal:
        return _ratio(self.re_games, self.partnership_games)

    @property
    def kontra_win_rate(self) -> Decimal:
        return _ratio(self.kontra_won, self.kontra_won + self.kontra_lost)

    @property
    def adjusted_without_solos(self) -> Decimal:
        re_value = self.re_win_rate * self.average_re_win_points + (
            Decimal(1) - self.re_win_rate
        ) * self.average_re_loss_points
        kontra_value = self.kontra_win_rate * self.average_kontra_win_points + (
            Decimal(1) - self.kontra_win_rate
        ) * self.average_kontra_loss_points
        return Decimal(self.partnership_games) * (re_value + kontra_value) / Decimal(2)

    @property
    def adjusted_with_solos(self) -> Decimal:
        return self.adjusted_without_solos + Decimal(self.solo_balance)

    @property
    def adjustment_difference(self) -> Decimal:
        return self.adjusted_with_solos - Decimal(self.total_points)


@dataclass(frozen=True, slots=True)
class PairStatistics:
    players: tuple[str, str]
    games: int
    won: int
    lost: int
    points: int

    @property
    def balance(self) -> int:
        return self.won - self.lost

    @property
    def points_per_game(self) -> Decimal:
        return _average([self.points], self.games)


@dataclass(frozen=True, slots=True)
class PointFrequencies:
    """One frequency per game, separated by winning party and normal/solo play."""

    total: tuple[tuple[int, int], ...]
    re: tuple[tuple[int, int], ...]
    kontra: tuple[tuple[int, int], ...]
    solo_re: tuple[tuple[int, int], ...]


@dataclass(frozen=True, slots=True)
class Statistics:
    players: tuple[PlayerStatistics, ...]
    pairs: tuple[PairStatistics, ...]
    rounds: int
    solos: int
    zero_rounds: int
    bock_rounds: int
    point_frequency: tuple[tuple[int, int], ...]
    round_point_values: tuple[tuple[int, int], ...]
    cumulative_points: tuple[tuple[int, tuple[tuple[str, int], ...]], ...]
    cumulative_wins: tuple[tuple[int, tuple[tuple[str, int], ...]], ...]
    re_point_frequency: tuple[tuple[int, int], ...]
    kontra_point_frequency: tuple[tuple[int, int], ...]
    solo_re_point_frequency: tuple[tuple[int, int], ...]
    point_frequencies_without_bock: PointFrequencies
    point_frequencies_only_bock: PointFrequencies


def calculate_statistics(
    player_order: tuple[str, ...], rounds: tuple[StatisticalRound, ...]
) -> Statistics:
    """Reproduce the workbook statistics from exact per-player round scores."""
    totals = Counter({name: 0 for name in player_order})
    wins: dict[str, list[int]] = defaultdict(list)
    losses: dict[str, list[int]] = defaultdict(list)
    partnership_wins: dict[str, list[int]] = defaultdict(list)
    partnership_losses: dict[str, list[int]] = defaultdict(list)
    solo_points = Counter({name: 0 for name in player_order})
    foreign_solo_points = Counter({name: 0 for name in player_order})
    solos_won = Counter({name: 0 for name in player_order})
    solos_lost = Counter({name: 0 for name in player_order})
    solos_played = Counter({name: 0 for name in player_order})
    re_won = Counter({name: 0 for name in player_order})
    re_lost = Counter({name: 0 for name in player_order})
    kontra_won = Counter({name: 0 for name in player_order})
    kontra_lost = Counter({name: 0 for name in player_order})
    partnership_games = Counter({name: 0 for name in player_order})
    re_games = Counter({name: 0 for name in player_order})
    kontra_games = Counter({name: 0 for name in player_order})
    re_win_points: dict[str, list[int]] = defaultdict(list)
    kontra_win_points: dict[str, list[int]] = defaultdict(list)
    re_loss_points: dict[str, list[int]] = defaultdict(list)
    kontra_loss_points: dict[str, list[int]] = defaultdict(list)
    pair_games: Counter[tuple[str, str]] = Counter()
    pair_wins: Counter[tuple[str, str]] = Counter()
    pair_losses: Counter[tuple[str, str]] = Counter()
    pair_points: Counter[tuple[str, str]] = Counter()
    frequency: Counter[int] = Counter()
    re_frequency: Counter[int] = Counter()
    kontra_frequency: Counter[int] = Counter()
    solo_re_frequency: Counter[int] = Counter()
    bock_frequency: Counter[int] = Counter()
    bock_re_frequency: Counter[int] = Counter()
    bock_kontra_frequency: Counter[int] = Counter()
    bock_solo_re_frequency: Counter[int] = Counter()
    running_wins = Counter({name: 0 for name in player_order})
    cumulative_points = []
    cumulative_wins = []
    round_point_values = []
    solo_count = 0
    zero_count = 0
    bock_count = 0

    for index, item in enumerate(rounds, start=1):
        score = dict(item.points)
        if len(score) != 4 or not set(score).issubset(player_order):
            raise ValueError("Jede Runde muss genau vier bekannte Spieler enthalten.")
        values = tuple(score.get(name, 0) for name in player_order)
        if sum(values) != 0:
            raise ValueError("Die Punkte einer Runde müssen zusammen null ergeben.")
        winners = tuple(name for name in score if score[name] > 0)
        losers = tuple(name for name in score if score[name] < 0)
        is_zero = not winners and not losers
        is_solo = {len(winners), len(losers)} == {1, 3}
        round_point_value = max(abs(value) for value in values)
        frequency[round_point_value] += 1
        if item.active_bocks > 0:
            bock_frequency[round_point_value] += 1
        round_point_values.append((index, round_point_value))
        zero_count += int(is_zero)
        bock_count += int(item.active_bocks > 0)

        zero_teams: tuple[tuple[str, str], tuple[str, str]] | None = None
        solo_player = None
        if is_zero and item.team_signs is not None:
            if len(item.team_signs) != 4:
                raise ValueError("Eine Teamzuordnung muss genau vier Vorzeichen enthalten.")
            re_team = tuple(
                name
                for (name, _points), sign in zip(
                    item.points, item.team_signs, strict=True
                )
                if sign == "+"
            )
            kontra_team = tuple(
                name
                for (name, _points), sign in zip(
                    item.points, item.team_signs, strict=True
                )
                if sign == "-"
            )
            if {len(re_team), len(kontra_team)} == {1, 3}:
                is_solo = True
                solo_player = re_team[0] if len(re_team) == 1 else kontra_team[0]
            elif len(re_team) == len(kontra_team) == 2:
                zero_teams = (
                    (re_team[0], re_team[1]),
                    (kontra_team[0], kontra_team[1]),
                )
            else:
                raise ValueError("Ein Nullspiel benötigt eine Partnerspiel- oder Solo-Zuordnung.")

        if is_solo:
            solo_count += 1
            if not is_zero:
                solo_player = winners[0] if len(winners) == 1 else losers[0]

        # Each game contributes once, using the same absolute value as the
        # overall distribution (the soloist's tripled score for solos).
        if not is_zero:
            if is_solo:
                if item.declaring_party is DeclaringParty.RE:
                    solo_re_frequency[round_point_value] += 1
                    if item.active_bocks > 0:
                        bock_solo_re_frequency[round_point_value] += 1
            elif item.declaring_party is DeclaringParty.RE:
                re_frequency[round_point_value] += 1
                if item.active_bocks > 0:
                    bock_re_frequency[round_point_value] += 1
            elif item.declaring_party is DeclaringParty.KONTRA:
                kontra_frequency[round_point_value] += 1
                if item.active_bocks > 0:
                    bock_kontra_frequency[round_point_value] += 1

        for name in player_order:
            if name not in score:
                continue
            points = score[name]
            totals[name] += points
            if points > 0:
                wins[name].append(points)
                running_wins[name] += 1
            elif points < 0:
                losses[name].append(points)
            if solo_player == name:
                solos_played[name] += 1
                solo_points[name] += points
                if points > 0:
                    solos_won[name] += 1
                elif points < 0:
                    solos_lost[name] += 1
            elif solo_player is not None:
                foreign_solo_points[name] += points

            if not is_solo and not is_zero:
                partnership_games[name] += 1
                player_won = points > 0
                if player_won:
                    partnership_wins[name].append(points)
                    if item.declaring_party is DeclaringParty.RE:
                        re_won[name] += 1
                        re_games[name] += 1
                        re_win_points[name].append(points)
                    else:
                        kontra_won[name] += 1
                        kontra_games[name] += 1
                        kontra_win_points[name].append(points)
                else:
                    partnership_losses[name].append(points)
                    if item.declaring_party is DeclaringParty.RE:
                        kontra_lost[name] += 1
                        kontra_games[name] += 1
                        re_loss_points[name].append(points)
                    else:
                        re_lost[name] += 1
                        re_games[name] += 1
                        kontra_loss_points[name].append(points)

            if zero_teams is not None:
                partnership_games[name] += 1
                if name in zero_teams[0]:
                    re_games[name] += 1
                else:
                    kontra_games[name] += 1

        if not is_solo and not is_zero:
            for pair, pair_won in ((winners, True), (losers, False)):
                ordered_pair = sorted(pair)
                key = (ordered_pair[0], ordered_pair[1])
                pair_games[key] += 1
                pair_wins[key] += int(pair_won)
                pair_losses[key] += int(not pair_won)
                pair_points[key] += score[pair[0]]
        elif zero_teams is not None:
            for pair in zero_teams:
                ordered_pair = sorted(pair)
                pair_games[(ordered_pair[0], ordered_pair[1])] += 1

        cumulative_points.append((index, tuple((name, totals[name]) for name in player_order)))
        cumulative_wins.append((index, tuple((name, running_wins[name]) for name in player_order)))

    player_statistics = tuple(
        PlayerStatistics(
            name=name,
            total_points=totals[name],
            highest_win=max(wins[name], default=0),
            highest_loss=min(losses[name], default=0),
            games_won=len(wins[name]),
            games_lost=len(losses[name]),
            average_win_points=_average(partnership_wins[name]),
            average_loss_points=_average(partnership_losses[name]),
            solos_played=solos_played[name],
            solos_won=solos_won[name],
            solos_lost=solos_lost[name],
            solo_points=solo_points[name],
            points_without_solos=totals[name] - solo_points[name] - foreign_solo_points[name],
            foreign_solo_points=foreign_solo_points[name],
            re_won=re_won[name],
            re_lost=re_lost[name],
            kontra_won=kontra_won[name],
            kontra_lost=kontra_lost[name],
            partnership_games=partnership_games[name],
            re_games=re_games[name],
            kontra_games=kontra_games[name],
            average_re_win_points=_average(re_win_points[name]),
            average_kontra_win_points=_average(kontra_win_points[name]),
            average_re_loss_points=_average(re_loss_points[name]),
            average_kontra_loss_points=_average(kontra_loss_points[name]),
        )
        for name in player_order
    )
    pair_statistics = tuple(
        PairStatistics(
            players=pair,
            games=games,
            won=pair_wins[pair],
            lost=pair_losses[pair],
            points=pair_points[pair],
        )
        for pair, games in sorted(pair_games.items())
    )
    return Statistics(
        players=player_statistics,
        pairs=pair_statistics,
        rounds=len(rounds),
        solos=solo_count,
        zero_rounds=zero_count,
        bock_rounds=bock_count,
        point_frequency=tuple(sorted(frequency.items())),
        round_point_values=tuple(round_point_values),
        cumulative_points=tuple(cumulative_points),
        cumulative_wins=tuple(cumulative_wins),
        re_point_frequency=tuple(sorted(re_frequency.items())),
        kontra_point_frequency=tuple(sorted(kontra_frequency.items())),
        solo_re_point_frequency=tuple(sorted(solo_re_frequency.items())),
        point_frequencies_without_bock=PointFrequencies(
            total=tuple(sorted((frequency - bock_frequency).items())),
            re=tuple(sorted((re_frequency - bock_re_frequency).items())),
            kontra=tuple(sorted((kontra_frequency - bock_kontra_frequency).items())),
            solo_re=tuple(sorted((solo_re_frequency - bock_solo_re_frequency).items())),
        ),
        point_frequencies_only_bock=PointFrequencies(
            total=tuple(sorted(bock_frequency.items())),
            re=tuple(sorted(bock_re_frequency.items())),
            kontra=tuple(sorted(bock_kontra_frequency.items())),
            solo_re=tuple(sorted(bock_solo_re_frequency.items())),
        ),
    )


def _average(values: list[int], divisor: int | None = None) -> Decimal:
    count = len(values) if divisor is None else divisor
    return Decimal(sum(values)) / Decimal(count) if count else Decimal(0)


def _ratio(numerator: int, denominator: int) -> Decimal:
    return Decimal(numerator) / Decimal(denominator) if denominator else Decimal(0)
