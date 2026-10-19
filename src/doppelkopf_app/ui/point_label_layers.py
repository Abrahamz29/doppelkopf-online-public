"""Native Vega-Lite layers for stable labels inside player-history plots."""

from collections.abc import Sequence
from typing import Any

import streamlit as st

from doppelkopf_app.ui.chart_styles import PlayerLineStyle
from doppelkopf_app.ui.point_labels import LabelLayout, plan_point_labels


def add_point_label_layers(
    spec: dict[str, Any],
    rows: Sequence[dict[str, int]],
    styles: Sequence[PlayerLineStyle],
    *,
    key: str,
) -> None:
    """Add measured labels without including their positions in the point scales."""
    from doppelkopf_app.ui.point_label_metrics import point_bounds_name, read_point_label_metrics

    values = [row[style.name] for row in rows for style in styles]
    low, high = min(0, *values), max(0, *values)
    padding = max(1, (high - low + 9) // 10)
    domain = (low - padding, high + padding)
    spec["encoding"]["y"]["scale"] = {"domain": list(domain), "nice": False}
    spec["usermeta"] = {"embedOptions": {"renderer": "svg"}}

    # This named, invisible native mark exposes the real plot size to the
    # read-only browser probe, excluding axes, padding and legend.
    spec["layer"].insert(0, {
        "name": point_bounds_name(key), "data": {"values": [{}]},
        "mark": {"type": "rect", "opacity": 0, "aria": False},
        "encoding": {
            "x": {"value": 0}, "x2": {"value": {"expr": "width"}},
            "y": {"value": 0}, "y2": {"value": {"expr": "height"}},
            "color": {"value": "transparent"}, "strokeDash": {"value": []},
            "tooltip": {"value": None},
        },
    })
    metrics = read_point_label_metrics(key, styles)
    if metrics is None:
        return
    state_key = f"{key}-point-label-layout"
    saved = st.session_state.get(state_key)
    previous = saved if isinstance(saved, LabelLayout) else None
    layout = plan_point_labels(rows, styles, metrics, domain, previous)
    if layout is None:
        return
    st.session_state[state_key] = layout
    by_id = {style.player_id: style for style in styles}
    anchor_row = next(row for row in rows if row["Spiel"] == layout.anchor_game)
    labels = [{
        "Spieler": by_id[item.player_id].name,
        "Spiel": item.game,
        "Punkte": anchor_row[by_id[item.player_id].name],
        "label_x": item.x / metrics.width,
        "label_y": item.y / metrics.height,
        "point_x": item.point_x / metrics.width,
        "point_y": item.point_y / metrics.height,
    } for item in layout.placements]
    positions = {
        "x": {"value": {"expr": "datum.label_x * width"}},
        "y": {"value": {"expr": "datum.label_y * height"}},
        "strokeDash": {"value": []},
    }
    # Positions scale immediately on resize, while the font does not. Hide stale
    # boxes until the browser probe supplies dimensions for a fresh safe layout.
    measured_size = (f"abs(width - {metrics.width}) < 1 && "
                     f"abs(height - {metrics.height}) <= 0.5")
    # Explicit mark positions keep the original integer point data and domains
    # intact, independent of the label geometry.
    # Leaders start beyond the right-aligned name and its two-pixel halo.
    leaders = [label for item, label in zip(layout.placements, labels, strict=True)
               if item.needs_leader]
    if leaders:
        spec["layer"].append({
            "name": "doko_label_leaders",
            "data": {"values": leaders},
            "mark": {"type": "rule", "strokeWidth": 1,
                     "opacity": {"expr": f"{measured_size} ? 0.65 : 0"}},
            "encoding": {
                **positions,
                "x": {"value": {"expr": "datum.label_x * width + 4"}},
                "x2": {"value": {"expr": "datum.point_x * width"}},
                "y2": {"value": {"expr": "datum.point_y * height"}},
            },
        })
    text_mark: dict[str, Any] = {
        "type": "text", "align": "right", "baseline": "middle",
        "font": "sans-serif", "fontWeight": 600, "fontSize": layout.font_size,
        # Geometry reserves the full measured name; rendering must never shorten it.
        "limit": 0, "clip": False,
        "opacity": {"expr": f"{measured_size} ? 1 : 0"},
    }
    background = "#15110E" if st.context.theme.type == "dark" else "#FFF9E8"
    for halo in (True, False):
        spec["layer"].append({
            "name": "doko_label_halo" if halo else "doko_player_labels",
            "data": {"values": labels},
            "mark": {
                **text_mark,
                **({"stroke": background, "strokeWidth": 4, "strokeJoin": "round",
                    "aria": False} if halo else {}),
            },
            "encoding": {**positions, "text": {"field": "Spieler", "type": "nominal"}},
        })
