import socket
from contextlib import suppress
from ipaddress import ip_address
from urllib.parse import urlsplit, urlunsplit

from doppelkopf_app.infrastructure.network_adapters import LanAddress, windows_lan_addresses


def _local_only(host: str) -> bool:
    if host.lower().rstrip(".") == "localhost":
        return True
    try:
        address = ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_unspecified


def detect_lan_ip() -> str | None:
    """Find the server's routed IPv4 address without sending network packets."""
    networks = windows_lan_addresses()
    if networks is not None:
        return networks[0].address if networks else None
    candidates: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.connect(("192.0.2.1", 9))
            candidates.append(str(connection.getsockname()[0]))
    except OSError:
        pass  # Offline networks without a default route use hostname resolution below.
    with suppress(OSError):
        candidates.extend(socket.gethostbyname_ex(socket.gethostname())[2])
    return next(
        (candidate for candidate in candidates
         if not _local_only(candidate) and not ip_address(candidate).is_link_local),
        None,
    )


def local_network_choices(browser_url: str) -> tuple[LanAddress, ...]:
    """Offer connected networks only when a loopback URL needs replacing."""
    host = urlsplit(browser_url).hostname
    if not host or not _local_only(host):
        return ()
    return windows_lan_addresses() or ()


def game_page_url(
    browser_url: str, *, public_base_url: str | None = None, lan_ip: str | None = None,
) -> str:
    """Build a phone-accessible game URL, preserving deployment paths and ports."""
    url = urlsplit(public_base_url or browser_url)
    host = url.hostname
    if url.scheme not in {"http", "https"} or not host or url.username or url.password:
        raise ValueError("Die Adresse der App konnte nicht ermittelt werden.")
    # Reading the port also validates malformed/out-of-range ports.
    port = url.port
    netloc = url.netloc
    if _local_only(host):
        lan_ip = lan_ip or detect_lan_ip()
        if lan_ip is None:
            raise ValueError(
                "Keine LAN-IP gefunden. Bitte die App über ihre Netzwerkadresse öffnen."
            )
        netloc = lan_ip + (f":{port}" if port is not None else "")
    path = url.path.rstrip("/")
    if not public_base_url:
        if host.endswith(".streamlit.app") and path.startswith("/~/+/"):
            path = path.removeprefix("/~/+")
        path = path.rsplit("/", 1)[0]
    return urlunsplit((url.scheme, netloc, path + "/live_game", "", ""))
