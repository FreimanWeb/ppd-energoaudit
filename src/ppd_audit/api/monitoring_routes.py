"""Monitoring endpoints never seed or mutate the telemetry database."""

from __future__ import annotations

import os
import sqlite3
from datetime import date
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from ..db import AuditDatabase, default_database_path
from ..services.monitoring import monitoring_history, monitoring_objects, object_timeline


router = APIRouter()


def _database():
    path = Path(os.getenv("PPD_DATABASE_PATH", default_database_path()))
    if not path.is_file():
        raise HTTPException(503, detail="База телеметрии ещё не подготовлена.")
    return AuditDatabase(path)


@router.get("/monitoring/objects")
def objects(
    history_days: int = Query(30, ge=1, le=180),
    history_end: date | None = None,
    include_history: bool = True,
) -> dict:
    try:
        return monitoring_objects(
            _database(),
            history_days=history_days,
            history_end=history_end,
            include_history=include_history,
        )
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except sqlite3.DatabaseError as exc:
        raise HTTPException(503, detail="База телеметрии недоступна или не подготовлена.") from exc


@router.get("/monitoring/history")
def history(
    history_end: date,
    history_days: int = Query(30, ge=1, le=180),
) -> dict:
    try:
        return monitoring_history(_database(), history_days=history_days, history_end=history_end)
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except sqlite3.DatabaseError as exc:
        raise HTTPException(503, detail="База телеметрии недоступна или не подготовлена.") from exc


@router.get("/objects/{object_id}/timeline")
def timeline(
    object_id: str,
    aggregate_id: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    try:
        first, last = (
            date.fromisoformat(start) if start else None,
            date.fromisoformat(end) if end else None,
        )
        if first and first.isoformat() != start or last and last.isoformat() != end:
            raise ValueError("Даты должны иметь формат YYYY-MM-DD.")
        return object_timeline(_database(), object_id, aggregate_id, first, last)
    except KeyError as exc:
        raise HTTPException(404, detail="Объект или агрегат не найден.") from exc
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except sqlite3.DatabaseError as exc:
        raise HTTPException(503, detail="База телеметрии недоступна или не подготовлена.") from exc
