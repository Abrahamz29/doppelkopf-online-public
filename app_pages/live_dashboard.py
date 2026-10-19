import streamlit as st

from doppelkopf_app.application.services import (
    GameSessionAlreadyEndedError,
    GameSessionConfigurationError,
    GameSessionNotFoundError,
    GameSessionState,
    SaveOutcomeUnknownError,
)
from doppelkopf_app.config import get_settings
from doppelkopf_app.domain.scoring import ScoreEntryError
from doppelkopf_app.ui.bock_preview import format_session_bock_preview
from doppelkopf_app.ui.chart_styles import player_line_styles
from doppelkopf_app.ui.charts import render_points_progress, tempo_label
from doppelkopf_app.ui.diagnostics import diagnostic_span
from doppelkopf_app.ui.layout import page_heading
from doppelkopf_app.ui.live_refresh import (
    game_session_state_signature,
    open_game_session_signature,
    watch_for_changes,
)
from doppelkopf_app.ui.phone_connect import show_phone_connection
from doppelkopf_app.ui.runtime import get_service
from doppelkopf_app.ui.score_cards import (
    render_dashboard_score_cards,
    render_score_cards,
)
from doppelkopf_app.ui.score_keypad_v4 import score_entry
from doppelkopf_app.ui.seating import render_seating_change_form

service = get_service()
chart_players = list(service.list_players())
initial_state = st.session_state.pop("dashboard-saved-state", None)
if initial_state is None:
    initial_state = service.get_open_game_session_state()

page_heading("Live-Dashboard", icon=":material/dashboard:")
st.html(
    """
    <style>
    [data-testid="stMainBlockContainer"] {
      padding-top: 1.25rem;
      padding-bottom: .45rem;
    }
    [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {
      gap: .25rem;
      height: 100%;
    }
    .dashboard-bock-preview {
      margin: 0;
      font-size: 1.45rem;
      line-height: 1.15;
      font-weight: 700;
    }
    .dashboard-bock-preview:has(strong) {
      font-weight: 400;
    }
    [data-testid="stMainBlockContainer"]:has(.st-key-dashboard-points-panel) {
      height: calc(100dvh - 16px);
      min-height: calc(100dvh - 16px);
    }
    [data-testid="stLayoutWrapper"]:has(
      > .st-key-dashboard-points-panel
    ) {
      flex: 1 1 0;
      min-height: 0;
    }
    .st-key-dashboard-points-panel {
      min-height: 0;
      overflow: hidden;
    }
    .st-key-dashboard-points-panel > [data-testid="stVerticalBlock"] {
      height: 100%;
      min-height: 0;
    }
    .st-key-dashboard-chart-heading [data-testid="stColumn"]:has(
      .st-key-dashboard-current-game
    ) {
      display: none;
    }
    [data-testid="stLayoutWrapper"]:has(> .st-key-dashboard-mobile-scores) {
      display: none;
    }
    @media (max-width:767px) {
      [data-testid="stLayoutWrapper"]:has(> .st-key-dashboard-mobile-scores) {
        display: block;
      }
      [data-testid="stLayoutWrapper"]:has(> .st-key-dashboard-desktop-scores) {
        display: none;
      }
      /* Let the phone page scroll instead of clipping a stretched chart. */
      [data-testid="stMainBlockContainer"] {
        padding-top: 4.5rem;
        padding-bottom: calc(1.5rem + env(safe-area-inset-bottom, 0px));
      }
      [data-testid="stMainBlockContainer"]:has(.st-key-dashboard-points-panel) {
        height: auto;
        min-height: 100dvh;
      }
      [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {
        height: auto;
      }
      [data-testid="stLayoutWrapper"]:has(> .st-key-dashboard-points-panel) {
        flex: 0 0 auto;
      }
      .st-key-dashboard-points-panel,
      .st-key-dashboard-points-panel > [data-testid="stVerticalBlock"] {
        height: auto;
        overflow: visible;
      }
      .st-key-dashboard-points-panel [data-testid="stVegaLiteChart"] {
        height: 340px;
        min-height: 340px;
      }
      .st-key-dashboard-chart-heading h3 {
        font-size: 1.35rem;
        padding-top: 0;
      }
      .st-key-dashboard-tempo [data-testid="stMetricValue"],
      .st-key-dashboard-tempo [data-testid="stMetricValue"] p {
        font-size: 1.4rem;
        line-height: 1.3;
      }
      .dashboard-bock-preview {
        font-size: 1.15rem;
      }
    }
    @media (min-width:768px) {
      .st-key-dashboard-chart-heading {
        container-type: inline-size;
      }
      .st-key-dashboard-chart-heading [data-testid="stMarkdownContainer"] {
        margin: 0;
      }
      .st-key-dashboard-chart-heading h3,
      .st-key-dashboard-current-game [data-testid="stMarkdownContainer"] p,
      .st-key-dashboard-tempo [data-testid="stMetricValue"],
      .st-key-dashboard-tempo [data-testid="stMetricValue"] p {
        font-size: clamp(1rem,3.2cqw,1.75rem);
        line-height: 1.4;
        margin: 0;
        padding: 0;
        white-space: nowrap;
      }
      .st-key-dashboard-tempo [data-testid="stMetric"] {
        padding: 0;
        min-height: 0;
      }
      .st-key-dashboard-tempo [data-testid="stMetricValue"] {
        text-align: right;
      }
      .st-key-dashboard-chart-heading [data-testid="stColumn"] {
        flex: 1 1 0;
        min-width: 0;
      }
      .st-key-dashboard-chart-heading [data-testid="stColumn"]:has(
        .st-key-dashboard-current-game
      ) {
        display: block;
      }
      .st-key-dashboard-current-game [data-testid="stMarkdownContainer"] p {
        text-align: center;
        white-space: nowrap;
        margin: 0;
        font-weight: 700;
      }
      .st-key-dashboard-tempo [data-testid="stMetricLabel"] {
        position: absolute;
        width: 1px;
        height: 1px;
        overflow: hidden;
        clip-path: inset(50%);
        white-space: nowrap;
      }
    }
    </style>
    """
)
if initial_state is None:
    watch_for_changes(
        lambda: open_game_session_signature(service.list_game_sessions()), (None,)
    )
    st.info("Aktuell gibt es keinen offenen Spieltag. Lege unter „Spieltage“ einen an.")
    st.stop()
