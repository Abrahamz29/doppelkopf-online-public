from collections.abc import Sequence

import streamlit as st

from doppelkopf_app.application.services import (
    DoppelkopfService,
    GameSessionAlreadyEndedError,
    GameSessionConfigurationError,
    GameSessionState,
    PlayerSummary,
)


def render_seating_change_form(
    service: DoppelkopfService,
    state: GameSessionState,
    available_players: Sequence[PlayerSummary],
    *,
    key_prefix: str = "change",
) -> None:
    """Render the shared form for changing the seating from the next round onward."""
    session_id = state.session.id
    allowed_players = state.players if state.rounds else available_players
    allowed_names = {player.id: player.name for player in allowed_players}
    allowed_ids = [player.id for player in allowed_players]

    with st.form(f"{key_prefix}-seating-{session_id}"):
        columns = st.columns(4, gap="small")
        new_order = []
        for index, column in enumerate(columns):
            current_id = state.players[index].id
            with column:
                new_order.append(
                    st.selectbox(
                        f"Sitz {index + 1}",
                        allowed_ids,
                        index=allowed_ids.index(current_id),
                        format_func=allowed_names.__getitem__,
                        key=f"{key_prefix}-seat-{session_id}-{index}",
                    )
                )
        save_seating = st.form_submit_button(
            "Reihenfolge speichern", icon=":material/save:"
        )

    if not save_seating:
        return
    if len(set(new_order)) != 4:
        st.warning("Jeder Spieler darf nur einen Sitzplatz belegen.")
        return
    try:
        service.change_seating(session_id, new_order)
        st.rerun()
    except (
        GameSessionAlreadyEndedError,
        GameSessionConfigurationError,
    ) as error:
        st.error(str(error))
