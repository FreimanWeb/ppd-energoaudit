"""Сводные показатели станции, независимо от выбранного агрегата."""

from fastapi import APIRouter, HTTPException

from ..services.station_summary import station_summary
from .analysis_contracts import AnalysisContext


router = APIRouter()


def _database():
    from .main import _database as database

    return database()


@router.post("/objects/{object_id}/station-summary")
def station_summary_view(object_id: str, request: AnalysisContext):
    try:
        return station_summary(_database(), object_id, **request.model_dump())
    except KeyError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, detail=str(exc)) from exc
