import streamlit as st

from doppelkopf_app.config import get_settings
from doppelkopf_app.ui.bock_preview import format_session_bock_preview
from doppelkopf_app.ui.charts import tempo_label
from doppelkopf_app.ui.layout import page_heading
from doppelkopf_app.ui.live_refresh import (
    game_session_state_signature,
    game_sessions_signature,
    watch_for_changes,
)
from doppelkopf_app.ui.runtime import get_service
from doppelkopf_app.ui.score_cards import render_score_cards

page_heading("Übersicht", icon=":material/home:")
service = get_service()
sessions = list(service.list_game_sessions())
open_session = next((item for item in sessions if not item.is_ended), None)
open_state = (
    service.get_game_session_state(open_session.id) if open_session is not None else None
)
initial_signature = (
    game_sessions_signature(sessions),
    game_session_state_signature(open_state) if open_state is not None else None,
)


def _load_signature() -> tuple[object, ...]:
    """Read current data for the overview's automatic refresh."""
    current_sessions = list(service.list_game_sessions())
    current_open_session = next(
        (item for item in current_sessions if not item.is_ended), None
    )
    return (
        game_sessions_signature(current_sessions),
        (current_open_session.id, service.get_game_session_revision(current_open_session.id))
        if current_open_session is not None else None,
    )


watch_for_changes(_load_signature, initial_signature)

if open_session is None:
    st.caption("Aktuell ist kein Spieltag geöffnet.")
    if st.button(
        "Spieltag anlegen",
        icon=":material/event_available:",
        type="primary",
    ):
        st.switch_page("app_pages/game_sessions.py")
    completed = next((item for item in sessions if item.is_ended), None)
    if completed is not None:
        st.markdown(
            f"**Zuletzt:** {completed.title} · {completed.played_on:%d.%m.%Y} · "
            f"{completed.round_count} Spiele"
        )
else:
    state = open_state
    assert state is not None
    st.caption(
        f"{open_session.title} · {open_session.played_on:%d.%m.%Y} · "
        f"{len(state.rounds)} Spiele"
    )
    render_score_cards(
        state.players,
        state.day_totals,
        state.last_round_points,
        state.next_dealer_position,
        last_round_team_signs=state.last_round_team_signs,
    )

    st.caption(
        format_session_bock_preview(state, html=True), unsafe_allow_html=True
    )
    tempos = service.tempo(
        open_session.id,
        get_settings().tempo_window_minutes,
        state=state,
        since=state.session.tempo_reset_at,
        live_only=True,
    )
    tempo, detail = tempo_label(tempos)
    st.metric("Aktuelles Tempo", tempo, detail, border=True)
    if st.button(
        "Spiel fortsetzen",
        icon=":material/play_arrow:",
        type="primary",
    ):
        st.switch_page("app_pages/live_game.py")
