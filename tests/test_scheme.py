import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from tabs import scheme


def test_other_aggregate_pressure_requires_the_exact_snapshot_timestamp():
    timestamp = datetime(2026, 7, 24, 10, 0)
    nearby_snapshot = SimpleNamespace(
        timestamp=timestamp + timedelta(seconds=1), p_in_mpa=1.2, p_out_mpa=10.4
    )
    exact_snapshot = SimpleNamespace(timestamp=timestamp, p_in_mpa=1.3, p_out_mpa=10.5)

    assert scheme._aggregate_pressure_text([nearby_snapshot], timestamp) == "p_вх/p_вых: нет данных"
    assert scheme._aggregate_pressure_text([nearby_snapshot, exact_snapshot], timestamp) == (
        "p_вх=1,30 МПа · p_вых=10,50 МПа"
    )


def test_topology_shows_pressures_on_the_corresponding_pump_arrows():
    figure = scheme._topology_figure(
        {
            "nodes": [
                {"id": "src", "type": "source", "x": 0, "y": 0, "label": "Приём"},
                {"id": "na2", "type": "pump", "agg": "НА-2", "x": 2, "y": 0, "label": "НА-2"},
                {"id": "man", "type": "manifold", "x": 4, "y": 0, "label": "Выкид"},
            ],
            "edges": [{"from": "src", "to": "na2"}, {"from": "na2", "to": "man"}],
        },
        selected_audit=None,
        sel_agg="НА-1",
        rm=SimpleNamespace(p_in=None, q_day=None, p_out=None, p_bg=None),
        pressure_labels={"НА-2": ("p_вх=1,30 МПа", "p_вых=10,50 МПа")},
    )

    labels = {annotation.text for annotation in figure.layout.annotations}
    assert {"p_вх=1,30 МПа", "p_вых=10,50 МПа"} <= labels
