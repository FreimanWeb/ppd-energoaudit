"""Изолированные реальные входные файлы для browser regression.

Запуск: .venv/bin/python scripts/seed_e2e.py /tmp/новый-каталог
Существующую БД никогда не перезаписывает.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from openpyxl import Workbook

from ppd_audit.db_seed import bootstrap_database


def seed(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "audit.sqlite"
    if path.exists():
        raise FileExistsError(f"E2E требует новую БД: {path}")
    db = bootstrap_database(path, Path(__file__).resolve().parents[1] / "config/plants")
    start = datetime(2026, 7, 1)
    for index in range(93):
        day = start + timedelta(days=index)
        db.add_measurement(
            "kns54an", None, day, "p_bg", 11, "МПа",
            source_kind="scada", source_file="e2e-scada.csv",
        )
        for aggregate in ("НА-1", "НА-2"):
            values = [
                ("p_in", 1, "МПа"),
                ("p_out", 12, "МПа"),
                ("q_day", 2880, "м³/сут"),
                ("runtime", 24, "ч"),
                ("energy", 14400 if index != 91 else 100, "кВт·ч"),
                ("density", 1000, "кг/м³"),
            ]
            for metric, value, unit in values:
                db.add_measurement(
                    "kns54an",
                    aggregate,
                    day,
                    metric,
                    value,
                    unit,
                    source_kind="scada",
                    source_file="e2e-scada.csv",
                )
            for halfhour in range(48):
                db.add_measurement(
                    "kns54an",
                    aggregate,
                    day + timedelta(minutes=30 * halfhour),
                    "power",
                    600 if index != 92 else 0,
                    "кВт",
                    source_kind="scada",
                    source_file="e2e-scada.csv",
                )
    crm = directory / "crm/kns54an"
    for scenario, flow in (("baseline", 120), ("event", 100)):
        run = crm / scenario
        run.mkdir(parents=True)
        (run / "model_metadata.json").write_text(
            json.dumps({"object_id": "001", "model": "E2E CRM"})
        )
        (run / "run.json").write_text(
            json.dumps({"title": scenario, "events": scenario == "event"})
        )
        header = "datetime,PRED::PUMP_001_QVD_I3,PRED::PUMP_002_QVD_I3,Q_OUT_SUM\n"
        rows = [f"{start + timedelta(hours=h)},{flow},{flow},{flow * 2}" for h in range(24 * 100)]
        (run / "forecast_by_equipment_and_total.csv").write_text(header + "\n".join(rows))
    wells = crm / "wells"
    wells.mkdir()
    header = (
        "КНС,Период,Нагн. скваж.,Закачка м3/мес базовый прогноз,Закачка м3/мес прогноз,"
        "Доля базовый прогноз,Доля прогноз,Руст базовый прогноз,Руст прогноз,"
        "Суммарная закачка прогноз,Закачка м3/мес факт,Руст факт\n"
    )
    rows = [
        f"54,{month}.2026,{well},1000,900,0.5,0.5,60,61,1800,1100,62"
        for month in ("07", "08", "09")
        for well in ("2015", "2017")
    ]
    (wells / "predicted_injector_report_like.csv").write_text(header + "\n".join(rows))
    (wells / "loaded_model_injector_interdependence_edges.csv").write_text(
        "source,target,combined_strength,combined_signed\n2015,2017,0.82,0.29\n2017,2015,0.82,0.29\n"
    )
    (wells / "loaded_model_injector_dependency_centrality.csv").write_text(
        "injector,strength_sum,degree_centrality,betweenness_centrality,top_neighbor,top_neighbor_strength\n2015,0.82,1,0,2017,0.82\n"
    )
    (directory / "tags.yaml").write_text(
        "objects:\n  '001':\n    aggregates: {PUMP_001: НА-1, PUMP_002: НА-2}\n"
    )
    downtime = directory / "downtime"
    downtime.mkdir()
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["КНС-54"])
    sheet.append(["Цех", "В_в", "Скваж", "T_раб", "Причина_простоя", "Дата_непр_пр", "Q_ф"])
    sheet.append(["8", "3", "2017", 0, "Ремонт", datetime(2026, 9, 1), 0])
    workbook.save(downtime / "kns54an.xlsx")


if __name__ == "__main__":
    seed(Path(sys.argv[1]))
