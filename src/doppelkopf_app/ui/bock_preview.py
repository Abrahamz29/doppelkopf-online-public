from collections.abc import Iterable

from doppelkopf_app.application.services import GameSessionState
from doppelkopf_app.domain.entities import BockCounting


def format_bock_preview(
    factors: Iterable[int], *, remaining_games: int | None = None, html: bool = False
) -> str:
    """Format appended games or the unchanged four-factor preview."""
    if remaining_games is not None:
        start, end = ("<strong>", "</strong>") if html else ("**", "**")
        if remaining_games == 0:
            return f"{start}Kein{end} Bock"
        if html:
            start = '<strong style="font-size: 1.4em">'
        if remaining_games == 1:
            return f"Noch {start}1{end} Spiel im Bock"
        return f"Nächsten {start}{remaining_games}{end} Spiele im Bock"
    return "Bockvorschau · " + " · ".join(str(factor) for factor in factors)


def format_session_bock_preview(state: GameSessionState, *, html: bool = False) -> str:
    """Use the same mode-specific preview on every game screen."""
    if state.session.bock_counting is BockCounting.APPEND:
        return format_bock_preview((), remaining_games=state.remaining_appended_bocks, html=html)
    return format_bock_preview(
        state.session.bock_counting.factor(level) for level in state.pending_bocks
    )
