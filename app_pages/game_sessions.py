import random
from datetime import date

import streamlit as st

from doppelkopf_app.application.services import (
    GameSessionAlreadyEndedError,
    GameSessionNotFoundError,
    OpenGameSessionExistsError,
)
from doppelkopf_app.domain.entities import BockCounting
from doppelkopf_app.ui.layout import page_heading
from doppelkopf_app.ui.runtime import get_service
from doppelkopf_app.ui.seating import render_seating_change_form

service = get_service()


@st.dialog("Spieltag endgültig löschen")
def _confirm_delete(session_id: int, title: str, rounds: int) -> None:
    st.warning(
        f"„{title}“ mit {rounds} Spielen wird einschließlich Sitzhistorie und Punkten gelöscht. "
        "Die Gesamtstatistik ändert sich dadurch."
    )
    confirmation = st.text_input(
        "Bezeichnung zur Bestätigung",
        key=f"delete-confirmation-{session_id}",
        help="Gib die Bezeichnung exakt ein.",
    )
    if st.button(
        "Endgültig löschen",
        icon=":material/delete_forever:",
        type="primary",
        disabled=confirmation != title,
        key=f"delete-final-{session_id}",
    ):
        try:
            service.delete_game_session(session_id, confirmation)
            st.rerun()
        except (GameSessionNotFoundError, ValueError) as error:
            st.error(str(error))


page_heading("Spieltage", icon=":material/event:")
sessions = list(service.list_game_sessions())
open_session = next((item for item in sessions if not item.is_ended), None)
players = list(service.list_players())
player_names = {player.id: player.name for player in players}

if open_session is None:
    if len(players) < 4:
        st.warning("Lege zuerst mindestens vier Spieler an.")
    else:
        selected_ids = st.multiselect(
            "Vier Spieler",
            [player.id for player in players],
            max_selections=4,
            format_func=player_names.__getitem__,
            key="new-session-players",
        )
        if st.button(
            "Zufällig anordnen",
            icon=":material/shuffle:",
            disabled=len(selected_ids) != 4,
            key="new-session-randomize",
        ):
            shuffled = list(selected_ids)
            random.SystemRandom().shuffle(shuffled)
            for index, player_id in enumerate(shuffled):
                st.session_state[f"new-session-seat-{index}"] = player_id
            st.rerun()

        if len(selected_ids) == 4:
            with st.form("new-session"):
                played_on = st.date_input("Datum", value=date.today())
                title = st.text_input("Bezeichnung")
                bock_label = st.segmented_control(
                    "Bockzählung",
                    ["Addieren", "Multiplizieren", "Anhängen"],
                    default="Addieren",
                    required=True,
                    help="Anhängen: Jeder Bock fügt vier Bockspiele an. Der Faktor bleibt ×2.",
                )
                seat_columns = st.columns(4, gap="small")
                ordered_ids: list[int] = []
                for index, column in enumerate(seat_columns):
                    key = f"new-session-seat-{index}"
                    if st.session_state.get(key) not in selected_ids:
                        st.session_state[key] = selected_ids[index]
                    with column:
                        ordered_ids.append(
                            st.selectbox(
                                f"Sitz {index + 1}",
                                selected_ids,
                                format_func=player_names.__getitem__,
                                key=key,
                            )
                        )
                dealer_position = st.selectbox(
                    "Erster Geber",
                    range(4),
                    format_func=lambda index: player_names[ordered_ids[index]],
                )
                submitted = st.form_submit_button(
                    "Spieltag anlegen",
                    icon=":material/event_available:",
                    type="primary",
                    width="stretch",
                )
            if submitted:
                if len(set(ordered_ids)) != 4:
                    st.warning("Jeder Spieler darf nur einen Sitzplatz belegen.")
                else:
                    try:
                        counting = {
                            "Addieren": BockCounting.ADDITIVE,
                            "Multiplizieren": BockCounting.MULTIPLICATIVE,
                            "Anhängen": BockCounting.APPEND,
                        }[bock_label or "Addieren"]
                        service.create_configured_game_session(
                            played_on, title, ordered_ids, dealer_position, counting
                        )
                        st.rerun()
                    except (OpenGameSessionExistsError, ValueError) as error:
                        st.error(str(error))
else:
    st.subheader("Aktueller Spieltag")
    state = service.get_game_session_state(open_session.id)
    st.caption(
        f"Offen: {open_session.title} · {open_session.played_on:%d.%m.%Y} · "
        f"{len(state.rounds)} Spiele"
    )
    with st.expander("Sitzreihenfolge ändern", icon=":material/event_seat:"):
        render_seating_change_form(service, state, players)

    with st.container(horizontal=True, vertical_alignment="bottom"):
        next_dealer_id = st.selectbox(
            "Nächster Geber",
            [player.id for player in state.players],
            index=state.next_dealer_position or 0,
            format_func=lambda player_id: next(
                player.name for player in state.players if player.id == player_id
            ),
            key=f"next-dealer-{open_session.id}",
        )
        if st.button("Geber übernehmen", icon=":material/style:"):
            service.set_next_dealer(open_session.id, next_dealer_id)
            st.rerun()

    history = st.expander(
        "Sitzhistorie", icon=":material/history:", on_change="rerun"
    )
    if history.open:
        revisions = service.list_seating_revisions(open_session.id)
        with history:
            if not revisions:
                st.caption("Noch keine Sitzhistorie vorhanden.")
            st.dataframe(
                [
                    {
                        "Version": item.revision,
                        "Gültig ab Spiel": item.effective_from_sequence,
                        "Geändert": item.changed_at.strftime("%d.%m.%Y %H:%M"),
                        "Reihenfolge": " · ".join(player.name for player in item.players),
                    }
                    for item in revisions
                ],
                hide_index=True,
            )

    with st.container(horizontal=True):
        if st.button(
            "Spieltag beenden",
            key=f"end-session-{open_session.id}",
            icon=":material/event_available:",
            type="primary",
        ):
            try:
                service.end_game_session(open_session.id)
                st.rerun()
            except (GameSessionAlreadyEndedError, GameSessionNotFoundError) as error:
                st.error(str(error))
        if st.button(
            "Spieltag löschen",
            key=f"delete-session-{open_session.id}",
            icon=":material/delete:",
        ):
            _confirm_delete(open_session.id, open_session.title, len(state.rounds))

st.subheader("Bisherige Spieltage")
if not sessions:
    st.caption("Noch kein Spieltag angelegt.")
for session in sessions:
    if open_session is not None and session.id == open_session.id:
        continue
    with st.container(border=True, gap="small"):
        st.markdown(
            f"**{session.title}** · {session.played_on:%d.%m.%Y} · "
            f"{session.round_count} Spiele"
        )
        if session.ended_at is not None:
            st.caption(f"Beendet am {session.ended_at:%d.%m.%Y um %H:%M Uhr}")
        if st.button(
            "Löschen",
            key=f"delete-session-{session.id}",
            icon=":material/delete:",
        ):
            _confirm_delete(session.id, session.title, session.round_count)
