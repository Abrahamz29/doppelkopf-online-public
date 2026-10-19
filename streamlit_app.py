import streamlit as st

from doppelkopf_app.config import get_settings
from doppelkopf_app.ui.authentication import require_app_password
from doppelkopf_app.ui.diagnostics import diagnostic_span, mark_render_complete, mount_diagnostics
from doppelkopf_app.ui.theme import apply_app_theme

st.set_page_config(
    page_title="Doppelkopf Online",
    page_icon=":material/style:",
    layout="wide",
    initial_sidebar_state="auto",
)
apply_app_theme()
require_app_password()
mount_diagnostics()
st.sidebar.caption("Doppelkopf Online · eigene Datenbank")

if get_settings().offline_mode:
    with st.sidebar:
        st.caption(":material/cloud_off: Offline · lokale Datenbank")

page = st.navigation(
    [
        st.Page("app_pages/overview.py", title="Übersicht", icon=":material/home:"),
        st.Page("app_pages/players.py", title="Spieler", icon=":material/group:"),
        st.Page("app_pages/game_sessions.py", title="Spieltage", icon=":material/event:"),
        st.Page("app_pages/live_game.py", title="Spiel", icon=":material/playing_cards:"),
        st.Page(
            "app_pages/live_dashboard.py",
            title="Live-Dashboard",
            icon=":material/dashboard:",
        ),
        st.Page("app_pages/statistics.py", title="Statistik", icon=":material/monitoring:"),
    ]
)
# A saved snapshot belongs only to the immediate rerun of its originating page.
if page.url_path != "live_game":
    st.session_state.pop("live-saved-state", None)
if page.url_path != "live_dashboard":
    st.session_state.pop("dashboard-saved-state", None)
with diagnostic_span("page"):
    page.run()
mark_render_complete()
