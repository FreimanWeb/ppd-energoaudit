"""По-вкладочные AppTest-тесты дашборда SQLite-телеметрии."""

from datetime import date

import pytest


pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest


APP = "app/main.py"

# Вкладка → маркер контента (ищется в subheader/markdown/caption).
TAB_MARKERS = {
    "Обзор": ["Суточный KPI", "Структура потерь", "Топ-мероприятия", "Паспорт и режим"],
    "Телеметрия": ["Телеметрия за сутки"],
    "Схема ППД": ["Схема работы ППД", "Поток мощности"],
    "Карта потерь": ["Цифровая карта потерь мощности", "Структура (доли от подведённой мощности"],
    "Рабочая точка": ["Рабочая точка: насос × трубопровод"],
    "Модель vs Отчёт": ["Трёхсторонняя сверка"],
    "Мероприятия": ["Реестр мероприятий с ТЭО", "Оптимизация уставки"],
    "Новый объект": ["Подключение нового объекта", "Требуемая телеметрия"],
    "Формулы": ["Как получено каждое число"],
    "Качество данных": ["Качество и происхождение данных", "Полнота режима"],
}


def _run_for(label_part: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=240).run()
    option = next(o for o in at.selectbox[0].options if label_part in o)
    at.selectbox[0].set_value(option).run()
    if label_part == "КНС-54":
        at.selectbox[1].set_value("НА-2").run()
        return at.date_input[0].set_value(date(2025, 6, 5)).run()
    return at


def _all_text(at: AppTest) -> str:
    chunks = [m.value for m in at.markdown]
    chunks += [s.value for s in at.subheader]
    chunks += [c.value for c in at.caption]
    return " ".join(str(c) for c in chunks)


@pytest.fixture(scope="module")
def at_kns54():
    return _run_for("КНС-54")


@pytest.mark.parametrize("tab_name", list(TAB_MARKERS))
def test_tab_renders_kns54(at_kns54, tab_name):
    """КНС-54: каждая вкладка рендерит контент из SQLite-телеметрии."""
    assert not at_kns54.exception, at_kns54.exception
    text = _all_text(at_kns54)
    for marker in TAB_MARKERS[tab_name]:
        assert marker in text, f"КНС-54, вкладка «{tab_name}»: нет «{marker}»"


@pytest.mark.parametrize("label_part", ["ДНС-7с", "КНС-25"])
def test_object_without_telemetry_shows_message(label_part):
    at = _run_for(label_part)
    assert not at.exception
    assert any("Нет телеметрии" in warning.value for warning in at.warning)


def test_overview_answers_manager_questions(at_kns54):
    """Главная вкладка отвечает руководителю: УРЭ ф/р/опт, потери, топ-мероприятия."""
    labels = {m.label for m in at_kns54.metric}
    assert {
        "УРЭ факт, кВт·ч/м³",
        "УРЭ расчётный, кВт·ч/м³",
        "УРЭ оптимальный, кВт·ч/м³",
        "КПД факт",
        "ΔW по КПД, кВт·ч/год",
        "ΔW по КПД, тыс. ₽/год",
    } <= labels
    text = _all_text(at_kns54)
    assert "Структура потерь" in text and "Топ-мероприятия" in text


def test_dashboard_marks_calculated_blocks(at_kns54):
    text = _all_text(at_kns54)
    assert "Расчёт по Методике" in text
    assert "Паспортная или модельная кривая" in text
