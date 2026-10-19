from html import escape

import streamlit as st

from doppelkopf_app.application.services import (
    GameSessionAlreadyEndedError,
    GameSessionConfigurationError,
    GameSessionNotFoundError,
    GameSessionState,
    RoundNotFoundError,
    RoundSummary,
    SaveOutcomeUnknownError,
)
from doppelkopf_app.config import get_settings
from doppelkopf_app.domain.scoring import ScoreEntryError
from doppelkopf_app.ui.bock_preview import format_session_bock_preview
from doppelkopf_app.ui.chart_styles import player_line_styles
from doppelkopf_app.ui.charts import (
    render_points_progress,
    render_smoothed_tempo,
    tempo_label,
)
from doppelkopf_app.ui.diagnostics import diagnostic_span
from doppelkopf_app.ui.live_refresh import (
    game_session_state_signature,
    open_game_session_signature,
    watch_for_changes,
)
from doppelkopf_app.ui.runtime import get_service
from doppelkopf_app.ui.score_cards import format_points, render_score_cards
from doppelkopf_app.ui.score_keypad_v4 import score_entry
from doppelkopf_app.ui.seating import render_seating_change_form


def _round_action_error_key(game_session_id: int) -> str:
    return f"round-action-error-{game_session_id}"


def _round_submission_ack_key(game_session_id: int) -> str:
    return f"round-submission-ack-{game_session_id}"


def _record_round_immediately(
    game_session_id: int, state: GameSessionState, entry: str
) -> None:
    """Persist a submitted entry before Streamlit rebuilds the page."""
    try:
        with diagnostic_span("save"):
            saved = get_service().record_round(game_session_id, entry, state=state)
        st.session_state["live-saved-state"] = saved
        st.session_state.pop(_round_action_error_key(game_session_id), None)
    except (
        GameSessionAlreadyEndedError,
        GameSessionConfigurationError,
        GameSessionNotFoundError,
        ScoreEntryError,
        SaveOutcomeUnknownError,
    ) as error:
        st.session_state[_round_action_error_key(game_session_id)] = str(error)
    finally:
        ack_key = _round_submission_ack_key(game_session_id)
        st.session_state[ack_key] = int(st.session_state.get(ack_key, 0)) + 1


def _record_manual_round(
    game_session_id: int,
    state: GameSessionState,
    input_key: str,
) -> None:
    entry = st.session_state.get(input_key, "")
    if isinstance(entry, str):
        _record_round_immediately(game_session_id, state, entry)


service = get_service()
state = st.session_state.pop("live-saved-state", None)
if state is None:
    state = service.get_open_game_session_state()
if state is None:
    watch_for_changes(
        lambda: open_game_session_signature(service.list_game_sessions()), (None,)
    )
    st.info("Aktuell gibt es keinen offenen Spieltag. Lege unter „Spielabende“ einen an.")
    st.stop()
selected_session_id = state.session.id
st.html(
    '<p class="live-session-meta">'
    f"{escape(state.session.title)} · {state.session.played_on:%d.%m.%Y} · Offen"
    "</p>"
)

if len(state.players) != 4:
    st.error("Der offene Spieltag ist nicht vollständig eingerichtet.")
    st.stop()


def _dismiss_correction_dialog() -> None:
    st.session_state.pop(f"edit-round-{selected_session_id}", None)


def _dismiss_delete_dialog() -> None:
    st.session_state.pop(f"delete-round-{selected_session_id}", None)


@st.dialog(
    "Spiel korrigieren",
    width="small",
    on_dismiss=_dismiss_correction_dialog,
)
def _correct_round_dialog(item: RoundSummary) -> None:
    st.caption(
        f"Spiel {item.sequence} · Bockvormerkungen betroffener Folgespiele "
        "werden automatisch neu berechnet."
    )
    with st.form(f"correct-round-{selected_session_id}-{item.id}"):
        corrected_entry = st.text_input(
            "Korrigierte Eingabe",
            value=item.entry,
            help="Verwende dieselbe Kurznotation wie bei der Spieleingabe.",
            key=f"corrected-entry-{selected_session_id}-{item.id}",
        )
        confirm = st.checkbox(
            "Ich bestätige, dass diese Korrektur gespeichert werden soll.",
            key=f"confirm-correction-{selected_session_id}-{item.id}",
        )
        save_correction = st.form_submit_button(
            "Korrektur endgültig speichern",
            icon=":material/save:",
            type="primary",
            key=f"save-correction-{selected_session_id}-{item.id}",
        )
        cancel_correction = st.form_submit_button(
            "Abbrechen",
            key=f"cancel-correction-{selected_session_id}-{item.id}",
        )
    if cancel_correction:
        st.session_state.pop(f"edit-round-{selected_session_id}", None)
        st.rerun()
    if save_correction:
        if not confirm:
            st.warning("Bitte bestätige die Korrektur vor dem Speichern.")
            return
        try:
            service.correct_round(selected_session_id, item.id, corrected_entry)
            st.session_state.pop(f"edit-round-{selected_session_id}", None)
            st.toast(f"Spiel {item.sequence} wurde korrigiert.", icon="✅")
            st.rerun()
        except ScoreEntryError as error:
            st.error(str(error))
        except (
            GameSessionAlreadyEndedError,
            GameSessionConfigurationError,
            GameSessionNotFoundError,
            RoundNotFoundError,
        ) as error:
            st.error(str(error))


