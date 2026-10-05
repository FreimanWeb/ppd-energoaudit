"""Characterization помесячного CRM графика и общая service orchestration."""

from streamlit.testing.v1 import AppTest
from test_data_services import monthly_report as monthly_report_fixture


monthly_report = monthly_report_fixture


def _app(report, *, trace=False):
    source = f"""
import sys
sys.path.insert(0, 'app')
from types import SimpleNamespace
import streamlit as st
from tabs import crm_wells
from ppd_audit.services import crm_view
report = {dict(report, wells=["100", "200"])!r}
downtime = [
    {{'well': '100/2', 'reason': 'Ремонт', 'since': '2025-12-01T00:00:00'}},
    {{'well': '100/2', 'reason': 'Ремонт', 'since': '2026-02-01T00:00:00'}},
]
original_chart = st.altair_chart
st.altair_chart = lambda chart, **kwargs: st.session_state.update(monthly_plot=chart.to_dict())
st.session_state['crm-wells-series-test'] = '100'
"""
    if trace:
        source += """
original_view = crm_view.monthly_view
st.session_state['monthly_calls'] = 0
def trace_view(*args, **kwargs):
    st.session_state['monthly_calls'] += 1
    return original_view(*args, **kwargs)
crm_view.monthly_view = trace_view
"""
    source += """
try:
    crm_wells._totals_section(SimpleNamespace(object_id='test'), report, downtime)
finally:
    st.altair_chart = original_chart
"""
    if trace:
        source += "    crm_view.monthly_view = original_view\n"
    return AppTest.from_string(source).run()


def test_characterization_monthly_chart_and_metrics(monthly_report):
    app = _app(monthly_report)
    assert not app.exception
    assert [metric.value for metric in app.metric] == ["30", "40", "-25,0 %"]
    datasets = app.session_state["monthly_plot"]["datasets"]
    marks = next(points for points in datasets.values() if points and "Момент" in points[0])
    assert len(marks) == 1
    assert marks[0]["Момент"] == "2025-12-01T00:00:00"
    assert marks[0]["Скважина"] == "100/2"


def test_monthly_ui_calls_shared_view_once(monthly_report):
    app = _app(monthly_report, trace=True)
    assert not app.exception
    assert app.session_state["monthly_calls"] == 1
