from __future__ import annotations

import hashlib
import hmac

import streamlit as st


SECRET_KEY = "app_password"
_AUTHENTICATED = "_ppd_authenticated"
_INPUT_KEY = "_ppd_password_input"


def configured_password() -> str | None:
    try:
        value = st.secrets.get(SECRET_KEY)
    except Exception:
        return None
    if value is None:
        return None
    password = str(value).strip()
    return password or None


def require_password() -> None:
    expected = configured_password()
    if expected is None:
        return
    if st.session_state.get(_AUTHENTICATED):
        return
    _render_login(expected)
    st.stop()


def render_logout() -> None:
    if configured_password() is None or not st.session_state.get(_AUTHENTICATED):
        return
    if st.sidebar.button("Выйти", key="_ppd_logout"):
        st.session_state[_AUTHENTICATED] = False
        st.rerun()


def _matches(entered: str, expected: str) -> bool:
    return hmac.compare_digest(
        hashlib.sha256(entered.encode("utf-8")).digest(),
        hashlib.sha256(expected.encode("utf-8")).digest(),
    )


def _render_login(expected: str) -> None:
    _, middle, _ = st.columns([1, 1.4, 1])
    with middle:
        st.markdown("## ⚡ Энергоаудит ППД")
        st.caption("Доступ к дашборду ограничен. Введите пароль.")
        with st.form("_ppd_login_form"):
            entered = st.text_input("Пароль", type="password", key=_INPUT_KEY)
            submitted = st.form_submit_button("Войти")
        if not submitted:
            return
        if _matches(entered or "", expected):
            st.session_state[_AUTHENTICATED] = True
            st.session_state.pop(_INPUT_KEY, None)
            st.rerun()
        st.error("Неверный пароль.")
