"""E2E данные должны проходить настоящий расчёт и обнаружение CRM."""

import subprocess
import sys
from datetime import datetime

from ppd_audit.config import project_root
from ppd_audit.db import AuditDatabase
from ppd_audit.services.crm_view import crm_daily_forecast, crm_wells_report, well_downtime
from ppd_audit.services.telemetry_audit import run_snapshot_audit, telemetry_snapshots


def test_seed_real_data_and_unfit_day(tmp_path):
    script = project_root() / "scripts" / "seed_e2e.py"
    subprocess.run([sys.executable, str(script), str(tmp_path)], check=True)
    db = AuditDatabase(tmp_path / "audit.sqlite")
    start, end = datetime(2026, 9, 29), datetime(2026, 9, 30)
    snapshots = telemetry_snapshots(db, "kns54an", "НА-1", start, end)
    assert len(snapshots) >= 2
    result = run_snapshot_audit(db, "kns54an", "НА-1", start, end, snapshots[-1].timestamp)
    assert result.quality.status != "unfit"
    assert result.audit.regime.q == 120
    assert result.audit.decomposition is not None
    assert result.audit.decomposition.p_bg_useful > 0
    start, end = datetime(2026, 9, 30), datetime(2026, 10, 1)
    snap = telemetry_snapshots(db, "kns54an", "НА-1", start, end)[0]
    assert (
        run_snapshot_audit(db, "kns54an", "НА-1", start, end, snap.timestamp).quality.status
        == "unfit"
    )
    assert (
        telemetry_snapshots(db, "kns54an", "НА-1", datetime(2026, 10, 1), datetime(2026, 10, 2))
        == []
    )
    forecast = crm_daily_forecast(tmp_path / "crm", tmp_path / "tags.yaml", "kns54an", "baseline")
    assert forecast["by_unit"]["НА-1"][0][1] == 2880
    assert crm_wells_report(tmp_path / "crm", "kns54an", "wells")["wells"] == ["2015", "2017"]
    assert well_downtime(tmp_path / "downtime", "kns54an")[0]["well"] == "2017"


def test_seed_does_not_replace_existing_database(tmp_path):
    path = tmp_path / "audit.sqlite"
    path.write_bytes(b"do not replace")
    script = project_root() / "scripts" / "seed_e2e.py"
    result = subprocess.run([sys.executable, str(script), str(tmp_path)], capture_output=True)
    assert result.returncode != 0
    assert path.read_bytes() == b"do not replace"
