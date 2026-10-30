from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest


_TEST_DB = Path(tempfile.gettempdir()) / f"ppd-audit-tests-{os.getpid()}.sqlite"
_TEST_DB.unlink(missing_ok=True)

os.environ.setdefault("PPD_DATABASE_PATH", str(_TEST_DB))
os.environ.setdefault("PPD_SKIP_EXAMPLE_TELEMETRY", "1")
os.environ.setdefault("PPD_SKIP_SCADA_TELEMETRY", "1")


@pytest.fixture
def data_source(tmp_path):
    """Общие измерения и CSV-источники без зависимости от какого-либо UI."""
    from ppd_audit.db import AuditDatabase

    db = AuditDatabase(tmp_path / "data.sqlite")
    db.migrate()
    db.upsert_plant("test", "КНС тест", "НГДУ", "пресная", "кнс")
    db.upsert_aggregate("test", "НА-1", "работа")
    start = datetime(2026, 1, 1)
    db.add_measurement("test", "НА-1", start - timedelta(hours=1), "p_in", 1, "МПа")
    for index in range(3):
        stamp = start + timedelta(days=index)
        db.add_measurement("test", None, stamp, "q_day", 100 + index, "м³/сут")
    db.add_measurement("test", "НА-1", start + timedelta(days=1), "q_day", 20, "м³/сут")
    db.add_measurement("test", "НА-1", start + timedelta(days=2), "p_in", 2, "МПа")
    crm = tmp_path / "crm"
    run = crm / "test" / "daily"
    run.mkdir(parents=True)
    (run / "model_metadata.json").write_text(json.dumps({"object_id": "001"}))
    header = "datetime,PRED::PUMP_001_QVD_I3,Q_OUT_SUM\n"
    rows = [f"2026-01-01 {hour:02}:00:00,2,2" for hour in range(24)]
    (run / "forecast_by_equipment_and_total.csv").write_text(header + "\n".join(rows))
    tags = tmp_path / "tags.yaml"
    tags.write_text("objects:\n  '001':\n    aggregates: {PUMP_001: НА-1}\n")
    return db, crm, tags
