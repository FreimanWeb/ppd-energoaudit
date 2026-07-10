"""По-вкладочные AppTest-тесты дашборда (Фаза 3 ревизии, 02.07.2026).

Каждая из 8 вкладок рендерит свой ключевой контент без исключений на двух
контрастных объектах: ДНС-7с (пилот с телеметрией, ветка перекачки)
и КНС-25 (без телеметрии, инженерный xlsx, есть as-built схема).
"""

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = "app/main.py"

# Вкладка → маркер контента (ищется в subheader/markdown/caption).
TAB_MARKERS = {
    "Обзор": ["Ключевые показатели", "Структура потерь", "Топ-мероприятия", "Паспорт и режим"],
    "Схема ППД": ["Схема работы ППД", "Поток мощности"],
    "Карта потерь": ["Цифровая карта потерь мощности", "Структура (доли от подведённой мощности"],
    "Рабочая точка": ["Рабочая точка: насос × трубопровод"],
    "Мероприятия": ["Реестр мероприятий с ТЭО", "Оптимизация уставки"],
    "Новый объект": ["Подключение нового объекта", "Требуемая телеметрия"],
    "Формулы": ["Как получено каждое число"],
    "Качество данных": ["Качество и происхождение данных", "Полнота режима"],
}


def _run_for(label_part: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=240).run()
    option = next(o for o in at.selectbox[0].options if label_part in o)
    return at.selectbox[0].set_value(option).run()


def _all_text(at: AppTest) -> str:
    chunks = [m.value for m in at.markdown]
    chunks += [s.value for s in at.subheader]
    chunks += [c.value for c in at.caption]
    return " ".join(str(c) for c in chunks)


@pytest.fixture(scope="module")
def at_dns7s():
    return _run_for("ДНС-7с")


@pytest.fixture(scope="module")
def at_kns25():
    return _run_for("КНС-25")


@pytest.mark.parametrize("tab_name", list(TAB_MARKERS))
def test_tab_renders_dns7s(at_dns7s, tab_name):
    """ДНС-7с (телеметрия, перекачка): каждая вкладка рендерит свой контент."""
    assert not at_dns7s.exception, at_dns7s.exception
    text = _all_text(at_dns7s)
    for marker in TAB_MARKERS[tab_name]:
        assert marker in text, f"ДНС-7с, вкладка «{tab_name}»: нет «{marker}»"


@pytest.mark.parametrize("tab_name", list(TAB_MARKERS))
def test_tab_renders_kns25(at_kns25, tab_name):
    """КНС-25 (без телеметрии, инженерный xlsx): каждая вкладка рендерит свой контент."""
    assert not at_kns25.exception, at_kns25.exception
    text = _all_text(at_kns25)
    for marker in TAB_MARKERS[tab_name]:
        assert marker in text, f"КНС-25, вкладка «{tab_name}»: нет «{marker}»"


def test_empty_states_are_friendly(at_dns7s):
    """Пустые состояния — человеческим языком, без traceback."""
    assert not at_dns7s.exception
    text = _all_text(at_dns7s)
    assert "Traceback" not in text


def test_overview_answers_manager_questions(at_kns25):
    """Главная вкладка отвечает руководителю: УРЭ ф/р/опт, потери, топ-мероприятия."""
    labels = {m.label for m in at_kns25.metric}
    assert {"УРЭ факт, кВт·ч/м³", "УРЭ расчётный, кВт·ч/м³",
            "УРЭ оптимальный, кВт·ч/м³", "КПД факт",
            "ΔW по КПД, кВт·ч/год", "ΔW по КПД, тыс. ₽/год"} <= labels
    text = _all_text(at_kns25)
    assert "Структура потерь" in text and "Топ-мероприятия" in text