session_id = initial_state.session.id
if len(initial_state.players) != 4:
    st.error("Der offene Spieltag ist nicht vollständig eingerichtet.")
    st.stop()

st.caption(f"{initial_state.session.title} · {initial_state.session.played_on:%d.%m.%Y}")

keypad_enabled_key = f"score-keypad-enabled-{session_id}"
score_entry_visible_key = f"dashboard-score-entry-visible-{session_id}"
submission_ack_key = f"dashboard-submission-ack-{session_id}"
action_error_key = f"dashboard-round-error-{session_id}"
st.session_state.setdefault(keypad_enabled_key, True)
st.session_state.setdefault(score_entry_visible_key, False)
st.session_state.setdefault(submission_ack_key, 0)


def _record_round(entry: str) -> None:
    """Persist dashboard input against freshly loaded state."""
    try:
        with diagnostic_span("save"):
            saved = service.record_round(session_id, entry, state=initial_state)
        st.session_state["dashboard-saved-state"] = saved
        st.session_state.pop(action_error_key, None)
    except (
        GameSessionAlreadyEndedError,
        GameSessionConfigurationError,
        GameSessionNotFoundError,
        ScoreEntryError,
        SaveOutcomeUnknownError,
    ) as error:
        st.session_state[action_error_key] = str(error)
    finally:
        st.session_state[submission_ack_key] = int(st.session_state[submission_ack_key]) + 1


def _record_manual_round(input_key: str) -> None:
    entry = st.session_state.get(input_key, "")
    if isinstance(entry, str):
        _record_round(entry)


def _reset_tempo() -> None:
    try:
        service.reset_tempo(session_id)
        st.toast("Tempo wurde neu gestartet.", icon=":material/restart_alt:")
    except (GameSessionAlreadyEndedError, GameSessionNotFoundError) as error:
        st.error(str(error))


def _live_scoreboard(state: GameSessionState) -> None:
    with st.container(key="dashboard-desktop-scores"):
        render_dashboard_score_cards(
            state.players,
            state.day_totals,
            state.last_round_points,
            state.next_dealer_position,
            last_round_team_signs=state.last_round_team_signs,
        )
    with st.container(key="dashboard-mobile-scores"):
        render_score_cards(
            state.players,
            state.day_totals,
            state.last_round_points,
            state.next_dealer_position,
            last_round_team_signs=state.last_round_team_signs,
        )


def _live_tempo(state: GameSessionState) -> None:
    tempos = service.tempo(
        session_id,
        get_settings().tempo_window_minutes,
        state=state,
        since=state.session.tempo_reset_at,
        live_only=True,
    )
    tempo_value, tempo_detail = tempo_label(tempos)
    with st.container(
        horizontal=True, vertical_alignment="center", gap="small", key="dashboard-tempo"
    ):
        st.metric("Aktuelles Tempo", tempo_value, help=tempo_detail)
        st.button(
            "Reset",
            icon=":material/restart_alt:",
            key=f"dashboard-reset-tempo-{session_id}",
            help="Tempo nach einer Pause neu starten.",
            on_click=_reset_tempo,
        )


def _live_charts(state: GameSessionState) -> None:
    running = {player.id: 0 for player in state.players}
    rows: list[dict[str, int]] = []
    for item in state.rounds:
        seating = item.seating_players or state.players
        for index, player in enumerate(seating):
            running[player.id] += item.points[index]
        rows.append(
            {
                "Spiel": item.sequence,
                **{player.name: running[player.id] for player in state.players},
            }
        )
    with st.container(
        border=True,
        key="dashboard-points-panel",
        height="stretch",
    ):
        with st.container(key="dashboard-chart-heading"):
            heading, current_game, tempo = st.columns([3, 1, 1], vertical_alignment="center")
            with heading:
                st.subheader("Punkteverlauf", icon=":material/show_chart:")
            with current_game, st.container(key="dashboard-current-game"):
                st.markdown(f"Aktuelles Spiel: {len(state.rounds) + 1}")
            with tempo:
                _live_tempo(state)
        if not state.rounds:
            st.caption("Noch kein Spiel erfasst.")
            return
        render_points_progress(
            rows,
            [player.name for player in state.players],
            key=f"dashboard-points-{session_id}",
            height="stretch",
            dashboard=True,
            styles=player_line_styles(
                [p for p in chart_players if p.id in {p.id for p in state.players}],
                dark=st.context.theme.type == "dark",
            ),
        )


