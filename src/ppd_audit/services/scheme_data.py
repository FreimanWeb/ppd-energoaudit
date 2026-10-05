"""Давления ветвей ППД в общий выбранный момент, без подмены соседним снимком."""

from datetime import datetime, timedelta

from ..db import AuditDatabase
from .telemetry_audit import telemetry_snapshots


def scheme_pressures(
    database: AuditDatabase,
    object_id: str,
    timestamp: datetime,
) -> dict[str, dict[str, float]]:
    """Пропустить ветви без физически пригодного снимка в точный момент."""
    start = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    pressures = {}
    for aggregate in database.aggregates(object_id):
        snapshot = next(
            (
                item
                for item in telemetry_snapshots(database, object_id, aggregate["code"], start, end)
                if item.timestamp == timestamp
            ),
            None,
        )
        if snapshot is not None:
            pressures[aggregate["code"]] = {
                "p_in_mpa": snapshot.p_in_mpa,
                "p_out_mpa": snapshot.p_out_mpa,
            }
    return pressures
