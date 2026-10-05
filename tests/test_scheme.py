import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET


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
    svg = scheme._topology_svg(
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

    root = ET.fromstring(svg)
    inlet = root.find(".//*[@data-from='src']")
    outlet = root.find(".//*[@data-from='na2']")
    assert "p_вх=1,30 МПа" in "".join(inlet.itertext())
    assert "p_вых=10,50 МПа" in "".join(outlet.itertext())


def test_equipment_scheme_keeps_branches_and_escapes_passport_text():
    topology = {
        "nodes": [
            {"id": "source", "type": "source", "x": 0, "y": 0, "label": "Приём"},
            {
                "id": "pump1",
                "type": "pump",
                "agg": "НА-1",
                "x": 1,
                "y": 1,
                "label": "НА-1",
                "sub": '<script>alert("x")</script>',
            },
            {"id": "pump2", "type": "pump", "agg": "НА-2", "x": 1, "y": -1, "label": "НА-2"},
            {"id": "well", "type": "wells", "x": 2, "y": 0, "label": "Скважины"},
            {"id": "reservoir", "type": "reservoir", "x": 3, "y": 0, "label": "Пласт"},
        ],
        "edges": [
            {"from": "source", "to": "pump1"},
            {"from": "source", "to": "pump2"},
            {"from": "well", "to": "reservoir"},
        ],
    }
    svg = scheme._topology_svg(
        topology,
        None,
        "НА-2",
        SimpleNamespace(p_in=None, q_day=None, p_out=None, p_bg=None),
        {},
    )
    root = ET.fromstring(svg)
    ns = {"s": "http://www.w3.org/2000/svg"}
    assert root.find(".//*[@data-node='pump2']").get("data-selected") == "true"
    assert root.find(".//*[@data-node='pump1']").get("data-selected") == "false"
    symbols = {node.get("href") for node in root.findall(".//s:use", ns)}
    assert {"#ppd-pump", "#ppd-wells", "#ppd-reservoir"} <= symbols
    assert len(root.findall(".//*[@data-from='source']")) == 2
    assert not root.findall(".//s:script", ns)
    assert "15–40 %" not in svg
