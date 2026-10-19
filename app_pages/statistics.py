from collections import Counter
from decimal import Decimal

import streamlit as st

from doppelkopf_app.config import get_settings
from doppelkopf_app.domain.statistics import Statistics
from doppelkopf_app.ui.chart_styles import player_line_styles
from doppelkopf_app.ui.charts import (
    render_points_progress,
    render_raw_tempo,
    render_round_values,
    render_smoothed_tempo,
)
from doppelkopf_app.ui.layout import page_heading
from doppelkopf_app.ui.runtime import get_service


def _decimal(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}"


PLAYER_BAR_METRICS = {
    "Punkte insgesamt": lambda item: item.total_points,
    "Höchster Sieg": lambda item: item.highest_win,
    "Höchste Niederlage": lambda item: item.highest_loss,
    "Spiele gewonnen": lambda item: item.games_won,
    "Spiele verloren": lambda item: item.games_lost,
    "Ø Punkte bei Sieg": lambda item: item.average_win_points,
    "Ø Punkte bei Niederlage": lambda item: item.average_loss_points,
    "Soli gespielt": lambda item: item.solos_played,
    "Soli gewonnen": lambda item: item.solos_won,
    "Soli verloren": lambda item: item.solos_lost,
    "Solo-Punkte": lambda item: item.solo_points,
    "Punkte ohne Soli": lambda item: item.points_without_solos,
    "Solo-Bilanz": lambda item: item.solo_balance,
    "Punkte durch Fremdsoli": lambda item: item.foreign_solo_points,
    "Re gewonnen": lambda item: item.re_won,
    "Re verloren": lambda item: item.re_lost,
    "Re gewonnen %": lambda item: item.re_win_rate * 100,
    "Re gespielt %": lambda item: item.re_play_rate * 100,
    "Kontra gewonnen": lambda item: item.kontra_won,
    "Kontra verloren": lambda item: item.kontra_lost,
    "Kontra gewonnen %": lambda item: item.kontra_win_rate * 100,
    "Ø Punkte gewonnene Re-Spiele": lambda item: item.average_re_win_points,
    "Ø Punkte gewonnene Kontra-Spiele": lambda item: item.average_kontra_win_points,
    "Ø Punkte verlorene Re-Spiele": lambda item: item.average_re_loss_points,
    "Ø Punkte verlorene Kontra-Spiele": lambda item: item.average_kontra_loss_points,
    "Bereinigt ohne Soli": lambda item: item.adjusted_without_solos,
    "Bereinigt mit Soli": lambda item: item.adjusted_with_solos,
    "Differenz zur Realität": lambda item: item.adjustment_difference,
}
PAIR_BAR_METRICS = {
    "Spiele": lambda item: item.games,
    "Gewonnen": lambda item: item.won,
    "Verloren": lambda item: item.lost,
    "Bilanz": lambda item: item.balance,
    "Punkte": lambda item: item.points,
    "Punkte pro Spiel": lambda item: item.points_per_game,
}


@st.fragment
def _player_chart(statistics: Statistics) -> None:
    metric = st.selectbox(
        "Kennzahl im Balkendiagramm",
        PLAYER_BAR_METRICS,
        key="player-bar-metric",
    )
    getter = PLAYER_BAR_METRICS[metric]
    st.bar_chart(
        [
            {"Spieler": item.name, metric: float(getter(item))}
            for item in statistics.players
        ],
        x="Spieler",
        y=metric,
    )


@st.fragment
def _pair_chart(statistics: Statistics) -> None:
    metric = st.selectbox(
        "Kennzahl der Paare im Balkendiagramm",
        PAIR_BAR_METRICS,
        index=5,
        key="pair-bar-metric",
    )
    getter = PAIR_BAR_METRICS[metric]
    st.bar_chart(
        [
            {"Paar": " & ".join(item.players), metric: float(getter(item))}
            for item in statistics.pairs
        ],
        x="Paar",
        y=metric,
    )


page_heading("Statistik", icon=":material/monitoring:")
service = get_service()
chart_players = list(service.list_players())
sessions = sorted(
    service.list_game_sessions(),
    key=lambda item: (item.played_on, item.id),
    reverse=True,
)
session_labels = {
    item.id: f"{item.played_on:%d.%m.%Y} · {item.title}" for item in sessions
}
label_counts = Counter(session_labels.values())
options: dict[int | str, str] = {"overall": "Gesamtstatistik"}
options.update({
    session_id: label if label_counts[label] == 1 else f"Nr. {session_id} · {label}"
    for session_id, label in session_labels.items()
})
default_session = next(
    (item for item in sessions if not item.is_ended),
    sessions[0] if sessions else None,
)
selection_key = "statistics-session-id"
if selection_key not in st.session_state or st.session_state[selection_key] not in options:
    st.session_state[selection_key] = (
        default_session.id if default_session is not None else "overall"
    )
selection = st.selectbox(
    "Auswertung", options, format_func=options.__getitem__, key=selection_key
)
selected_session_id = selection if isinstance(selection, int) else None
date_from = None
date_to = None
if selected_session_id is None and sessions:
    available_dates = [item.played_on for item in sessions]
    from_column, to_column = st.columns(2)
    with from_column:
        date_from = st.date_input(
            "Von",
            value=min(available_dates),
            min_value=min(available_dates),
            max_value=max(available_dates),
            key="statistics-date-from",
        )
    with to_column:
        date_to = st.date_input(
            "Bis",
            value=max(available_dates),
            min_value=min(available_dates),
            max_value=max(available_dates),
            key="statistics-date-to",
        )
    if date_from > date_to:
        st.error("Das Von-Datum darf nicht nach dem Bis-Datum liegen.")
        st.stop()

