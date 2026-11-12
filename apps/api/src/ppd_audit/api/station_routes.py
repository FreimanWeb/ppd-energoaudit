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
    if request.measurement_id is not None or request.equipment_override is not None:
        raise HTTPException(
            400,
            detail="Замер и сценарий одного агрегата нельзя применять к сводке всей станции.",
        )
    try:
        return station_summary(
            _database(),
            object_id,
            source=request.source,
            day=request.day,
            timestamp=request.timestamp,
        )
    except KeyError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, detail=str(exc)) from exc
