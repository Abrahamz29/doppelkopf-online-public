"""Bounded, content-free diagnostics for intermittent rendering failures."""

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from uuid import uuid4

import streamlit as st

_LOGGER = logging.getLogger(__name__)
_KEY = "doko-diagnostics-browser"
_EVENTS = {
    "mounted", "error", "rejection", "offline", "online", "blank", "restored",
    "submit", "rendered", "transport",
}


def sanitize_browser_events(value: object) -> list[dict[str, str | int]]:
    """Accept only bounded technical metadata, never arbitrary browser text."""
    if not isinstance(value, list):
        return []
    result: list[dict[str, str | int]] = []
    for item in value[-40:]:
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("event"), str)
            or item["event"] not in _EVENTS
        ):
            continue
        row: dict[str, str | int] = {"event": item["event"]}
        for key in ("id", "at", "run"):
            field = item.get(key)
            if (
                isinstance(field, str) and len(field) <= 80
                and all(c.isalnum() or c in "-:._TZ" for c in field)
            ):
                row[key] = field
        for key in ("elements", "line", "column"):
            field = item.get(key)
            if type(field) is int and 0 <= field <= 10_000_000:
                row[key] = field
        error_type = item.get("error_type")
        if isinstance(error_type, str) and error_type in {
            "Error", "TypeError", "ReferenceError", "SyntaxError", "RangeError",
        }:
            row["error_type"] = error_type
        result.append(row)
    return result


def record_event(event: str, **details: str | int) -> None:
    """Write correlated server events and retain the latest 200 for download."""
    session = st.session_state.setdefault("diagnostic-session", uuid4().hex)
    row = {
        "at": datetime.now(UTC).isoformat(), "session": session,
        "event": event, **details,
    }
    rows = st.session_state.get("diagnostic-events", [])
    st.session_state["diagnostic-events"] = [*rows[-199:], row]
    # Alembic's fileConfig disables pre-existing application loggers on first load.
    _LOGGER.disabled = False
    _LOGGER.warning("DOKO_DIAGNOSTIC %s", json.dumps(row, ensure_ascii=True))


@contextmanager
def diagnostic_span(name: str) -> Iterator[None]:
    """Log completion, failure, or Streamlit interruption without swallowing it."""
    operation = uuid4().hex
    started = monotonic()
    record_event(f"{name}.start", operation=operation)
    outcome = "interrupted"
    try:
        yield
    except Exception as error:
        outcome = "error"
        record_event(f"{name}.error", operation=operation, error_type=type(error).__name__)
        raise
    else:
        outcome = "complete"
    finally:
        record_event(
            f"{name}.end", operation=operation, outcome=outcome,
            duration_ms=int((monotonic() - started) * 1000),
        )


def _receive_report() -> None:
    state = st.session_state.get(_KEY)
    events = sanitize_browser_events(getattr(state, "report", None))
    seen = st.session_state.get("diagnostic-seen", [])
    for event in events:
        identity = event.get("id")
        if not identity or identity in seen:
            continue
        record_event("browser", payload=json.dumps(event))
        seen.append(identity)
    st.session_state["diagnostic-seen"] = seen[-200:]
    st.session_state["diagnostic-ack"] = [event["id"] for event in events if "id" in event]


_COMPONENT = st.components.v2.component(
    "doko_diagnostics_v1",
    html='<span aria-hidden="true"></span>',
    js=Path(__file__).with_name("diagnostics.js").read_text(encoding="utf-8"),
)


@st.fragment(run_every="15s")
def _browser_probe(run: str) -> None:
    _COMPONENT(
        key=_KEY, height=0,
        data={"run": run, "ack": st.session_state.get("diagnostic-ack", [])},
        on_report_change=_receive_report,
    )


def mount_diagnostics() -> None:
    """Install a browser recorder and an optional report download after login."""
    run = uuid4().hex
    st.session_state["diagnostic-run"] = run
    record_event("render.start", run=run, streamlit=st.__version__)
    _browser_probe(run)
    with st.sidebar.expander("Technische Diagnose"):
        st.caption("Automatische Fehleraufzeichnung aktiv. Keine Spielinhalte enthalten.")
        st.download_button(
            "Diagnose herunterladen",
            json.dumps(st.session_state.get("diagnostic-events", []), indent=2),
            file_name="doppelkopf-diagnose.json", mime="application/json",
            on_click="ignore",
        )


def mark_render_complete() -> None:
    """Place a nonvisual browser marker after a successful page build."""
    run = st.session_state["diagnostic-run"]
    record_event("render.complete", run=run)
    st.html(f'<span hidden data-doko-render="{run}"></span>')
