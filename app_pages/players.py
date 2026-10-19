import streamlit as st

from doppelkopf_app.application.services import (
    DuplicatePlayerError,
    PlayerInUseError,
    PlayerNotFoundError,
)
from doppelkopf_app.ui.chart_color_options import render_chart_color_options
from doppelkopf_app.ui.layout import page_heading
from doppelkopf_app.ui.runtime import get_service

page_heading("Spieler", icon=":material/group:")

with st.form("new-player", clear_on_submit=True):
    name = st.text_input("Name")
    submitted = st.form_submit_button(
        "Spieler anlegen", icon=":material/person_add:", width="stretch"
    )

if submitted:
    try:
        get_service().create_player(name)
        st.success(f"{name.strip()} wurde angelegt.")
    except ValueError as error:
        st.error(str(error))
    except DuplicatePlayerError:
        st.error("Ein Spieler mit diesem Namen ist bereits vorhanden.")

service = get_service()
players = list(service.list_players())
st.session_state.setdefault("player-management-id", None)

if not players:
    st.info("Noch keine Spieler vorhanden.")
    st.stop()

st.subheader("Vorhandene Spieler")


def select_clicked_player() -> None:
    click = st.session_state.get("player-list-click")
    if click is not None and click.row in range(len(players)):
        st.session_state["player-management-id"] = players[click.row].id


st.dataframe(
    {"Name": [player.name for player in players]},
    hide_index=True,
    width="stretch",
    key="player-list",
    column_config={
        "Name": st.column_config.ButtonColumn(
            "Name",
            type="tertiary",
            alignment="left",
            on_click=select_clicked_player,
            key="player-list-click",
        )
    },
)

selected = next(
    (
        player
        for player in players
        if player.id == st.session_state["player-management-id"]
    ),
    None,
)
edit_tab, delete_tab = st.tabs(["Bearbeiten", "Löschen"])

with edit_tab:
    if selected is None:
        st.info("Wähle oben einen Spieler aus.")
    else:
        with st.form(f"edit-player-{selected.id}"):
            edited_name = st.text_input(
                "Name", value=selected.name, key=f"player-name-{selected.id}"
            )
            save = st.form_submit_button(
                "Änderungen speichern", icon=":material/save:", width="stretch"
            )
        if save:
            try:
                service.update_player(selected.id, edited_name)
                st.success(f"{edited_name.strip()} wurde gespeichert.")
                st.rerun()
            except ValueError as error:
                st.error(str(error))
            except DuplicatePlayerError:
                st.error("Ein Spieler mit diesem Namen ist bereits vorhanden.")
            except PlayerNotFoundError:
                st.error("Der Spieler ist nicht mehr vorhanden.")

        render_chart_color_options(
            service, players, key="player-colors", player_id=selected.id,
        )

with delete_tab:
    if selected is None:
        st.info("Wähle oben einen Spieler aus.")
    else:
        st.warning(
            "Spieler können nur gelöscht werden, solange sie noch keinem Spieltag "
            "oder Ergebnis zugeordnet sind."
        )
        with st.form(f"delete-player-{selected.id}"):
            confirmation = st.text_input(
                f"Zum Löschen „{selected.name}“ eingeben",
                key=f"delete-player-confirmation-{selected.id}",
            )
            remove = st.form_submit_button(
                "Spieler löschen", icon=":material/delete:", width="stretch"
            )
        if remove:
            try:
                service.delete_player(selected.id, confirmation)
                st.session_state["player-management-id"] = None
                st.success(f"{selected.name} wurde gelöscht.")
                st.rerun()
            except PlayerInUseError:
                st.error(
                    "Dieser Spieler wird bereits in einem Spieltag verwendet und kann "
                    "deshalb nicht gelöscht werden."
                )
            except (PlayerNotFoundError, ValueError) as error:
                st.error(str(error))
