from io import BytesIO

import segno
import streamlit as st

from doppelkopf_app.config import get_settings
from doppelkopf_app.infrastructure.phone_link import game_page_url, local_network_choices

_network_choices = st.cache_data(ttl=15, show_spinner=False)(local_network_choices)


def phone_qr_png(url: str) -> bytes:
    """Encode a standard QR code with a white quiet zone for phone cameras."""
    buffer = BytesIO()
    segno.make_qr(url, error="m").save(
        buffer, kind="png", scale=8, border=4, dark="black", light="white"
    )
    return buffer.getvalue()


@st.dialog("Handy verbinden", width="small")
def show_phone_connection() -> None:
    """Show a compact QR dialog linking to mobile score entry."""
    try:
        browser_url = st.context.url or ""
        base_url = get_settings().public_base_url
        networks = _network_choices(browser_url) if not base_url else ()
        lan_ip = networks[0].address if networks else None
        if len(networks) > 1:
            st.caption("Mehrere Netzwerke sind verbunden. Wähle das Netzwerk deines Handys.")
            lan_ip = st.selectbox(
                "Netzwerk", [item.address for item in networks],
                format_func=lambda address: next(
                    f"{item.name} · {item.address}" for item in networks if item.address == address
                ),
                key="phone-connection-network",
            )
        url = game_page_url(browser_url, public_base_url=base_url, lan_ip=lan_ip)
    except ValueError as error:
        st.warning(str(error))
        return
    st.write("Mit der Handykamera scannen, um Spiele einzugeben.")
    with st.container(horizontal_alignment="center"):
        st.image(phone_qr_png(url), width=280)
    st.link_button("Spiel auf diesem Gerät öffnen", url)
    st.caption(url)
    st.caption("Bei lokalem Betrieb müssen Handy und Rechner im selben WLAN/LAN sein.")
