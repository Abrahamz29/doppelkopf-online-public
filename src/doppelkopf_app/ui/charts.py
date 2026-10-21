from collections.abc import Sequence
from decimal import Decimal
from math import log
from typing import Any, Literal

import streamlit as st

from doppelkopf_app.domain.tempo import RoundTempo
from doppelkopf_app.ui.chart_styles import PlayerLineStyle
from doppelkopf_app.ui.point_label_layers import add_point_label_layers


def render_points_progress(
    rows: Sequence[dict[str, int]],
    player_names: Sequence[str],
    *,
    key: str,
    styles: Sequence[PlayerLineStyle],
    height: int | Literal["content", "stretch"] = "content",
    dashboard: bool = True,
    value_label: str = "Punkte",
) -> None:
    """Render exact point totals with redundant color and line-pattern encoding."""
    # Axis text must depend on the viewport, not the remaining plot width:
    # two axes would otherwise alternate font sizes around the width threshold.
    label_size = {
        "expr": "(windowSize()[0] >= 1280 ? 18 : 10) * (windowSize()[0] >= 768 ? 1.3 : 1)"
    } if dashboard else 10
    title_size = {
        "expr": "(windowSize()[0] >= 1280 ? 20 : 10) * (windowSize()[0] >= 768 ? 1.3 : 1)"
    } if dashboard else 10
    legend_size = {"expr": "width >= 800 ? 18 : 12"} if dashboard else 12
    by_name = {style.name: style for style in styles}
    ordered = sorted((by_name[name] for name in player_names), key=lambda item: item.player_id)
    names = [style.name for style in ordered]
    last_game = max((row["Spiel"] for row in rows), default=1)
    # Vega's horizontal default can overflow a narrow mobile chart. Reserve space
    # for each line sample and wrap entries as the actual plot width changes.
    legend_columns = "width < 280 ? 1 : width < 700 ? 2 : 4"
    label_limit = f"max(40, width / ({legend_columns}) - (width < 700 ? 56 : 80))"
    legend = {"orient": "bottom", "symbolType": "stroke",
              "symbolSize": {"expr": "width < 700 ? 576 : 2304"},
              "columns": {"expr": legend_columns}, "direction": "horizontal",
              "labelLimit": {"expr": label_limit},
              "columnPadding": 12, "rowPadding": 8,
              "symbolStrokeWidth": 3, "offset": 5, "titlePadding": 5,
              "labelFontSize": legend_size}
    # Dense histories can make collision-free name placement prohibitively costly.
    # Keep every point, but use the existing accessible legend above 500 games.
    inline_names = dashboard and len(rows) <= 500
    spec: dict[str, Any] = {
            "encoding": {
                "x": {"field": "Spiel", "type": "quantitative",
                      "scale": {"domain": [1, last_game], "nice": False, "zero": False},
                      "axis": {"tickMinStep": 1, "grid": False,
                               "labelFontSize": label_size, "titleFontSize": title_size}},
                "y": {"field": "Punkte", "type": "quantitative", "title": "",
                      "axis": {"tickMinStep": 1, "labelFontSize": label_size}},
                "color": {"field": "Spieler", "type": "nominal", "title": " ",
                          "scale": {"domain": names, "range": [s.color for s in ordered]},
                          "legend": None if inline_names else legend},
                "strokeDash": {"field": "Spieler", "type": "nominal", "title": " ",
                               "scale": {"domain": names,
                                         "range": [list(s.dash) for s in ordered]},
                               "legend": None if inline_names else legend},
                "tooltip": [{"field": "Spiel", "type": "quantitative"},
                            {"field": "Punkte", "type": "quantitative", "title": value_label},
                            {"field": "Spieler", "type": "nominal"}],
            },
            "layer": [
                {"mark": {"type": "line", "strokeWidth": 3}},
                {"mark": {"type": "point", "opacity": 0},
                 "params": [{"name": "nearest", "select": {
                     "type": "point", "nearest": True, "on": "mousemove",
                     "fields": ["Spiel"], "clear": "mouseleave"}}]},
                {"mark": {"type": "point", "filled": True, "size": 65},
                 "transform": [{"filter": {"param": "nearest", "empty": False}}]},
            ],
        }
    if len(rows) == 1:
        spec["layer"][0]["mark"]["point"] = True
    if dashboard:
        # Rounded corners stay within the label solver's stroke-radius margin.
        spec["layer"][0]["mark"]["strokeJoin"] = "round"
    if inline_names and rows:
        add_point_label_layers(spec, rows, ordered, key=key)
    if dashboard:
        _add_desktop_right_axis(spec)
    st.vega_lite_chart(
        [{"Spiel": row["Spiel"], "Spieler": name, "Punkte": row[name]}
         for row in rows for name in player_names],
        spec,
        width="stretch", height=height, key=key,
    )
    if inline_names and rows:
        from doppelkopf_app.ui.point_label_metrics import mount_point_label_metrics

        mount_point_label_metrics(key, ordered)


