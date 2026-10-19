import json
import time
from hashlib import sha256
from hmac import compare_digest, new

import streamlit as st

from doppelkopf_app.config import get_settings

_AUTHENTICATED_KEY = "app-authenticated"
_CLEAR_COOKIE_KEY = "clear-app-auth-cookie"
_COOKIE_NAME = "doko-device-auth"
_COOKIE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60


def _device_token(password: str, expires_at: int) -> str:
    payload = f"v1:{expires_at}"
    signature = new(password.encode("utf-8"), payload.encode("ascii"), sha256).hexdigest()
    return f"{expires_at}.{signature}"


def _valid_device_token(token: str | None, password: str, now: int | None = None) -> bool:
    if not token:
        return False
    try:
        expires_text, supplied_signature = token.split(".", maxsplit=1)
        expires_at = int(expires_text)
    except (TypeError, ValueError):
        return False
    if len(supplied_signature) != 64 or not supplied_signature.isascii():
        return False
    current_time = int(time.time()) if now is None else now
    if expires_at <= current_time:
        return False
    expected_token = _device_token(password, expires_at)
    return compare_digest(token, expected_token)


def _write_device_cookie(token: str, max_age: int) -> None:
    cookie = (
        f"{_COOKIE_NAME}={token}; Path=/; Max-Age={max_age}; "
        "Secure; SameSite=Lax"
    )
    st.html(
        f"<script>document.cookie = {json.dumps(cookie)};</script>",
        unsafe_allow_javascript=True,
    )


def _show_logout_button() -> None:
    with st.sidebar:
        st.button(
            "Abmelden",
            key="app-logout",
            icon=":material/logout:",
            on_click=_logout,
        )


def _logout() -> None:
    st.session_state[_AUTHENTICATED_KEY] = False
    st.session_state[_CLEAR_COOKIE_KEY] = True


def require_app_password() -> None:
    """Stop the current Streamlit run until the shared app password is entered."""
    settings = get_settings()
    if settings.offline_mode or not settings.app_password_required:
        return
    expected_password = settings.app_password
    if expected_password is None:
        return

    just_logged_out = bool(st.session_state.pop(_CLEAR_COOKIE_KEY, False))
    if just_logged_out:
        _write_device_cookie("", 0)

    st.session_state.setdefault(_AUTHENTICATED_KEY, False)
    if not st.session_state[_AUTHENTICATED_KEY] and not just_logged_out:
        remembered_token = st.context.cookies.get(_COOKIE_NAME)
        st.session_state[_AUTHENTICATED_KEY] = _valid_device_token(
            remembered_token, expected_password
        )

    if st.session_state[_AUTHENTICATED_KEY]:
        _show_logout_button()
        return

    st.title("Doppelkopf Manager")
    st.info("Bitte gib das gemeinsame Passwort ein, um die App zu öffnen.")
    with st.form("app-login", border=True):
        entered_password = st.text_input(
            "Passwort",
            type="password",
            key="app-password",
            autocomplete="current-password",
        )
        submitted = st.form_submit_button(
            "Anmelden",
            type="primary",
            icon=":material/login:",
        )

    if submitted:
        st.session_state[_AUTHENTICATED_KEY] = compare_digest(
            entered_password.encode("utf-8"),
            expected_password.encode("utf-8"),
        )
        if st.session_state[_AUTHENTICATED_KEY]:
            expires_at = int(time.time()) + _COOKIE_MAX_AGE_SECONDS
            _write_device_cookie(
                _device_token(expected_password, expires_at), _COOKIE_MAX_AGE_SECONDS
            )
            st.rerun()
        st.error("Das Passwort ist nicht korrekt.")

    st.stop()
