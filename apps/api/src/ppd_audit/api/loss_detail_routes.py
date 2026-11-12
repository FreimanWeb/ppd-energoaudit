"""Scoped loss explanation and the same requirements before/after a usable audit."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException
from pydantic import Field

from ..services.armits_data import load_network
from ..services.loss_details import DOWNSTREAM, SUPPORTED_KEYS, build_loss_detail
from ..services.loss_requirements import data_requirements
from ..services.manual_data import apply_equipment_override, equipment_view, manual_measurement
from ..services.network_losses import build_network_analysis
from ..spec import AggregateSpec
from .analysis_contracts import AnalysisContext, NetworkLossScenario
from .analysis_routes import _context
from .dashboard import _require_ids, _tariff


router = APIRouter()


class LossDetailRequest(AnalysisContext):
    key: str = Field(min_length=1)
    scenario: NetworkLossScenario = Field(default_factory=NetworkLossScenario)


class RequirementsRequest(AnalysisContext):
    with_regime: bool = True


def _database():
    from .main import _database as database

    return database()


def _at(database, object_id, aggregate_id, request, audit):
    if request.source == "telemetry":
        return datetime.fromisoformat(request.timestamp)
    if request.measurement_id is not None:
        measurement = manual_measurement(database, object_id, aggregate_id, request.measurement_id)
        return datetime.fromisoformat(measurement["measured_at"])
    measured = audit.spec.regime.measured_at
    return (
        datetime.combine(measured, time.min)
        if measured is not None
        else datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None)
    )


def _equipment_for_audit(database, object_id, aggregate_id, at, request, audit):
    equipment = equipment_view(database, object_id, aggregate_id, at)
    if request.equipment_override is None:
        actual = {
            "pump": audit.spec.pump.model_dump(mode="json"),
            "motor": audit.spec.motor.model_dump(mode="json"),
            "transmission": audit.spec.transmission.model_dump(mode="json"),
            "vfd": audit.spec.vfd,
        }
        if actual != equipment["equipment"]:
            raise HTTPException(409, detail="Паспорт изменился во время расчёта. Обновите разбор.")
    return equipment


def _passport_requirements(database, object_id, aggregate_id, selected, override=None):
    equipment = equipment_view(database, object_id, aggregate_id, selected)
    aggregate = AggregateSpec(
        id=aggregate_id,
        technical_place_code=database.aggregate(object_id, aggregate_id)["technical_place_code"],
        **equipment["equipment"],
    )
    if override is not None:
        aggregate = apply_equipment_override(aggregate, override)
    return {
        "requirements": data_requirements(
            aggregate,
            provenance=equipment["provenance"],
            scenario=override is not None,
            network=load_network(object_id),
        ),
        "basis": {"source": "passport", "at": selected.isoformat()},
        "notes": [
            "Проверен паспорт на выбранную дату. Без пригодного режима "
            "наличие его измерений не подтверждается."
        ],
    }


@router.post("/objects/{object_id}/aggregates/{aggregate_id}/loss-detail")
def loss_detail(object_id: str, aggregate_id: str, request: LossDetailRequest):
    database = _database()
    if request.key not in SUPPORTED_KEYS:
        raise HTTPException(400, detail="Неизвестная составляющая потерь")
    _, audit, _, quality, sources = _context(database, object_id, aggregate_id, request)
    at = _at(database, object_id, aggregate_id, request, audit)
    equipment = _equipment_for_audit(database, object_id, aggregate_id, at, request, audit)
    network = load_network(object_id) if request.key in DOWNSTREAM else None
    network_result = (
        build_network_analysis(audit, network, options=request.scenario.model_dump())
        if network is not None
        else None
    )
    tariff = _tariff(database, at.date() if request.source == "telemetry" else None)["rub_per_kwh"]
    result = build_loss_detail(
        audit,
        request.key,
        tariff=tariff,
        provenance=equipment["provenance"],
        sources=sources,
        scenario=request.equipment_override is not None,
        network=network,
        network_analysis=network_result,
    )
    result["notes"].extend(issue.message for issue in quality.issues)
    result["analysis_context"] = request.model_dump(mode="json", exclude={"key", "scenario"})
    return result


@router.get("/objects/{object_id}/aggregates/{aggregate_id}/data-requirements")
def requirements_without_regime(object_id: str, aggregate_id: str, at: str | None = None):
    database = _database()
    _require_ids(database, object_id, aggregate_id)
    try:
        selected = (
            datetime.fromisoformat(at)
            if at
            else datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None)
        )
        if selected.tzinfo is not None:
            raise ValueError("Используется локальное время без UTC offset")
        return _passport_requirements(database, object_id, aggregate_id, selected)
    except KeyError as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


@router.post("/objects/{object_id}/aggregates/{aggregate_id}/data-requirements")
def requirements_for_regime(object_id: str, aggregate_id: str, request: RequirementsRequest):
    database = _database()
    if not request.with_regime:
        _require_ids(database, object_id, aggregate_id)
        try:
            if request.source == "field_trip" and request.measurement_id is not None:
                row = manual_measurement(database, object_id, aggregate_id, request.measurement_id)
                selected = datetime.fromisoformat(row["measured_at"])
            else:
                stamp = request.timestamp or request.day
                selected = (
                    datetime.fromisoformat(stamp)
                    if stamp
                    else datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None)
                )
            if selected.tzinfo is not None:
                raise ValueError("Используется локальное время без UTC offset")
            return _passport_requirements(
                database, object_id, aggregate_id, selected, request.equipment_override
            )
        except KeyError as exc:
            raise HTTPException(404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, detail=str(exc)) from exc
    _, audit, _, quality, _ = _context(database, object_id, aggregate_id, request)
    at = _at(database, object_id, aggregate_id, request, audit)
    equipment = _equipment_for_audit(database, object_id, aggregate_id, at, request, audit)
    return {
        "requirements": data_requirements(
            audit.spec,
            audit=audit,
            provenance=equipment["provenance"],
            scenario=request.equipment_override is not None,
            network=load_network(object_id),
        ),
        "basis": {"source": request.source, "at": at.isoformat()},
        "notes": [issue.message for issue in quality.issues],
    }