def _add_desktop_right_axis(spec: dict[str, Any]) -> None:
    """Mirror the shared point scale on wide screens without a mobile gutter."""
    y = spec["encoding"]["y"]
    # Independent guides share one scale. Only the line owns the left guide;
    # selection points must not create additional copies of it.
    for layer in spec["layer"]:
        if layer["mark"]["type"] == "point":
            layer.setdefault("encoding", {})["y"] = {**y, "axis": None}
    desktop = "windowSize()[0] >= 768"
    spec["resolve"] = {"scale": {"y": "shared"}, "axis": {"y": "independent"}}
    spec["layer"].append({
        "name": "doko_right_axis",
        "mark": {"type": "point", "opacity": 0, "aria": False},
        "encoding": {
            "x": {"value": 0},
            "y": {**y, "axis": {
                **y["axis"], "orient": "right", "grid": False, "title": None,
                "labelExpr": f"{desktop} ? datum.label : ''",
                "labelPadding": {"expr": f"{desktop} ? 5 : 0"},
                "tickSize": {"expr": f"{desktop} ? 5 : 0"},
                "domainOpacity": {"expr": f"{desktop} ? 1 : 0"},
                "minExtent": 0,
            }},
            "tooltip": {"value": None},
        },
    })


def _render_tempo_segments(
    tempos: Sequence[RoundTempo], *, smoothed: bool, key: str,
    height: int | Literal["content", "stretch"] = "content",
) -> None:
    if not tempos:
        st.caption("Nach dem zweiten gespeicherten Spiel verfügbar.")
        return
    label = "Minuten pro Spiel" if smoothed else "Minuten"
    with st.expander("Y-Achse"):
        logarithmic = st.toggle("Logarithmische Y-Achse", key=f"{key}-logarithmic")
        base = st.number_input(
            "Logarithmusbasis (Minuten bei Achsenwert 1)",
            min_value=2, value=5, step=1, disabled=not logarithmic,
            key=f"{key}-log-base",
        )
        if logarithmic:
            st.caption(
                f"1 Minute → 0 · {base} Minuten → 1 · {base * base} Minuten → 2. "
                "Unter 1 Minute sind die Werte negativ. "
                "Der Tooltip zeigt weiterhin die Dauer in Minuten."
            )
    axis_label = f"log{base}({label})" if logarithmic else label
    rows = []
    for item in tempos:
        minutes = float(item.minutes_per_game if smoothed
                        else Decimal(item.duration_seconds) / Decimal(60))
        rows.append({
            "Zeit": item.completed_at.isoformat(), "Spiel": item.sequence,
            "Abschnitt": item.segment, label: minutes,
            axis_label: log(minutes, base) if logarithmic and minutes > 0
            else (None if logarithmic else minutes),
        })
    if logarithmic and any(row[axis_label] is None for row in rows):
        st.caption("Dauern von 0 Minuten sind logarithmisch nicht darstellbar.")
    spec: dict[str, Any] = {
        "layer": [{"mark": {"type": "line", "point": True, "strokeWidth": 3}}],
         "encoding": {
             "x": {"field": "Zeit", "type": "temporal"},
             "y": {"field": axis_label, "type": "quantitative", "axis": {}},
             "detail": {"field": "Abschnitt", "type": "nominal"},
             "tooltip": [{"field": "Spiel", "type": "quantitative"},
                         {"field": "Zeit", "type": "temporal"},
                         {"field": label, "type": "quantitative"}],
         }}
    _add_desktop_right_axis(spec)
    st.vega_lite_chart(
        rows, spec,
        width="stretch", height=height, key=key,
    )


def render_round_values(values: Sequence[tuple[int, int]], *, key: str) -> None:
    """Show the point value of each game with the common responsive axes."""
    spec: dict[str, Any] = {
        "layer": [{"mark": {"type": "line", "strokeWidth": 3, "point": len(values) == 1}}],
        "encoding": {
            "x": {"field": "Spiel", "type": "quantitative", "axis": {"tickMinStep": 1}},
            "y": {"field": "Punktewert", "type": "quantitative",
                  "axis": {"tickMinStep": 1}},
            "tooltip": [{"field": "Spiel", "type": "quantitative"},
                        {"field": "Punktewert", "type": "quantitative"}],
        },
    }
    _add_desktop_right_axis(spec)
    st.vega_lite_chart(
        [{"Spiel": game, "Punktewert": points} for game, points in values],
        spec, key=key, width="stretch",
    )


def render_raw_tempo(tempos: Sequence[RoundTempo], *, key: str) -> None:
    _render_tempo_segments(tempos, smoothed=False, key=key)


def render_smoothed_tempo(
    tempos: Sequence[RoundTempo], *, key: str,
    height: int | Literal["content", "stretch"] = "content",
) -> None:
    _render_tempo_segments(tempos, smoothed=True, key=key, height=height)


def tempo_label(tempos: Sequence[RoundTempo]) -> tuple[str, str]:
    if not tempos:
        return "–", "Noch nicht verfügbar"
    current = tempos[-1]
    return (
        f"{current.minutes_per_game.quantize(Decimal('0.1'))} min/Spiel",
        f"{current.games_per_hour.quantize(Decimal('0.1'))} Spiele/Stunde",
    )
