"""Characterization Streamlit forecast на реальной локальной телеметрии."""

import json
from datetime import datetime, timedelta

import pytest
from streamlit.testing.v1 import AppTest

from ppd_audit.db import AuditDatabase


@pytest.fixture
def forecast_database(tmp_path):
    database = AuditDatabase(tmp_path / "forecast.sqlite")
    database.migrate()
    database.upsert_plant("test", "КНС тест", "НГДУ", "пресная", "кнс")
    database.upsert_aggregate("test", "НА-1", "работа")
    for index, value in enumerate([10, 20, 30]):
        database.add_measurement(
            "test",
            "НА-1",
            datetime(2026, 1, 1) + timedelta(days=index),
            "q_day",
            value,
            "м³/сут",
        )
    return database


def _app(database, *, period_days=1, horizon=None, short_history=False, trace_service=False):
    script = f"""
import sys
sys.path.insert(0, 'app')
from datetime import date
from types import SimpleNamespace
import streamlit as st
import lib
from tabs import forecast
from ppd_audit.db import AuditDatabase
original_database = lib.database
original_chart = st.altair_chart
lib.database = lambda: AuditDatabase({str(database.path)!r})
def capture_chart(chart, **kwargs):
    st.session_state['forecast_plot'] = chart.to_dict()
st.altair_chart = capture_chart
st.session_state['forecast_granularity'] = {period_days!r}
"""
    if horizon is not None:
        script += f"st.session_state['forecast_horizon'] = {horizon!r}\n"
    if short_history:
        script += "st.session_state['forecast_period'] = (date(2026, 1, 1), date(2026, 1, 2))\n"
    if trace_service:
        script += """
assert hasattr(lib, 'forecast_series'), 'нужна общая forecast wrapper'
original_forecast = lib.forecast_series
st.session_state['forecast_calls'] = []
def trace_forecast(*args, **kwargs):
    st.session_state['forecast_calls'].append((args, kwargs))
    return original_forecast(*args, **kwargs)
lib.forecast_series = trace_forecast
"""
    script += """
try:
    forecast.render(SimpleNamespace(object_id='test', agg_id='НА-1'))
finally:
    lib.database, st.altair_chart = original_database, original_chart
"""
    if trace_service:
        script += "    lib.forecast_series = original_forecast\n"
    return AppTest.from_string(script).run()


def test_daily_forecast_widget_accepts_its_default_horizon(forecast_database):
    app = _app(forecast_database)
    assert not app.exception
    assert app.number_input(key="forecast_horizon").value == 1095


def test_characterization_forecast_metrics_and_chart(forecast_database):
    app = _app(forecast_database, horizon=2)
    assert not app.exception
    assert [metric.value for metric in app.metric] == ["10,0", "20", "50", "90"]
    datasets = app.session_state["forecast_plot"]["datasets"]
    combined = next(values for values in datasets.values() if len(values) == 5)
    assert [point["Период"] for point in combined] == [-2, -1, 0, 1, 2]
    assert [point["Значение"] for point in combined] == [10, 20, 30, 40, 50]
    assert json.loads(json.dumps(app.session_state["forecast_plot"]))["height"] == 320


def test_characterization_insufficient_daily_history(forecast_database):
    app = _app(forecast_database, short_history=True)
    assert not app.exception
    assert app.info[0].value.startswith("В выбранном периоде меньше 3 суток")
    assert not app.metric


def test_characterization_insufficient_complete_periods(forecast_database):
    app = _app(forecast_database, period_days=30)
    assert not app.exception
    assert app.warning[0].value == "Полных периодов «месяц»: 0 — нужно не менее 3."
    assert not app.metric


def test_streamlit_forecast_uses_shared_service_once(forecast_database):
    app = _app(forecast_database, horizon=2, trace_service=True)
    assert not app.exception
    calls = app.session_state["forecast_calls"]
    assert len(calls) == 1
    assert calls[0][0] == ("test", "НА-1", datetime(2026, 1, 1).date(), datetime(2026, 1, 3).date())
    assert calls[0][1] == {"period_days": 1, "horizon": 2}
