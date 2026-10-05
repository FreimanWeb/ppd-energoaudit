"""Контракт Streamlit-render с общим представлением рабочей точки."""

import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from tabs import working_point as tab

from ppd_audit.services.audit import run_energy_audit
from ppd_audit.spec import PumpKind, load_object_spec


@pytest.fixture
def rendered(monkeypatch):
    figures = []
    monkeypatch.setattr(tab.st, "subheader", lambda *_: None)
    monkeypatch.setattr(tab.st, "caption", lambda *_: None)
    monkeypatch.setattr(tab.st, "columns", lambda _: [nullcontext(), nullcontext()])
    monkeypatch.setattr(tab.st, "plotly_chart", lambda fig, **_: figures.append(fig))
    monkeypatch.setattr(tab.ui, "provenance", lambda *_: None)
    return figures


def context():
    audit = run_energy_audit(load_object_spec("kns25"))
    return SimpleNamespace(agg=audit.spec, audit=audit)


@pytest.mark.parametrize("kind", ["model", "passport", "volumetric"])
def test_existing_plotly_traces_characterization(rendered, kind):
    ctx = context()
    p = ctx.agg.pump
    p.kind = PumpKind.centrifugal
    p.q_nom = 100
    p.h_nom = 1000
    p.eta_nom = 0.8
    p.curve_qh = []
    p.curve_qeta = []
    if kind == "passport":
        p.curve_qh = [[0, 1000], [100, 900]]
        p.curve_qeta = [[20, 0.5], [100, 0.8]]
    if kind == "volumetric":
        p.kind = PumpKind.positive_displacement
    tab.render(ctx)
    qh, qe = rendered
    if kind == "volumetric":
        assert "Характеристика трубопровода" not in [t.name for t in qh.data]
        assert "Номинал" not in [t.name for t in qe.data]
        assert not any(t.mode == "lines" for t in (*qh.data, *qe.data))
    else:
        pump = qh.data[0]
        eta = qe.data[0]
        assert pump.name.endswith("паспорт" if kind == "passport" else "модель")
        assert eta.name.endswith("паспорт" if kind == "passport" else "модель")
        if kind == "passport":
            assert list(pump.x) == [0, 100]
            assert list(pump.y) == [1000, 900]
            assert list(eta.y) == [0.5, 0.8]
        else:
            assert len(pump.x) == 41 and len(eta.x) == 31
            assert pump.y[0] == pytest.approx(1.22 * p.h_nom)
            assert eta.y[0] == pytest.approx(p.eta_nom * (1 - 0.9 * 0.8**2))
    assert list(qh.data[-1].x) == [ctx.agg.regime.flow()]
    assert list(qh.data[-1].y) == [ctx.audit.regime.h_fact]
    assert list(qe.data[-1].y) == [ctx.audit.regime.eta_unit]


def test_shared_view_controls_every_curve_and_point(rendered, monkeypatch):
    ctx = context()
    view = {
        "pump_kind": "центробежный",
        "point": {"q": 123, "h": 456, "eta": 0.321},
        "nominal": {"q": 222, "h": 333, "eta": 0.654},
        "due": {"h": 789, "eta": 0.8},
        "qh": [{"q": 1, "h": 2}, {"q": 3, "h": 4}],
        "qeta": [{"q": 5, "eta": 0.6}],
        "system": [{"q": 7, "h": 8}],
        "origin": {"qh": "passport", "qeta": "passport", "system": "model"},
        "notes": [],
    }
    monkeypatch.setattr(tab, "working_point", lambda _: view)
    tab.render(ctx)
    qh, qe = rendered
    assert list(qh.data[0].x) == [1, 3]
    assert list(qh.data[0].y) == [2, 4]
    assert list(qh.data[1].x) == [7]
    assert list(qh.data[1].y) == [8]
    nominal = next(t for t in qh.data if t.name == "Номинал")
    due = next(t for t in qh.data if t.name == "Должный напор (29)")
    assert list(nominal.x) == [222] and list(nominal.y) == [333]
    assert list(due.x) == [123] and list(due.y) == [789]
    assert list(qh.data[-1].x) == [123] and list(qh.data[-1].y) == [456]
    assert list(qe.data[0].x) == [5] and list(qe.data[0].y) == [0.6]
    assert list(qe.data[-1].x) == [123] and list(qe.data[-1].y) == [0.321]
    nominal_eta = next(t for t in qe.data if t.name == "Номинал")
    assert list(nominal_eta.x) == [222] and list(nominal_eta.y) == [0.654]