@st.dialog(
    "Spiel löschen",
    width="small",
    on_dismiss=_dismiss_delete_dialog,
)
def _delete_round_dialog(item: RoundSummary) -> None:
    st.warning(
        f"Spiel {item.sequence} (`{item.entry}`) wird endgültig gelöscht. "
        "Nachfolgende Spiele und Bockfaktoren werden automatisch neu berechnet."
    )
    confirm = st.checkbox(
        "Ich bestätige, dass dieses Spiel gelöscht werden soll.",
        key=f"confirm-delete-round-{selected_session_id}-{item.id}",
    )
    with st.container(horizontal=True):
        if st.button(
            "Endgültig löschen",
            icon=":material/delete:",
            type="primary",
            disabled=not confirm,
            key=f"confirm-delete-round-button-{selected_session_id}-{item.id}",
        ):
            try:
                service.delete_round(selected_session_id, item.id)
                st.session_state.pop(f"delete-round-{selected_session_id}", None)
                st.toast(f"Spiel {item.sequence} wurde gelöscht.")
                st.rerun()
            except (
                GameSessionAlreadyEndedError,
                GameSessionConfigurationError,
                GameSessionNotFoundError,
                RoundNotFoundError,
                ScoreEntryError,
            ) as error:
                st.error(str(error))
        if st.button(
            "Abbrechen",
            key=f"cancel-delete-round-{selected_session_id}-{item.id}",
        ):
            st.session_state.pop(f"delete-round-{selected_session_id}", None)
            st.rerun()

keypad_enabled_key = f"score-keypad-enabled-{selected_session_id}"
edit_state_key = f"edit-round-{selected_session_id}"
delete_state_key = f"delete-round-{selected_session_id}"
st.session_state.setdefault(keypad_enabled_key, True)
window_key = "tempo-window-minutes"
st.session_state.setdefault(window_key, get_settings().tempo_window_minutes)
tempos = service.tempo(
    selected_session_id,
    int(st.session_state[window_key]),
    state=state,
    since=state.session.tempo_reset_at,
    live_only=True,
)
tempo_value, tempo_detail = tempo_label(tempos)


def _load_signature() -> tuple[object, ...]:
    """Read current data for the game page's automatic refresh."""
    return (selected_session_id, service.get_game_session_revision(selected_session_id))


watch_for_changes(_load_signature, game_session_state_signature(state))