statistics = service.statistics(selected_session_id, date_from, date_to)
chart_styles = player_line_styles(
    [p for p in chart_players if p.name in {s.name for s in statistics.players}],
    dark=st.context.theme.type == "dark",
)

if not statistics.rounds:
    st.info("Für diese Auswahl sind noch keine gespielten Runden vorhanden.")
    st.stop()

with st.container(horizontal=True):
    st.metric("Spiele", statistics.rounds, border=True)
    st.metric("Soli", statistics.solos, border=True)
    st.metric("Nullrunden", statistics.zero_rounds, border=True)
    st.metric("Bockspiele", statistics.bock_rounds, border=True)

left, right = st.columns(2)
with left.container(border=True):
    st.markdown("**Spieler**")
    _player_chart(statistics)
with right.container(border=True):
    st.markdown("**Zusammenspiel**")
    _pair_chart(statistics)

left, right = st.columns(2)
with left.container(border=True):
    st.markdown("**Punktewert je Spiel**")
    render_round_values(
        statistics.round_point_values, key="statistics-round-values",
    )
with right.container(border=True):
    st.markdown("**Kumulierter Punkteverlauf**")
    render_points_progress(
        [
            {"Spiel": sequence, **dict(values)}
            for sequence, values in statistics.cumulative_points
        ],
        [item.name for item in statistics.players],
        key="statistics-points-progress",
        styles=chart_styles,
    )

left, right = st.columns(2)
with left.container(border=True):
    st.markdown("**Kumulierte Siege**")
    render_points_progress(
        [
            {"Spiel": sequence, **dict(values)}
            for sequence, values in statistics.cumulative_wins
        ],
        [item.name for item in statistics.players],
        key="statistics-wins-progress", styles=chart_styles, value_label="Siege",
    )

with right.container(border=True):
    st.markdown("**Punkteverteilung**")
    st.bar_chart(
        [
            {"Punktewert": points, "Häufigkeit": frequency}
            for points, frequency in statistics.point_frequency
        ],
        x="Punktewert",
        y="Häufigkeit",
    )

if selected_session_id is not None:
    window_key = "tempo-window-minutes"
    st.session_state.setdefault(window_key, get_settings().tempo_window_minutes)
    with st.popover("Tempofilter", icon=":material/tune:"):
        st.number_input(
            "Zeitfenster in Minuten",
            min_value=5,
            max_value=180,
            step=5,
            key=window_key,
        )
    tempos = service.tempo(selected_session_id, int(st.session_state[window_key]))
    left, right = st.columns(2)
    with left.container(border=True):
        st.markdown("**Dauer je Spiel**")
        render_raw_tempo(tempos, key="statistics-raw-tempo")
    with right.container(border=True):
        st.markdown("**Geglättetes Spieltempo**")
        render_smoothed_tempo(tempos, key="statistics-smoothed-tempo")
else:
    st.caption("Tempo wird für einen einzelnen Spieltag ausgewertet.")

with st.expander("Spielerdetails", icon=":material/table_chart:"):
    st.dataframe(
        [
            {
                "Spieler": item.name,
                "Punkte": item.total_points,
                "Höchster Sieg": item.highest_win,
                "Höchste Niederlage": item.highest_loss,
                "Gewonnen": item.games_won,
                "Verloren": item.games_lost,
                "Ø Sieg": _decimal(item.average_win_points),
                "Ø Niederlage": _decimal(item.average_loss_points),
                "Soli": item.solos_played,
                "Soli gewonnen": item.solos_won,
                "Soli verloren": item.solos_lost,
                "Solo-Punkte": item.solo_points,
                "Fremdsolo-Punkte": item.foreign_solo_points,
                "Ohne Soli": item.points_without_solos,
                "Re gewonnen": item.re_won,
                "Re verloren": item.re_lost,
                "Re gewonnen %": _decimal(item.re_win_rate * 100) + " %",
                "Re gespielt %": _decimal(item.re_play_rate * 100) + " %",
                "Kontra gewonnen": item.kontra_won,
                "Kontra verloren": item.kontra_lost,
                "Kontra gewonnen %": _decimal(item.kontra_win_rate * 100) + " %",
                "Ø Punkte gew. Re": _decimal(item.average_re_win_points),
                "Ø Punkte gew. Kontra": _decimal(item.average_kontra_win_points),
                "Ø Punkte verl. Re": _decimal(item.average_re_loss_points),
                "Ø Punkte verl. Kontra": _decimal(item.average_kontra_loss_points),
                "Bereinigt ohne Soli": _decimal(item.adjusted_without_solos),
                "Bereinigt mit Soli": _decimal(item.adjusted_with_solos),
                "Differenz": _decimal(item.adjustment_difference),
            }
            for item in statistics.players
        ],
        hide_index=True,
    )

with st.expander("Paardetails", icon=":material/groups:"):
    st.dataframe(
        [
            {
                "Paar": " & ".join(item.players),
                "Spiele": item.games,
                "Gewonnen": item.won,
                "Verloren": item.lost,
                "Bilanz": item.balance,
                "Punkte": item.points,
                "Punkte pro Spiel": _decimal(item.points_per_game),
            }
            for item in statistics.pairs
        ],
        hide_index=True,
    )
