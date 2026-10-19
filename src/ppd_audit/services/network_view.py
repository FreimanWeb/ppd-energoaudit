"""Разводящая сеть станции: данные для обоих интерфейсов.

Собирает геометрию водоводов из реестра трубопроводов, режим скважин из
карточек АРМИТС и давление на блок-гребёнке из телеметрии станции, считает
сеть (``core.network``) и отдаёт результат в виде словаря, общего для API и
Streamlit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cache
from pathlib import Path
from statistics import median

import yaml

from .. import units
from ..core.network import (
    MEASUREMENT_FLAGS,
    Fluid,
    NetworkResult,
    WellMeasurement,
    analyze_network,
    water_viscosity_cst,
)
from ..db import AuditDatabase
from ..ingest.armits_wells import WellCard, read_cards
from ..ingest.pipelines import Pipeline, read_pipelines


DEFAULT_TEMPERATURE_C = 10.0
DEFAULT_DENSITY = 1000.0
# Окно телеметрии для давления на БГ: последние сутки с данными и 30 суток до них.
MANIFOLD_WINDOW = timedelta(days=30)


@dataclass(frozen=True)
class PlantNetwork:
    """Источники разводящей сети одной станции."""

    plant_id: str
    pipelines_file: Path
    pipelines_sheet: str
    wells_archive: Path
    wells_folder: str
    station_nodes: tuple[str, ...]


def plant_network(network_dir: Path, config_path: Path, plant_id: str) -> PlantNetwork | None:
    """Источники сети станции; None, если для неё нет описания или файлов."""
    if not config_path.is_file():
        return None
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    plant = (config.get("plants") or {}).get(plant_id)
    if not plant:
        return None
    network = PlantNetwork(
        plant_id=plant_id,
        pipelines_file=network_dir / config["pipelines_file"],
        pipelines_sheet=str(plant["pipelines_sheet"]),
        wells_archive=network_dir / config["wells_archive"],
        wells_folder=str(plant["wells_folder"]),
        station_nodes=tuple(plant.get("station_nodes") or ()),
    )
    if not network.pipelines_file.is_file() or not network.wells_archive.is_file():
        return None
    return network


def _stamp(path: Path) -> int:
    return path.stat().st_mtime_ns


@cache
def _pipelines(path: Path, sheet: str, stamp: int) -> tuple[Pipeline, ...]:
    return tuple(read_pipelines(path, sheet))


@cache
def _cards(path: Path, folder: str, stamp: int) -> tuple[WellCard, ...]:
    return tuple(read_cards(path, folder))


def pipelines(network: PlantNetwork) -> list[Pipeline]:
    path = network.pipelines_file
    return list(_pipelines(path, network.pipelines_sheet, _stamp(path)))


def cards(network: PlantNetwork) -> list[WellCard]:
    path = network.wells_archive
    return list(_cards(path, network.wells_folder, _stamp(path)))


def time_weighted_median(
    events: list[tuple[datetime, float]], start: datetime, end: datetime
) -> float | None:
    """Медиана ступенчатого сигнала по времени на интервале [start, end).

    Каждое значение действует до следующего события. Медиана, а не среднее:
    остановы станции дают короткие провалы давления до нуля, и среднее
    занижало бы рабочее давление.
    """
    spans: list[tuple[float, float]] = []
    for index, (moment, value) in enumerate(events):
        begin = max(moment, start)
        finish = min(events[index + 1][0], end) if index + 1 < len(events) else end
        if finish > begin:
            spans.append((value, (finish - begin).total_seconds()))
    total = sum(duration for _, duration in spans)
    if total <= 0:
        return None
    passed = 0.0
    for value, duration in sorted(spans):
        passed += duration
        if passed >= total / 2:
            return value
    return spans[-1][0]


def manifold_pressure(
    database: AuditDatabase, plant_id: str
) -> tuple[float, datetime, datetime] | None:
    """Давление на БГ по телеметрии: медиана по времени за последние 30 суток."""
    last = database.last_station_timestamp(plant_id, "p_bg")
    if last is None:
        return None
    end = last.replace(hour=0, minute=0, second=0, microsecond=0)
    start = end - MANIFOLD_WINDOW
    events = database.station_metric_events(plant_id, "p_bg", start, end)
    value = time_weighted_median(events, start, end)
    if value is None or value <= 0:
        return None
    return value, start, end


def card_manifold_pressure(well_cards: list[WellCard]) -> float | None:
    """Давление на БГ из карточек: самое частое значение последнего месяца, МПа."""
    values = [
        card.last_month.p_bg_atm
        for card in well_cards
        if card.last_month and card.last_month.p_bg_atm
    ]
    if not values:
        return None
    return units.kgfcm2_to_mpa(max(set(values), key=values.count))


def station_nominal_efficiency(database: AuditDatabase, plant_id: str) -> float | None:
    """Номинальный КПД насосной установки станции: медиана по агрегатам."""
    values = []
    for aggregate in database.aggregates(plant_id):
        try:
            passport = database.active_passport(plant_id, aggregate["code"], datetime.now())
        except KeyError:
            continue
        pump, motor = passport["pump_eta_nom"], passport["motor_eta_nom"]
        if pump and motor:
            values.append(pump * motor * (passport["transmission_eff"] or 1.0))
    return median(values) if values else None


def measurements(well_cards: list[WellCard]) -> list[WellMeasurement]:
    """Режим скважин: среднекалендарный расход последнего полного месяца."""
    out = []
    for card in well_cards:
        last = card.last_month
        rate = last.mean_rate_m3h if last else None
        if not rate:
            continue
        before, after = card.p_before_choke_atm, card.p_after_choke_atm
        out.append(
            WellMeasurement(
                well=card.well,
                q_m3h=rate,
                annual_volume_m3=card.annual_volume_m3(),
                p_before_choke_mpa=units.kgfcm2_to_mpa(before) if before else None,
                p_after_choke_mpa=units.kgfcm2_to_mpa(after) if after else None,
            )
        )
    return out


def network_temperature_c(pipes: list[Pipeline]) -> float:
    """Температура агента по реестру трубопроводов, °C."""
    values = [pipe.temperature_c for pipe in pipes if pipe.temperature_c]
    return median(values) if values else DEFAULT_TEMPERATURE_C


def _sections(pipeline: Pipeline) -> str:
    sizes = dict.fromkeys(
        f"{section.outer_mm:g}×{section.wall_mm:g}" for section in pipeline.sections
    )
    return ", ".join(sizes)


def _well_rows(result: NetworkResult, eta: float) -> list[dict]:
    rows = []
    for well in sorted(result.wells, key=lambda item: item.q_m3h, reverse=True):
        energy = sum(
            dp / (units.HYDRAULIC_POWER_DIVISOR * eta) * well.annual_volume_m3
            for dp in (well.dp_friction_mpa, well.dp_other_mpa, well.dp_choke_mpa)
            if dp is not None and dp > 0
        )
        rows.append({
            "well": well.well,
            "q_m3h": well.q_m3h,
            "annual_volume_m3": well.annual_volume_m3,
            "path_length_m": well.path_length_m,
            "path_complete": well.path_complete,
            "has_geometry": well.has_geometry,
            "p_before_choke_mpa": well.p_before_choke_mpa,
            "p_after_choke_mpa": well.p_after_choke_mpa,
            "dp_network_mpa": well.dp_network_mpa,
            "dp_friction_mpa": well.dp_friction_mpa,
            "dp_other_mpa": well.dp_other_mpa,
            "dp_choke_mpa": well.dp_choke_mpa,
            "friction_kw": well.friction_kw,
            "other_kw": well.other_kw,
            "choke_kw": well.choke_kw,
            "loss_kw": well.friction_kw + well.other_kw + well.choke_kw,
            "annual_kwh": energy,
            "consistent": well.pressures_consistent,
            "flags": well.flags,
        })
    return rows


def _pipeline_rows(result: NetworkResult) -> list[dict]:
    return [
        {
            "name": load.pipeline.name,
            "start": load.pipeline.start,
            "end": load.pipeline.end,
            "length_m": load.pipeline.active_length_m,
            "sizes": _sections(load.pipeline),
            "inner_mm": min(section.inner_mm for section in load.pipeline.sections),
            "pipe_types": ", ".join(
                dict.fromkeys(section.pipe_type for section in load.pipeline.sections)
            ),
            "q_m3h": load.q_m3h,
            "velocity_ms": load.velocity_ms,
            "dp_friction_mpa": load.dp_friction_mpa,
        }
        for load in result.loads
    ]


def network_view(
    database: AuditDatabase,
    network_dir: Path,
    config_path: Path,
    plant_id: str,
    *,
    tariff: float,
    eta: float | None = None,
) -> dict:
    """Расчёт разводящей сети станции в виде, общем для API и Streamlit."""
    network = plant_network(network_dir, config_path, plant_id)
    if network is None:
        return {"error": "Для объекта нет геометрии водоводов и карточек скважин."}
    pipes = pipelines(network)
    well_cards = cards(network)

    telemetry = manifold_pressure(database, plant_id)
    if telemetry is not None:
        p_bg, start, end = telemetry
        p_bg_source = {
            "kind": "telemetry",
            "start": start.date().isoformat(),
            "end": end.date().isoformat(),
        }
    else:
        p_bg = card_manifold_pressure(well_cards)
        p_bg_source = {"kind": "wells", "start": None, "end": None}
    if p_bg is None:
        return {"error": "Нет давления на блок-гребёнке ни в телеметрии, ни в карточках."}

    eta_basis = "fact" if eta else "nominal"
    eta = eta or station_nominal_efficiency(database, plant_id)
    if not eta:
        return {"error": "Нет КПД насосной установки для оценки годовых потерь."}

    density = database.plant(plant_id)["default_density"] or DEFAULT_DENSITY
    temperature = network_temperature_c(pipes)
    fluid = Fluid(rho=density, nu_cst=water_viscosity_cst(temperature))
    result = analyze_network(pipes, measurements(well_cards), network.station_nodes, p_bg, fluid)
    month = max((card.last_month.month for card in well_cards if card.last_month), default=None)

    energy = {
        key: result.annual_energy_kwh(f"dp_{key}_mpa", eta)
        for key in ("friction", "other", "choke")
    }
    total_kwh = sum(energy.values())
    wells = result.wells
    return {
        "object_id": plant_id,
        "month": month.strftime("%Y-%m") if month else None,
        "p_bg_mpa": p_bg,
        "p_bg_source": p_bg_source,
        "fluid": {"rho": fluid.rho, "nu_cst": fluid.nu_cst, "temperature_c": temperature},
        "eta": eta,
        "eta_basis": eta_basis,
        "tariff": tariff,
        "totals": {
            "q_m3h": result.total_q_m3h,
            "friction_kw": result.friction_kw,
            "other_kw": result.other_kw,
            "choke_kw": result.choke_kw,
            "friction_kwh": energy["friction"],
            "other_kwh": energy["other"],
            "choke_kwh": energy["choke"],
            "total_kwh": total_kwh,
            "money_krub": total_kwh * tariff / 1000.0,
            "required_pressure_mpa": result.required_pressure_mpa,
            "excess_pressure_mpa": result.excess_pressure_mpa,
            "excess_kwh": result.excess_energy_kwh(eta),
        },
        "coverage": {
            "cards": len(well_cards),
            "wells": len(wells),
            "complete_paths": sum(well.path_complete for well in wells),
            "partial_paths": sum(well.has_geometry and not well.path_complete for well in wells),
            "no_geometry": sum(not well.has_geometry for well in wells),
            "inconsistent": sum(
                any(flag in MEASUREMENT_FLAGS for flag in well.flags) for well in wells
            ),
        },
        "wells": _well_rows(result, eta),
        "pipelines": _pipeline_rows(result),
    }