st.html(
    """
    <style>
    .live-session-meta {
      margin: 0;
      color: color-mix(in srgb, var(--st-text-color) 65%, transparent);
      font-size: .85rem;
    }
    @media (max-width: 640px) {
      :root {
        --doko-mobile-type-scale: clamp(1.2rem, calc(1.02rem + .75vw), 1.22rem);
      }
      [data-testid="stHeader"] {
        height: 2.5rem;
        background: var(--st-background-color);
        border-bottom: 1px solid
          color-mix(in srgb, var(--st-text-color) 14%, transparent);
        backdrop-filter: none;
      }
      [data-testid="stMainBlockContainer"] {
        padding: 2.75rem .55rem .6rem;
      }
      .live-session-meta { display: none; }
      [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {
        gap: .38rem;
      }
      [data-testid="stTabs"] [role="tablist"] {
        gap: 0;
        justify-content: space-between;
        width: calc(100% - .25rem);
      }
      [data-testid="stTabs"] [data-testid="stTab"] {
        min-height: 2.25rem;
        padding: .3rem .2rem;
        font-size: clamp(.98rem, calc(.85rem + .58vw), 1.02rem);
        white-space: nowrap;
      }
      [data-testid="stTabs"] [role="tabpanel"] {
        padding-top: .35rem;
      }
      [data-testid="stTabs"] [role="tabpanel"] [data-testid="stVerticalBlock"] {
        gap: .5rem;
      }
      [data-testid="stTabs"] [role="tabpanel"] [data-testid="stHorizontalBlock"] {
        gap: .5rem;
      }
      [data-testid="stTabs"] [role="tabpanel"] [data-testid="stMetric"] {
        padding: 0;
      }
      [data-testid="stTabs"] [role="tabpanel"] [data-testid="stMetricLabel"] {
        font-size: clamp(.91rem, calc(.78rem + .58vw), .93rem);
      }
      [data-testid="stTabs"] [role="tabpanel"] [data-testid="stMetricValue"] {
        font-size: clamp(1.26rem, calc(1.08rem + .75vw), 1.28rem);
      }
      [data-testid="stTabs"] [role="tabpanel"] [data-testid="stVerticalBlockBorderWrapper"] {
        padding: .58rem .55rem;
      }
      [data-testid="stTabs"] [role="tabpanel"] [data-testid="stCaptionContainer"] {
        font-size: clamp(.93rem, calc(.8rem + .58vw), .96rem);
        line-height: 1.15;
      }
      [data-testid="stTabs"] [role="tabpanel"] .stButton > button {
        min-height: 2.75rem;
        padding-block: .3rem;
        font-size: var(--doko-mobile-type-scale);
        white-space: nowrap;
      }
    }
    @media (max-width: 340px) {
      :root { --doko-mobile-type-scale: 1.15rem; }
      [data-testid="stTabs"] [data-testid="stTab"] { font-size: .92rem; }
      [data-testid="stTabs"] [role="tabpanel"] [data-testid="stMetricLabel"] {
        font-size: .875rem;
      }
      [data-testid="stTabs"] [role="tabpanel"] [data-testid="stMetricValue"] {
        font-size: 1.21rem;
      }
      [data-testid="stTabs"] [role="tabpanel"] [data-testid="stCaptionContainer"] {
        font-size: .88rem;
      }
    }
    </style>
    """
)

# Retain history/filter choices while their tab is not rendered.
for widget_key in list(st.session_state):
    if isinstance(widget_key, str) and (
        widget_key.startswith(
            ("history-view-", "correction-round-")
        )
        or widget_key == "tempo-window-minutes"
    ):
        st.session_state[widget_key] = st.session_state[widget_key]

game_tab, progress_tab, history_tab, settings_tab = st.tabs(
    ["Spiel", "Verlauf", "Einzelspiele", "Optionen"],
    key=f"live-tab-{selected_session_id}",
    on_change="rerun",
)

with game_tab:
    render_score_cards(
        state.players,
        state.day_totals,
        state.last_round_points,
        state.next_dealer_position if not state.session.is_ended else None,
        last_round_team_signs=state.last_round_team_signs,
    )
    st.caption(
        format_session_bock_preview(state, html=True), unsafe_allow_html=True
    )

    if not state.session.is_ended:
        submission_ack_key = _round_submission_ack_key(selected_session_id)
        st.session_state.setdefault(submission_ack_key, 0)
        action_error = st.session_state.pop(
            _round_action_error_key(selected_session_id), None
        )
        entry_column, tempo_column = st.columns([3, 2], vertical_alignment="center")
        if st.session_state[keypad_enabled_key]:
            with entry_column:
                score_entry(
                    players=tuple(player.name for player in state.players),
                    reset_token=len(state.rounds),
                    submission_ack=int(st.session_state[submission_ack_key]),
                    key=f"score-keypad-{selected_session_id}",
                    on_submit=lambda entry: _record_round_immediately(
                        selected_session_id, state, entry
                    ),
                )
        else:
            st.html(
                """
                <style>
                div[class*="st-key-manual-save-round-"] button {
                  background:var(--doko-save-background) !important;
                  border-color:var(--doko-save-background) !important; color:#fff !important;
                }
                div[class*="st-key-manual-save-round-"] button:hover {
                  background:var(--doko-save-hover) !important;
                  border-color:var(--doko-save-hover) !important;
                }
                </style>
                """
            )
            manual_entry_key = f"manual-round-entry-{selected_session_id}"
            with entry_column, st.form(
                f"round-entry-{selected_session_id}", clear_on_submit=True
            ):
                st.text_input(
                    "Ergebnis",
                    placeholder="z. B. 6--++R, BB9-+++K oder 0++--",
                    help=(
                        "Zahl = Grundwert, vier Vorzeichen = Sitzplätze, R/K = Partei. "
                        "Beim Nullspiel kennzeichnen zwei Pluszeichen Re und zwei Minuszeichen "
                        "Kontra. B = vier Bockspiele gemäß gewählter Bockzählung vormerken."
                    ),
                    key=manual_entry_key,
                )
                st.form_submit_button(
                    "Spiel speichern",
                    icon=":material/add_circle:",
                    type="primary",
                    width="stretch",
                    key=f"manual-save-round-{selected_session_id}",
                    on_click=_record_manual_round,
                    args=(selected_session_id, state, manual_entry_key),
                )
        if action_error:
            with tempo_column:
                st.error(action_error)
        with tempo_column.container(
            border=True,
            gap="small",
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="center",
        ):
            with st.container(gap=None):
                st.metric("Aktuelles Tempo", tempo_value)
                st.caption(tempo_detail)
            if st.button(
                "Zurücksetzen",
                icon=":material/restart_alt:",
                key=f"reset-tempo-{selected_session_id}",
                help=(
                    "Tempo nach einer Pause neu starten. Nach zwei weiteren Spielen "
                    "wird wieder ein Wert angezeigt."
                ),
            ):
                try:
                    service.reset_tempo(selected_session_id)
                    st.toast("Tempo wurde neu gestartet.", icon=":material/restart_alt:")
                    st.rerun()
                except (GameSessionAlreadyEndedError, GameSessionNotFoundError) as error:
                    st.error(str(error))
    else:
        st.info("Dieser Spieltag ist beendet. Die Ergebnisse können nur noch angesehen werden.")

