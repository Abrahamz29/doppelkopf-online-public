"""Shared, deterministic presentation of player identities in point charts."""
from collections.abc import Sequence
from dataclasses import dataclass

from doppelkopf_app.application.services import PlayerSummary

DARK_COLORS = ("#56B4E9", "#E69F00", "#66CC99", "#CC79A7")
LIGHT_COLORS = ("#0072B2", "#A65E00", "#007A5E", "#A33782")
LINE_KEYS = ("solid", "dashed", "dotted", "dashdot")
LINE_DASHES = ((), (10, 5), (2, 5), (10, 4, 2, 4))
LINE_NAMES = ("Durchgezogen", "Gestrichelt", "Gepunktet", "Strichpunktiert")
PALETTE = {
    "Blau · Dunkel": "#005A8D", "Blau": "#0072B2", "Blau · Hell": "#56B4E9",
    "Türkis · Dunkel": "#006B70", "Türkis": "#009DA6", "Türkis · Hell": "#63D5DC",
    "Grün · Dunkel": "#007A5E", "Grün": "#009E73", "Grün · Hell": "#66CC99",
    "Gelb · Dunkel": "#8A7000", "Gelb": "#D4B000", "Gelb · Hell": "#F0E442",
    "Orange · Dunkel": "#A65E00", "Orange": "#E69F00", "Orange · Hell": "#FFC46B",
    "Rot · Dunkel": "#A32424", "Rot": "#D64545", "Rot · Hell": "#FF8A80",
    "Magenta · Dunkel": "#A33782", "Magenta": "#CC79A7", "Magenta · Hell": "#F2A6D3",
    "Violett · Dunkel": "#6341A5", "Violett": "#9467BD", "Violett · Hell": "#C5A0E8",
}


@dataclass(frozen=True, slots=True)
class PlayerLineStyle:
    player_id: int
    name: str
    color: str
    dash: tuple[int, ...]
    pattern_name: str


def player_line_styles(
    players: Sequence[PlayerSummary], *, dark: bool,
) -> tuple[PlayerLineStyle, ...]:
    """Use stable player IDs, independent of names, seats and current scores."""
    colors = DARK_COLORS if dark else LIGHT_COLORS
    result = []
    for index, player in enumerate(sorted(players, key=lambda item: item.id)):
        pattern = (LINE_KEYS.index(player.chart_line) if player.chart_line is not None
                   else (index + index // 4) % 4)
        result.append(PlayerLineStyle(
            player.id, player.name, player.chart_color or colors[index % 4],
            LINE_DASHES[pattern], LINE_NAMES[pattern],
        ))
    return tuple(result)
