from __future__ import annotations

import pytest


pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest


APP = "app/main.py"
PASSWORD = "очень-секретно"


def _app(password: str | None = None) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=240)
    if password is not None:
        at.secrets["app_password"] = password
    return at


def _texts(at: AppTest) -> str:
    return "\n".join(str(el.value) for el in list(at.markdown) + list(at.caption))


def test_without_secret_the_app_is_open():
    at = _app().run()
    assert not at.exception
    assert not at.text_input
    assert at.sidebar.radio


def test_secret_closes_the_app_behind_a_password():
    at = _app(PASSWORD).run()
    assert not at.exception
    assert len(at.text_input) == 1
    assert at.text_input[0].label == "Пароль"
    assert "Доступ к дашборду ограничен" in _texts(at)
    assert not at.sidebar.selectbox


def test_wrong_password_is_rejected():
    at = _app(PASSWORD).run()
    at.text_input[0].set_value("не тот пароль")
    at.button[0].click().run()

    assert not at.exception
    assert any("Неверный пароль" in str(e.value) for e in at.error)
    assert not at.sidebar.selectbox


def test_correct_password_opens_the_app():
    at = _app(PASSWORD).run()
    at.text_input[0].set_value(PASSWORD)
    at.button[0].click().run()

    assert not at.exception
    assert at.sidebar.radio
    assert not at.error


def test_password_is_not_kept_in_session_state():
    at = _app(PASSWORD).run()
    at.text_input[0].set_value(PASSWORD)
    at.button[0].click().run()

    assert at.session_state["_ppd_authenticated"] is True
    assert "_ppd_password_input" not in at.session_state


def test_blank_secret_does_not_lock_the_app():
    at = _app("   ").run()
    assert not at.exception
    assert not at.text_input


def test_database_is_rebuilt_after_code_reload():
    """В кэше живёт путь, а не объект БД.

    st.cache_resource переживает обновление кода на Streamlit Cloud. Если в
    нём лежит экземпляр AuditDatabase, после деплоя у него не окажется новых
    методов и приложение упадёт с AttributeError до ручного перезапуска.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, "app")
    import lib

    cached = lib._bootstrap()
    assert isinstance(cached[0], Path)  # путь, а не AuditDatabase

    first, second = lib.database(), lib.database()
    assert first is not second  # объект собирается заново на каждый вызов
    assert first.path == second.path
