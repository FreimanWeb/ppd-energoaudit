from datetime import datetime

import openpyxl

from ppd_audit.ingest.excel_telemetry import build_excel_telemetry


def test_build_excel_telemetry_extracts_rows(tmp_path):
    path = tmp_path / "sample.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Telemetry"
    ws.append(["Дата", "Тех. место", "Мощность, кВт", "Плотность, кг/м3", "Кач."])
    ws.append([datetime(2026, 1, 2, 3, 4), "НА-1", 12.5, 1000, "OK"])
    wb.save(path)

    payload = build_excel_telemetry(path, source_root=tmp_path)

    assert payload["source"]["relative_path"] == "sample.xlsx"
    assert payload["sheets"][0]["name"] == "Telemetry"
    assert payload["sheets"][0]["tables"][0]["header_row"] == 1
    assert payload["telemetry"] == [
        {
            "sheet": "Telemetry",
            "row": 2,
            "timestamp": "2026-01-02T03:04:00",
            "tag": "НА-1",
            "metric": "power_kw",
            "label": "Мощность, кВт",
            "unit": "кВт",
            "value": 12.5,
            "quality": "OK",
        },
        {
            "sheet": "Telemetry",
            "row": 2,
            "timestamp": "2026-01-02T03:04:00",
            "tag": "НА-1",
            "metric": "density_kg_m3",
            "label": "Плотность, кг/м3",
            "unit": "кг/м³",
            "value": 1000.0,
            "quality": "OK",
        },
    ]
