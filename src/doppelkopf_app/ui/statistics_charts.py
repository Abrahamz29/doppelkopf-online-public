"""Small aggregate-only bar charts with browser-local KPI selection."""

from collections.abc import Callable
from decimal import Decimal
from typing import Any

import streamlit as st

from doppelkopf_app.domain.statistics import PairStatistics, PlayerStatistics, Statistics

PLAYER_BAR_METRICS: dict[str, Callable[[PlayerStatistics], int | Decimal]] = {
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
PAIR_BAR_METRICS: dict[str, Callable[[PairStatistics], int | Decimal]] = {
    "Spiele": lambda item: item.games,
    "Gewonnen": lambda item: item.won,
    "Verloren": lambda item: item.lost,
    "Bilanz": lambda item: item.balance,
    "Punkte": lambda item: item.points,
    "Punkte pro Spiel": lambda item: item.points_per_game,
}


@st.fragment
def render_point_distribution(statistics: Statistics) -> None:
    """Filter precomputed frequencies without reloading the statistics page."""
    distributions = {
        "Gesamt": statistics.point_frequency,
        "Re (Normalspiel)": statistics.re_point_frequency,
        "Kontra (Normalspiel)": statistics.kontra_point_frequency,
        "Solo Re": statistics.solo_re_point_frequency,
    }
    selection = st.selectbox(
        "Punkteverteilung für", distributions, key="statistics-point-distribution",
        help="Re und Kontra: gewonnene Normalspiele ohne Solos. "
        "Solo Re: gewonnene Solos, mit dem dreifachen Punktewert des Solisten. "
        "Gesamt: alle Spiele einschließlich verlorener Solos und Nullrunden.",
    )
    frequency = distributions[selection]
    if not frequency:
        st.info("Für diesen Filter sind keine Spiele vorhanden.")
        return
    st.bar_chart(
        [{"Punktewert": points, "Häufigkeit": count} for points, count in frequency],
        x="Punktewert", y="Häufigkeit",
    )



def render_statistics_bars(statistics: Statistics, *, pairs: bool = False) -> None:
    """Send one row per player/pair; switching KPI never requests a Python rerun."""
    category = "Paar" if pairs else "Spieler"
    metrics = list(PAIR_BAR_METRICS if pairs else PLAYER_BAR_METRICS)
    rows: list[dict[str, str | int | float]]
    if pairs:
        rows = [
            {category: " & ".join(item.players),
             **{name: float(getter(item)) for name, getter in PAIR_BAR_METRICS.items()}}
            for item in statistics.pairs
        ]
    else:
        rows = [
            {category: item.name,
             **{name: float(getter(item)) for name, getter in PLAYER_BAR_METRICS.items()}}
            for item in statistics.players
        ]
    label = "Kennzahl der Paare im Balkendiagramm" if pairs else "Kennzahl im Balkendiagramm"
    default = "Punkte pro Spiel" if pairs else "Punkte insgesamt"
    spec: dict[str, Any] = {
        "usermeta": {"embedOptions": {"renderer": "svg"}},
        "params": [{"name": "selected_kpi", "value": default,
                    "bind": {"input": "select", "options": metrics, "name": label}}],
        "transform": [
            {"calculate": "datum[selected_kpi]", "as": "Wert"},
            {"calculate": "selected_kpi", "as": "Kennzahl"},
        ],
        "mark": "bar",
        "encoding": {
            "x": {"field": category, "type": "nominal", "sort": None},
            "y": {"field": "Wert", "type": "quantitative", "scale": {"zero": True}},
            "tooltip": [
                {"field": category, "type": "nominal"},
                {"field": "Kennzahl", "type": "nominal"},
                {"field": "Wert", "type": "quantitative"},
            ],
        },
    }
    st.vega_lite_chart(
        rows, spec, key="pair-kpi-chart" if pairs else "player-kpi-chart",
        width="stretch", on_select="ignore",
    )