if progress_tab.open:
    with progress_tab:
        render_score_cards(
            state.players,
            state.day_totals,
            state.last_round_points,
            state.next_dealer_position if not state.session.is_ended else None,
            last_round_team_signs=state.last_round_team_signs,
        )
        if not state.rounds:
            st.info("Noch kein Spiel erfasst.")
        else:
            running = {player.id: 0 for player in state.players}
            progress_rows = []
            for item in state.rounds:
                seating = item.seating_players or state.players
                for index, player in enumerate(seating):
                    running[player.id] += item.points[index]
                progress_rows.append(
                    {
                        "Spiel": item.sequence,
                        **{player.name: running[player.id] for player in state.players},
                    }
                )
            chart_players = list(service.list_players())
            chart_left, chart_right = st.columns(2)
            with chart_left.container(border=True):
                st.markdown("**Punkteverlauf**")
                render_points_progress(
                    progress_rows,
                    [player.name for player in state.players],
                    key=f"live-points-{selected_session_id}",
                    styles=player_line_styles(
                        [p for p in chart_players if p.id in {p.id for p in state.players}],
                        dark=st.context.theme.type == "dark",
                    ),
                )
            with chart_right.container(border=True):
                st.markdown("**Spieltempo**")
                tempo_history = service.tempo(
                    selected_session_id, int(st.session_state[window_key]), state=state
                )
                render_smoothed_tempo(tempo_history, key=f"live-tempo-{selected_session_id}")
                with st.popover("Filter", icon=":material/tune:"):
                    st.number_input(
                        "Zeitfenster in Minuten",
                        min_value=5,
                        max_value=180,
                        step=5,
                        key=window_key,
                    )

