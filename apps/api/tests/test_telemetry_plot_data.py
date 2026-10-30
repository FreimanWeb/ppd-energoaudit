"""Общая минутная редукция pressure series сохраняет raw events и границы."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ppd_audit.db import AuditDatabase


@pytest.fixture
def minute_frame():
    start = datetime(2026, 1, 1)
    values = [10 + second % 2 for second in range(60)]
    values[10], values[20] = 1, 30
    return pd.DataFrame({
        "Время": [start + timedelta(seconds=second) for second in range(60)],
        "Показатель": "p_вх",
        "Значение": values,
    })


def test_characterization_minute_pressure_extrema_and_boundaries(minute_frame):
    from ppd_audit.services.telemetry_series import reduce_pressure_points

    second_metric = minute_frame.iloc[[3, 40]].assign(Показатель="p_вых")
    frame = pd.concat([minute_frame, second_metric], ignore_index=True)
    reduced = reduce_pressure_points(frame)
    first_metric = reduced[reduced["Показатель"] == "p_вх"]
    assert list(first_metric["Время"].dt.second) == [0, 10, 20, 59]
    assert list(first_metric["Значение"]) == [10, 1, 30, 11]
    assert list(reduced[reduced["Показатель"] == "p_вых"]["Время"].dt.second) == [3, 40]
    assert "_bucket" not in reduced.columns


def test_pressure_reduction_preserves_shared_frame_shape(minute_frame):
    from ppd_audit.services.telemetry_series import reduce_pressure_points

    pd.testing.assert_frame_equal(
        reduce_pressure_points(minute_frame),
        minute_frame.iloc[[0, 10, 20, 59]].reset_index(drop=True),
    )


def test_telemetry_api_reduces_only_pressure_series_and_keeps_all_raw_events(
    tmp_path,
    monkeypatch,
    minute_frame,
):
    from ppd_audit.api import data_routes

    database = AuditDatabase(tmp_path / "pressure.sqlite")
    database.migrate()
    database.upsert_plant("test", "КНС тест", "НГДУ", "пресная", "кнс")
    database.upsert_aggregate("test", "НА-1", "работа")
    for _, row in minute_frame.iterrows():
        database.add_measurement("test", "НА-1", row["Время"], "p_in", row["Значение"], "МПа")
        database.add_measurement(
            "test", "НА-1", row["Время"], "power", 100 + row["Время"].second, "кВт"
        )
    monkeypatch.setattr(data_routes, "_database", lambda: database)
    app = FastAPI()
    app.include_router(data_routes.router)
    response = TestClient(app).get(
        "/objects/test/telemetry",
        params={
            "aggregate_id": "НА-1",
            "start": "2026-01-01",
            "end": "2026-01-01",
        },
    )
    assert response.status_code == 200
    body = response.json()
    pressure = next(series for series in body["series"] if series["metric"] == "p_вх")
    assert pressure["points"] == [
        {"timestamp": "2026-01-01T00:00:00", "value": 10},
        {"timestamp": "2026-01-01T00:00:10", "value": 1},
        {"timestamp": "2026-01-01T00:00:20", "value": 30},
        {"timestamp": "2026-01-01T00:00:59", "value": 11},
        {"timestamp": "2026-01-02T00:00:00", "value": 11},
    ]
    power = next(series for series in body["series"] if series["unit"] == "кВт")
    assert len(power["points"]) == 61
    assert len(body["records"]) == 120
    assert sum(row["metric"] == "p_in" for row in body["records"]) == 60
