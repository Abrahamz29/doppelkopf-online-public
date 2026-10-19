"""Shared chart preference editor; persistence stays in the application service."""
from base64 import b64encode
from collections.abc import Sequence
from html import escape

import streamlit as st

from doppelkopf_app.application.services import (
    DoppelkopfService,
    PlayerNotFoundError,
    PlayerSummary,
)
from doppelkopf_app.ui.chart_styles import (
    LINE_DASHES,
    LINE_KEYS,
    LINE_NAMES,
    PALETTE,
    player_line_styles,
)


def _palette_label(name: str) -> str:
    """Show the exact chart color inside its native, keyboard-accessible option."""
    if name not in PALETTE:
        return name
    swatch = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        'viewBox="0 0 24 24">'
        '<rect x="1" y="1" width="22" height="22" rx="4" fill="white"/>'
        f'<rect x="2" y="2" width="20" height="20" rx="3" fill="{PALETTE[name]}" '
        'stroke="#666" stroke-width="1"/></svg>'
    )
    encoded = b64encode(swatch.encode("ascii")).decode("ascii")
    return f"![](data:image/svg+xml;base64,{encoded}) {name}"


def render_chart_color_options(
    service: DoppelkopfService,
    players: Sequence[PlayerSummary],
    *,
    key: str,
    displayed_ids: Sequence[int] = (),
    player_id: int | None = None,
) -> None:
    """Preview and save a player's color and line pattern together."""
    st.markdown("**Diagrammfarben und Linien**")
    st.caption("Farben und Linientypen gelten für diesen Spieler auf allen Geräten und Spieltagen.")
    if not players:
        st.info("Lege zuerst einen Spieler an.")
        return
    if player_id is None:
        player_id = st.selectbox(
            "Diagrammstil für", [player.id for player in players],
            format_func=lambda value: next(p.name for p in players if p.id == value),
            key=f"{key}-player",
        )
    player = next(p for p in players if p.id == player_id)
    shown = [p for p in players if not displayed_ids or p.id in displayed_ids or p.id == player_id]
    styles = player_line_styles(shown, dark=st.context.theme.type == "dark")
    style = next(s for s in styles if s.player_id == player_id)
    # A saved or remotely changed preference starts a fresh draft without changing
    # widget state after instantiation. Switching players cannot leak draft colors.
    prefix = f"{key}-{player_id}-{player.chart_color or 'auto'}"
    labels = [*PALETTE, "Eigene Farbe"]
    initial = next(
        (name for name, color in PALETTE.items() if color == style.color), "Eigene Farbe"
    )
    selection = st.pills(
        "Farbpalette · Farbe direkt antippen", labels, default=initial,
        selection_mode="single", required=True, format_func=_palette_label,
        key=f"{prefix}-palette",
    ) or initial
    st.caption(f":material/check: Ausgewählt: {selection}")
    if selection == "Eigene Farbe":
        color = st.color_picker("Eigene Farbe wählen", style.color, key=f"{prefix}-custom")
    else:
        color = PALETTE[selection]
    line_key = f"{key}-{player_id}-{player.chart_line or 'auto'}-line"
    selected_line = st.selectbox(
        "Linientyp", LINE_KEYS,
        index=LINE_KEYS.index(player.chart_line) if player.chart_line else
        LINE_NAMES.index(style.pattern_name),
        format_func=lambda value: LINE_NAMES[LINE_KEYS.index(value)], key=line_key,
    )
    line_index = LINE_KEYS.index(selected_line)
    dash = " ".join(str(part) for part in LINE_DASHES[line_index])
    st.html(
        '<div style="display:flex;align-items:center;gap:10px">'
        '<svg width="100" height="24" aria-hidden="true">'
        f'<line x1="2" y1="12" x2="98" y2="12" stroke="{escape(color)}" '
        f'stroke-width="3" stroke-dasharray="{dash}"/></svg>'
        f'<span>{escape(player.name)} · {LINE_NAMES[line_index]} · '
        f'{escape(color.upper())}</span></div>'
    )
    matches = [s.name for s in styles if s.player_id != player_id and s.color == color.upper()]
    if matches:
        st.info(
            "Diese Farbe verwendet auch: " + ", ".join(matches)
            + ". Wähle zur Unterscheidung bei Bedarf ein anderes Linienmuster."
        )
    st.caption(
        "Aktuell gespeichert: " + (player.chart_color or "Automatische Farbe")
        + " · " + (
            LINE_NAMES[LINE_KEYS.index(player.chart_line)] if player.chart_line
            else "Automatischer Linientyp"
        ) + ". Farbe und Linientyp werden gemeinsam gespeichert."
    )
    save = st.button(
        "Diagrammstil speichern", key=f"{key}-save", icon=":material/save:", width="stretch"
    )
    with st.container(horizontal=True):
        reset = st.button("Automatische Farbe verwenden", key=f"{key}-reset")
        reset_line = st.button("Automatischen Linientyp verwenden", key=f"{key}-reset-line")
    if save or reset or reset_line:
        try:
            if save:
                service.set_player_chart_style(player_id, color, selected_line)
            elif reset:
                service.set_player_chart_color(player_id, None)
            else:
                service.set_player_chart_line(player_id, None)
        except PlayerNotFoundError:
            st.error("Der Spieler ist nicht mehr vorhanden. Bitte lade die Seite neu.")
        except ValueError as error:
            st.error(str(error))
        else:
            # Remove draft widget values before the next run, including when the
            # user resets an already automatic preference.
            if save or reset:
                for suffix in ("palette", "custom"):
                    st.session_state.pop(f"{prefix}-{suffix}", None)
            if save or reset_line:
                st.session_state.pop(line_key, None)
            st.rerun()