if history_tab.open:
    with history_tab:
        if not state.rounds:
            st.info("Noch kein Spiel erfasst.")
        else:
            reversed_rounds = list(reversed(state.rounds))
            history_view = st.segmented_control(
                "Darstellung",
                ["Kompakt", "Tabelle"],
                default="Kompakt",
                key=f"history-view-{selected_session_id}",
            )
            if history_view == "Tabelle":
                rows = []
                for item in reversed_rounds:
                    is_zero_round = not any(item.points)
                    rows.append(
                        {
                            "Spiel": item.sequence,
                            "Geber": next(
                                (
                                    player.name
                                    for player in (item.seating_players or state.players)
                                    if player.id == item.dealer_player_id
                                ),
                                (item.seating_players or state.players)[
                                    item.dealer_position
                                ].name,
                            ),
                            "Eingabe": item.entry,
                            "Partei": "–" if is_zero_round else item.declaring_party.value,
                            "Bock": f"×{item.bock_factor}",
                            "Excel-Zeile": item.source_row,
                            "Sitzreihenfolge": item.source_seat_order or "",
                            **{
                                player.name: item.points[index]
                                for index, player in enumerate(
                                    item.seating_players or state.players
                                )
                            },
                        }
                    )
                st.dataframe(rows, hide_index=True, width="stretch")
                if not state.session.is_ended:
                    selected_round_id = st.selectbox(
                        "Spiel auswählen",
                        options=[item.id for item in reversed_rounds],
                        format_func=lambda round_id: next(
                            f"Spiel {item.sequence}: {item.entry}"
                            for item in reversed_rounds
                            if item.id == round_id
                        ),
                        key=f"correction-round-{selected_session_id}",
                    )
                    with st.container(horizontal=True):
                        if st.button(
                            "Korrigieren",
                            key=f"edit-table-round-{selected_session_id}",
                            icon=":material/edit:",
                        ):
                            st.session_state[edit_state_key] = selected_round_id
                            st.rerun()
                        if st.button(
                            "Löschen",
                            key=f"delete-table-round-{selected_session_id}",
                            icon=":material/delete:",
                        ):
                            st.session_state[delete_state_key] = selected_round_id
                            st.rerun()
            else:
                for item in reversed_rounds:
                    is_zero_round = not any(item.points)
                    seating = item.seating_players or state.players
                    dealer_name = next(
                        (
                            player.name
                            for player in seating
                            if player.id == item.dealer_player_id
                        ),
                        seating[item.dealer_position].name,
                    )
                    with st.container(border=True, gap="small"):
                        st.markdown(
                            f"**Spiel {item.sequence}** · {dealer_name} gibt · `{item.entry}`"
                        )
                        point_text = " · ".join(
                            f"**{player.name}: {format_points(item.points[index])}**"
                            for index, player in enumerate(seating)
                        )
                        st.markdown(point_text)
                        round_type = (
                            "Nullspiel" if is_zero_round else item.declaring_party.value
                        )
                        details = f"{round_type} · Bock ×{item.bock_factor}"
                        if item.source_row is not None:
                            details += f" · Excel-Zeile {item.source_row}"
                        st.caption(details)
                        if item.source_seat_order:
                            st.caption(f"Sitzreihenfolge: {item.source_seat_order}")
                        if not state.session.is_ended:
                            with st.container(horizontal=True):
                                if st.button(
                                    "Korrigieren",
                                    key=f"edit-round-button-{selected_session_id}-{item.id}",
                                    icon=":material/edit:",
                                ):
                                    st.session_state[edit_state_key] = item.id
                                    st.rerun()
                                if st.button(
                                    "Löschen",
                                    key=f"delete-round-button-{selected_session_id}-{item.id}",
                                    icon=":material/delete:",
                                ):
                                    st.session_state[delete_state_key] = item.id
                                    st.rerun()

            edit_round_id = st.session_state.get(edit_state_key)
            editable_round = next(
                (item for item in state.rounds if item.id == edit_round_id), None
            )
            if not state.session.is_ended and editable_round is not None:
                _correct_round_dialog(editable_round)
            delete_round_id = st.session_state.get(delete_state_key)
            deletable_round = next(
                (item for item in state.rounds if item.id == delete_round_id), None
            )
            if not state.session.is_ended and deletable_round is not None:
                _delete_round_dialog(deletable_round)

with settings_tab:
    if state.session.is_ended:
        st.info("Die Spieleinstellungen eines beendeten Spieltags können nicht geändert werden.")
    else:
        with st.container(horizontal=True, gap="small", vertical_alignment="center"):
            with st.popover(
                "Sitzreihenfolge ändern", icon=":material/event_seat:"
            ):
                # Keep the form mounted so unsent browser inputs survive tab switches.
                available_players = state.players if state.rounds else service.list_players()
                render_seating_change_form(service, state, available_players)
            with st.popover("Geber ändern", icon=":material/style:"):
                dealer_id = st.selectbox(
                    "Nächster Geber",
                    [player.id for player in state.players],
                    index=state.next_dealer_position or 0,
                    format_func=lambda player_id: next(
                        player.name
                        for player in state.players
                        if player.id == player_id
                    ),
                    key=f"live-dealer-{selected_session_id}",
                )
                if st.button(
                    "Übernehmen", key=f"save-live-dealer-{selected_session_id}"
                ):
                    service.set_next_dealer(selected_session_id, dealer_id)
                    st.rerun()
            keypad_enabled = bool(st.session_state[keypad_enabled_key])
            keypad_label = "Tastatur an" if keypad_enabled else "Tastatur aus"
            if st.button(
                keypad_label,
                icon=":material/keyboard:",
                key=f"toggle-score-keypad-{selected_session_id}",
                help="Spieltastatur ein- oder ausschalten",
            ):
                st.session_state[keypad_enabled_key] = not keypad_enabled
                st.rerun()
