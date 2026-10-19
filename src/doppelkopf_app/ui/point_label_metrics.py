"""Independent browser measurements for each player-history chart."""

from collections.abc import Sequence
from hashlib import sha256
from math import isfinite
from pathlib import Path

import streamlit as st

from doppelkopf_app.ui.chart_styles import PlayerLineStyle
from doppelkopf_app.ui.point_labels import PlotMetrics

_COMPONENT = st.components.v2.component(
    "doko_point_label_metrics_v1",
    html='<span aria-hidden="true"></span>',
    js=Path(__file__).with_suffix(".js").read_text(encoding="utf-8"),
)


def point_bounds_name(key: str) -> str:
    """Give each chart a stable SVG measurement target, safe in CSS selectors."""
    return "doko_plot_bounds_" + sha256(key.encode("utf-8")).hexdigest()[:20]


def _measurement(value: object, *, minimum: float, maximum: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not minimum <= value <= maximum:
        return None
    number = float(value)
    return number if isfinite(number) else None


def _parse_metrics(value: object, styles: Sequence[PlayerLineStyle]) -> PlotMetrics | None:
    if not isinstance(value, dict):
        return None
    width = _measurement(value.get("width"), minimum=16, maximum=20_000)
    height = _measurement(value.get("height"), minimum=16, maximum=20_000)
    font_size = _measurement(value.get("font_size"), minimum=10, maximum=32)
    players = value.get("players")
    if width is None or height is None or font_size is None or not isinstance(players, list):
        return None
    if font_size != (18 if width >= 800 else 14) or len(players) != len(styles):
        return None
    text_half_height = None
    if "text_half_height" in value:
        text_half_height = _measurement(value["text_half_height"], minimum=font_size / 2,
                                        maximum=font_size * 3)
        if text_half_height is None:
            return None
    expected = {style.player_id: style.name for style in styles}
    text_widths: dict[int, float] = {}
    for player in players:
        if not isinstance(player, dict):
            return None
        identity = player.get("id")
        if type(identity) is not int or identity not in expected or identity in text_widths:
            return None
        if player.get("name") != expected[identity]:
            return None
        text_width = _measurement(player.get("width"), minimum=0.5, maximum=20_000)
        if text_width is None:
            return None
        text_widths[identity] = text_width
    if text_widths.keys() != expected.keys():
        return None
    return PlotMetrics(width=width, height=height, font_size=font_size, text_widths=text_widths,
                       text_half_height=text_half_height)


def read_point_label_metrics(
    key: str, styles: Sequence[PlayerLineStyle],
) -> PlotMetrics | None:
    """Return validated measurements for the current player names, once available."""
    state = st.session_state.get(f"{key}-label-metrics")
    return _parse_metrics(getattr(state, "metrics", None), styles)


def _metrics_changed() -> None:
    """Let the component's state update trigger the next chart render."""


def mount_point_label_metrics(key: str, styles: Sequence[PlayerLineStyle]) -> None:
    """Measure the native SVG without changing its DOM or logging game contents."""
    component_key = f"{key}-label-metrics"
    state = st.session_state.get(component_key)
    _COMPONENT(
        key=component_key,
        height=0,
        data={
            "selector": f".{point_bounds_name(key)}_marks",
            "players": [{"id": style.player_id, "name": style.name} for style in styles],
            "previous": getattr(state, "metrics", None),
        },
        on_metrics_change=_metrics_changed,
    )