def _score_entry(input_state: GameSessionState) -> None:
    """Render the fallback round input only when explicitly requested."""
    with st.container(border=True):
        action_error = st.session_state.pop(action_error_key, None)
        if action_error:
            st.error(action_error)
        if st.session_state[keypad_enabled_key]:
            score_entry(
                players=tuple(player.name for player in input_state.players),
                reset_token=len(input_state.rounds),
                submission_ack=int(st.session_state[submission_ack_key]),
                key=f"dashboard-score-keypad-{session_id}",
                on_submit=_record_round,
            )
        else:
            manual_entry_key = f"dashboard-manual-entry-{session_id}"
            st.html(
                """
                <style>
                div[class*="st-key-dashboard-manual-save-round-"] button:not(:disabled) {
                  --dashboard-save-color:color-mix(
                    in srgb, var(--st-green-color, #2e7d32) 68%, #000
                  );
                  background:var(--dashboard-save-color) !important;
                  border-color:var(--dashboard-save-color) !important;
                  color:#fff !important;
                }
                div[class*="st-key-dashboard-manual-save-round-"] button:hover:not(:disabled) {
                  --dashboard-save-color:color-mix(
                    in srgb, var(--st-green-color, #2e7d32) 58%, #000
                  );
                }
                </style>
                """
            )
            with st.form(f"dashboard-round-entry-{session_id}", clear_on_submit=True):
                st.text_input(
                    "Ergebnis",
                    placeholder="z. B. 6--++R, BB9-+++K oder 0++--",
                    key=manual_entry_key,
                )
                st.form_submit_button(
                    "Spiel speichern",
                    icon=":material/add_circle:",
                    type="primary",
                    width="stretch",
                    key=f"dashboard-manual-save-round-{session_id}",
                    on_click=_record_manual_round,
                    args=(manual_entry_key,),
                )

        with st.expander("Optionen", icon=":material/tune:"):
            keypad_enabled = bool(st.session_state[keypad_enabled_key])
            if st.button(
                "Interne Tastatur aus" if keypad_enabled else "Interne Tastatur an",
                icon=":material/keyboard:",
                key=f"dashboard-toggle-keypad-{session_id}",
            ):
                st.session_state[keypad_enabled_key] = not keypad_enabled
                st.rerun()
            with st.popover("Geber ändern", icon=":material/style:"):
                dealer_id = st.selectbox(
                    "Nächster Geber",
                    [player.id for player in input_state.players],
                    index=input_state.next_dealer_position or 0,
                    format_func=lambda player_id: next(
                        player.name
                        for player in input_state.players
                        if player.id == player_id
                    ),
                    key=f"dashboard-dealer-{session_id}",
                )
                if st.button("Übernehmen", key=f"save-dashboard-dealer-{session_id}"):
                    service.set_next_dealer(session_id, dealer_id)
                    st.rerun()
            with st.popover("Sitzreihenfolge ändern", icon=":material/event_seat:"):
                render_seating_change_form(
                    service, input_state,
                    input_state.players if input_state.rounds else service.list_players(),
                    key_prefix="dashboard",
                )


def _load_signature() -> tuple[object, ...]:
    """Read current data for the dashboard's automatic refresh."""
    return (session_id, service.get_game_session_revision(session_id))


_live_scoreboard(initial_state)

preview_column, action_buttons_column = st.columns(
    [3, 2], gap="small", vertical_alignment="center"
)
with preview_column:
    st.html(
        '<p class="dashboard-bock-preview">'
        + format_session_bock_preview(initial_state, html=True)
        + "</p>"
    )
with action_buttons_column, st.container(
    horizontal=True, horizontal_alignment="right", vertical_alignment="center", gap=None,
):
    if st.button(
        "Schließen" if st.session_state[score_entry_visible_key] else "Spiel eingeben",
        icon=(
            ":material/close:"
            if st.session_state[score_entry_visible_key]
            else ":material/keyboard:"
        ),
        type="tertiary",
        width=160,
        key=f"dashboard-toggle-score-entry-{session_id}",
    ):
        st.session_state[score_entry_visible_key] = not bool(
            st.session_state[score_entry_visible_key]
        )
        st.rerun()

    if st.button(
        "Handy verbinden",
        icon=":material/qr_code_2:",
        type="tertiary",
        width=160,
        key="dashboard-connect-phone",
    ):
        show_phone_connection()

if st.session_state[score_entry_visible_key]:
    _score_entry(initial_state)

_live_charts(initial_state)

watch_for_changes(_load_signature, game_session_state_signature(initial_state))
