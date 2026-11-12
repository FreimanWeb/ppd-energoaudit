"""Dated equipment journal; legacy manual measurements are read-only."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from ..db import JournalConflict, RevisionConflict
from ..services.manual_data import (
    JournalWriteRequest,
    equipment_journal_view,
    equipment_view,
    manual_measurements_view,
    save_journal_entry,
)
from .dashboard import _require_ids


router = APIRouter()


def _database():
    from .main import _database as database

    return database()


def _local_datetime(value: str | None) -> datetime:
    if value is None:
        return datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(400, detail="момент должен быть локальным ISO datetime") from exc
    if parsed.tzinfo is not None:
        raise HTTPException(400, detail="момент задаётся в локальном времени без UTC offset")
    return parsed


@router.get("/objects/{object_id}/aggregates/{aggregate_id}/equipment")
def equipment_get(object_id: str, aggregate_id: str, at: str | None = None):
    database = _database()
    _require_ids(database, object_id, aggregate_id)
    return equipment_view(database, object_id, aggregate_id, _local_datetime(at))


@router.get("/objects/{object_id}/aggregates/{aggregate_id}/equipment-journal")
def journal_get(object_id: str, aggregate_id: str):
    database = _database()
    _require_ids(database, object_id, aggregate_id)
    return equipment_journal_view(database, object_id, aggregate_id)


@router.post("/objects/{object_id}/aggregates/{aggregate_id}/equipment-journal")
def journal_post(object_id: str, aggregate_id: str, request: JournalWriteRequest):
    database = _database()
    _require_ids(database, object_id, aggregate_id)
    try:
        return save_journal_entry(database, object_id, aggregate_id, request)
    except (RevisionConflict, JournalConflict) as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, detail=str(exc)) from exc


@router.get("/objects/{object_id}/aggregates/{aggregate_id}/manual-measurements")
def manual_measurements_get(object_id: str, aggregate_id: str):
    database = _database()
    _require_ids(database, object_id, aggregate_id)
    return manual_measurements_view(database, object_id, aggregate_id)
