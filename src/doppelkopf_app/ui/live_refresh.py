from collections.abc import Callable, Sequence

import streamlit as st

from doppelkopf_app.application.services import GameSessionState, GameSessionSummary
from doppelkopf_app.ui.diagnostics import record_event


def watch_for_changes(
    load_signature: Callable[[], tuple[object, ...]],
    initial_signature: tuple[object, ...],
) -> None:
    """Poll fresh data every three seconds, reusing the full run's initial read."""
    first_run = True

    @st.fragment(run_every="3s")
    def poll() -> None:
        nonlocal first_run
        if first_run:
            first_run = False
            return
        if load_signature() != initial_signature:
            record_event("poll.change")
            st.rerun(scope="app")

    poll()


def game_session_state_signature(state: GameSessionState) -> tuple[object, ...]:
    """Every session mutation increments the revision atomically."""
    return (state.session.id, state.revision)


def open_game_session_signature(sessions: Sequence[GameSessionSummary]) -> tuple[int | None]:
    """Detect an open session from summaries without loading any round state."""
    return (next((session.id for session in sessions if not session.is_ended), None),)


def game_sessions_signature(
    sessions: list[GameSessionSummary] | tuple[GameSessionSummary, ...],
) -> tuple[object, ...]:
    """Return persisted session-list values that affect the overview."""
    return tuple(
        (
            session.id,
            session.played_on,
            session.title,
            session.ended_at,
            session.bock_counting,
            session.round_count,
            session.tempo_reset_at,
        )
        for session in sessions
    )
