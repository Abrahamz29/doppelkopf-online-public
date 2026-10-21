from decimal import Decimal

import pytest

from doppelkopf_app.domain.scoring import DeclaringParty
from doppelkopf_app.domain.statistics import StatisticalRound, calculate_statistics


def test_point_distributions_separate_winning_parties_and_solos() -> None:
    names = ("A", "B", "C", "D", "E")
    entries = [
        (DeclaringParty.RE, (4, 4, -4, -4), None),
        (DeclaringParty.RE, (-4, 4, -4, 4), None),
        (DeclaringParty.KONTRA, (4, -4, 4, -4), None),
        (DeclaringParty.RE, (12, -4, -4, -4), None),
        (DeclaringParty.KONTRA, (-12, 4, 4, 4), None),
        (DeclaringParty.NONE, (0, 0, 0, 0), None),
        (DeclaringParty.NONE, (0, 0, 0, 0), ("+", "+", "-", "-")),
        (DeclaringParty.NONE, (0, 0, 0, 0), ("+", "-", "-", "-")),
    ]
    result = calculate_statistics(names, tuple(
        StatisticalRound(i, party, tuple(zip(names[:4], points, strict=True)),
                         active_bocks=1, team_signs=signs)
        for i, (party, points, signs) in enumerate(entries, start=1)
    ))
    assert result.point_frequency == ((0, 3), (4, 3), (12, 2))
    assert result.re_point_frequency == ((4, 2),)
    assert result.kontra_point_frequency == ((4, 1),)
    assert result.solo_re_point_frequency == ((12, 1),)


def test_empty_point_distributions() -> None:
    result = calculate_statistics(("A", "B", "C", "D"), ())
    assert result.point_frequency == result.re_point_frequency == ()
    assert result.kontra_point_frequency == result.solo_re_point_frequency == ()


def test_statistics_classifies_partnership_solo_and_zero_rounds() -> None:
    rounds = (
        StatisticalRound(1, DeclaringParty.RE, (("A", 4), ("B", 4), ("C", -4), ("D", -4))),
        StatisticalRound(
            2, DeclaringParty.KONTRA, (("A", -3), ("B", -3), ("C", -3), ("D", 9))
        ),
        StatisticalRound(
            3, DeclaringParty.NONE, (("A", 0), ("B", 0), ("C", 0), ("D", 0))
        ),
    )

    result = calculate_statistics(("A", "B", "C", "D"), rounds)
    by_name = {item.name: item for item in result.players}

    assert result.rounds == 3
    assert result.solos == 1
    assert result.zero_rounds == 1
    assert result.round_point_values == ((1, 4), (2, 9), (3, 0))
    assert by_name["D"].solos_won == 1
    assert by_name["D"].solo_points == 9
    assert by_name["A"].foreign_solo_points == -3
    assert by_name["A"].points_without_solos == 4
    assert by_name["A"].average_win_points == Decimal(4)
    assert by_name["A"].re_won == 1
    assert by_name["A"].re_lost == 0
    pair = next(item for item in result.pairs if item.players == ("A", "B"))
    assert (pair.games, pair.won, pair.lost, pair.points) == (1, 1, 0, 4)


def test_zero_round_with_teams_counts_participation_without_result() -> None:
    rounds = (
        StatisticalRound(
            1,
            DeclaringParty.NONE,
            (("C", 0), ("A", 0), ("D", 0), ("B", 0)),
            team_signs=("+", "-", "+", "-"),
        ),
    )

    result = calculate_statistics(("A", "B", "C", "D"), rounds)
    by_name = {item.name: item for item in result.players}
    pairs = {item.players: item for item in result.pairs}

    assert result.zero_rounds == 1
    assert all(item.partnership_games == 1 for item in result.players)
    assert by_name["C"].re_games == 1
    assert by_name["D"].re_games == 1
    assert by_name["A"].kontra_games == 1
    assert by_name["B"].kontra_games == 1
    assert by_name["C"].re_play_rate == Decimal(1)
    assert by_name["A"].re_play_rate == Decimal(0)
    assert (pairs[("C", "D")].games, pairs[("C", "D")].won, pairs[("C", "D")].lost) == (
        1,
        0,
        0,
    )
    assert pairs[("A", "B")].points == 0


@pytest.mark.parametrize("signs", ["+---", "-+--", "--+-", "---+", "-+++", "+-++", "++-+", "+++-"])
def test_zero_solo_counts_participation_without_win_or_loss(signs: str) -> None:
    seating = ("C", "A", "D", "B")
    result = calculate_statistics(
        ("A", "B", "C", "D"),
        (StatisticalRound(
            1, DeclaringParty.NONE, tuple((name, 0) for name in seating),
            active_bocks=1, team_signs=(signs[0], signs[1], signs[2], signs[3]),
        ),),
    )
    solo_sign = "+" if signs.count("+") == 1 else "-"
    solo_player = seating[signs.index(solo_sign)]
    assert (result.rounds, result.solos, result.zero_rounds, result.bock_rounds) == (1, 1, 1, 1)
    assert not result.pairs
    for player in result.players:
        assert player.solos_played == int(player.name == solo_player)
        assert player.solos_won == player.solos_lost == 0
        assert player.games_won == player.games_lost == player.total_points == 0
        assert player.partnership_games == player.re_games == player.kontra_games == 0
