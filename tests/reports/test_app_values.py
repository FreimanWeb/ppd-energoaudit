"""UI-тесты дашборда (streamlit.testing.v1.AppTest): дашборд не только стартует,
но и ПОКАЗЫВАЕТ числа, совпадающие с моделью и отчётом.

Открываем приложение программно, выбираем каждый объект, читаем KPI-виджеты и сверяем
их с расчётом ядра; на экране «Модель vs Отчёт» проверяем наличие трёхсторонней таблицы.
"""

import pytest


pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest

from ppd_audit.core.audit import audit_aggregate
from ppd_audit.spec import load_object_spec


APP = "app/main.py"
REPORT_OBJECTS = ["КНС-25", "КНС-155", "КНС-ОПУ", "КНС-10", "КНС-154", "КНС-14"]
OID = {
    "КНС-25": "kns25",
    "КНС-155": "kns155bn",
    "КНС-ОПУ": "knsopu",
    "КНС-10": "kns10bn",
    "КНС-154": "kns154bn",
    "КНС-14": "kns14an",
}


def _num(s: str):
    """ru-RU строку метрики → float ('53 242,90'→53242.9)."""
    if s is None:
        return None
    s = s.replace("\xa0", " ").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _metric(at, label):
    for m in at.metric:
        if m.label == label:
            return m
    return None


def _select_object(at, label_part):
    option = next(o for o in at.selectbox[0].options if label_part in o)
    return at.selectbox[0].set_value(option).run()


def test_smoke_starts():
    at = AppTest.from_file(APP, default_timeout=240).run()
    assert not at.exception
    assert len(at.tabs) == 9


@pytest.mark.parametrize("label_part", REPORT_OBJECTS)
def test_displayed_kpi_matches_model(label_part):
    """УРЭ факт/расч и КПД факт на экране совпадают с расчётом модели (UI↔модель)."""
    at = AppTest.from_file(APP, default_timeout=240).run()
    at = _select_object(at, label_part)
    assert not at.exception, f"{label_part}: {at.exception}"

    oid = OID[label_part]
    agg_id = at.selectbox[1].value  # выбранный агрегат
    obj = load_object_spec(oid)
    res = audit_aggregate(obj.aggregate(agg_id), obj.branch)

    sec_ui = _num(_metric(at, "УРЭ факт, кВт·ч/м³").value)
    assert sec_ui == pytest.approx(res.sec_fact, rel=0.01), (
        f"{label_part}/{agg_id}: УРЭ факт UI {sec_ui} ≠ модель {res.sec_fact}"
    )
    seccalc_ui = _num(_metric(at, "УРЭ расчётный, кВт·ч/м³").value)
    assert seccalc_ui == pytest.approx(res.sec_calc, rel=0.01)
    eta_ui = _num(_metric(at, "КПД факт").value)
    assert eta_ui == pytest.approx(res.regime.eta_unit, rel=0.01)


def test_compare_screen_shows_three_sources():
    """Экран «Модель vs Отчёт» показывает трёхстороннюю таблицу (модель|xlsx|отчёт)."""
    at = AppTest.from_file(APP, default_timeout=240).run()
    at = _select_object(at, "КНС-25")
    assert not at.exception
    # на экране сверки рендерятся датафреймы с колонками трёх источников
    cols = set()
    for df in at.dataframe:
        try:
            cols |= set(df.value.columns)
        except Exception:
            pass
    assert {"Модель", "расчет.xlsx", "Отчёт .doc"} <= cols, f"нет трёх источников: {cols}"


def test_report_quote_rendered():
    """В карточке/сверке КНС-25 присутствует цитата из отчёта (проза)."""
    at = AppTest.from_file(APP, default_timeout=240).run()
    at = _select_object(at, "КНС-25")
    md = " ".join(m.value for m in at.markdown)
    assert "УРЭ" in md and ("снижен" in md or "больше расч" in md.lower() or "превыша" in md)
