"""Построение расчётного режима из временного окна SQLite-телеметрии."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from statistics import mean, median

from ..core.audit import AuditResult, audit_aggregate
from ..db import AuditDatabase
from ..spec import (
    AggregateSpec,
    Branch,
    MotorSpec,
    ObjectSpec,
    PumpSpec,
    RegimeMeasurement,
    TransmissionSpec,
)


_PRESSURE_POWER_MAX_GAP = timedelta(minutes=5)
_PRESSURE_STABILITY_WINDOW = timedelta(minutes=1)
_PRESSURE_STABILITY_MAX_RATE_MPA_PER_SECOND = 0.02
_MIN_PRESSURE_COVERAGE = 0.8


@dataclass(frozen=True)
class TelemetrySnapshot:
    """Один снимок режима с исходными временны́ми рассогласованиями."""

    timestamp: datetime
    p_in_mpa: float
    p_out_mpa: float
    p_bg_mpa: float | None
    p_bg_gap: timedelta | None
    power_kw: float | None
    power_gap: timedelta | None
    is_stable: bool


@dataclass(frozen=True)
class SnapshotAudit:
    """Расчёт по выбранному снимку и явно зафиксированные допущения."""

    audit: AuditResult
    snapshot: TelemetrySnapshot
    uses_daily_flow: bool
    uses_daily_power: bool
    annual_runtime_is_assumed: bool


def build_regime(
    database: AuditDatabase,
    plant_code: str,
    aggregate_code: str,
    start: datetime,
    end: datetime,
    *,
    require_daily_pressure_coverage: bool = True,
) -> RegimeMeasurement:
    """Свести measurements за окно к режиму одного агрегата."""
    rows = database.measurements_in_window(
        plant_code, aggregate_code, start, end, include_station=True
    )
    aggregate_values: dict[str, list[float]] = {}
    station_values: dict[str, list[float]] = {}
    for row in rows:
        if row["value"] == 0:
            continue
        target = station_values if row["is_station"] else aggregate_values
        target.setdefault(row["metric"], []).append(float(row["value"]))

    if any(metric in station_values for metric in ("q_day", "runtime", "energy")):
        raise ValueError("станционный расход, наработка или энергия не распределены по агрегатам")
    plant = database.plant(plant_code)
    p_in, p_out, p_bg = _operating_pressures(
        rows, require_daily_pressure_coverage=require_daily_pressure_coverage
    )
    q_day = _single(aggregate_values, "q_day", required=False)
    runtime = _single(aggregate_values, "runtime", required=False)
    energy = _single(aggregate_values, "energy", required=False)

    return RegimeMeasurement(
        rho=_median(aggregate_values, "density", required=False)
        or _required_plant_value(plant, "default_density", "density"),
        p_in=p_in,
        p_out=p_out,
        q_day=q_day,
        t=runtime,
        w=energy,
        q_fact=_median(aggregate_values, "flow_rate", required=False),
        p_electric=energy / runtime if energy is not None and runtime else _median(
            aggregate_values, "power", required=False
        ),
        nu=_median(aggregate_values, "viscosity", required=False) or plant["default_viscosity"],
        p_bg=p_bg,
        t_year=database.annual_runtime(plant_code, aggregate_code, end) or 8760.0,
    )


def telemetry_snapshots(
    database: AuditDatabase,
    plant_code: str,
    aggregate_code: str,
    start: datetime,
    end: datetime,
) -> list[TelemetrySnapshot]:
    """Вернуть точные физически допустимые пары давления выбранного окна."""
    return [
        snapshot
        for snapshot in _snapshot_candidates(database, plant_code, aggregate_code, start, end)
        if _is_usable_snapshot(snapshot)
    ]


def excluded_snapshots_by_manifold_pressure(
    database: AuditDatabase,
    plant_code: str,
    aggregate_code: str,
    start: datetime,
    end: datetime,
) -> int:
    """Количество снимков, исключённых из расчёта НА из-за p_вых ≤ p_БГ."""
    return sum(
        snapshot.p_bg_mpa is not None and snapshot.p_out_mpa <= snapshot.p_bg_mpa
        for snapshot in _snapshot_candidates(database, plant_code, aggregate_code, start, end)
    )


def _snapshot_candidates(
    database: AuditDatabase,
    plant_code: str,
    aggregate_code: str,
    start: datetime,
    end: datetime,
) -> list[TelemetrySnapshot]:
    """Вернуть все пары p_вх/p_вых; фильтры пригодности применяет публичная функция."""
    rows = database.measurements_in_window(
        plant_code, aggregate_code, start, end, include_station=True
    )
    pressure_by_time: dict[datetime, dict[str, float]] = {}
    p_bg_points: list[tuple[datetime, float]] = []
    power_points: list[tuple[datetime, float]] = []
    for row in rows:
        timestamp = datetime.fromisoformat(row["timestamp"])
        value = float(row["value"])
        if row["is_station"]:
            if row["metric"] == "p_bg":
                p_bg_points.append((timestamp, value))
            continue
        if row["metric"] in {"p_in", "p_out"}:
            pressure_by_time.setdefault(timestamp, {})[row["metric"]] = value
        elif row["metric"] == "power":
            power_points.append((timestamp, value))

    pairs = sorted(
        (
            (timestamp, values["p_in"], values["p_out"])
            for timestamp, values in pressure_by_time.items()
            if {"p_in", "p_out"} <= values.keys() and values["p_out"] > values["p_in"]
        ),
        key=lambda pair: pair[0],
    )
    snapshots = []
    for pair in pairs:
        timestamp, p_in, p_out = pair
        nearest_power = min(power_points, key=lambda point: abs(point[0] - timestamp), default=None)
        nearest_bg = min(p_bg_points, key=lambda point: abs(point[0] - timestamp), default=None)
        snapshots.append(
            TelemetrySnapshot(
                timestamp=timestamp,
                p_in_mpa=p_in,
                p_out_mpa=p_out,
                p_bg_mpa=nearest_bg[1] if nearest_bg else None,
                p_bg_gap=abs(nearest_bg[0] - timestamp) if nearest_bg else None,
                power_kw=nearest_power[1] if nearest_power else None,
                power_gap=abs(nearest_power[0] - timestamp) if nearest_power else None,
                is_stable=_is_stable_pressure_pair(pair, pressure_by_time),
            )
        )
    return snapshots


def _annual_runtime(
    database: AuditDatabase,
    plant_code: str,
    aggregate_code: str,
    end: datetime,
    *,
    track_clarifications: bool,
) -> float | None:
    annual_runtime = database.annual_runtime(plant_code, aggregate_code, end)
    if not track_clarifications:
        return annual_runtime
    if annual_runtime is None:
        database.upsert_clarification(
            plant_code,
            aggregate_code,
            field="t_year",
            provisional_value="8760",
            reason=(
                "Нет полного непрерывного года ежедневных моточасов; "
                "T_год временно принят равным 8760 ч."
            ),
        )
    else:
        database.resolve_clarification(plant_code, aggregate_code, field="t_year")
    return annual_runtime


def run_snapshot_audit(
    database: AuditDatabase,
    plant_code: str,
    aggregate_code: str,
    start: datetime,
    end: datetime,
    timestamp: datetime,
    *,
    track_clarifications: bool = True,
) -> SnapshotAudit:
    """Рассчитать выбранный снимок, явно используя доступные суточные итоги."""
    snapshot = next(
        (
            candidate
            for candidate in telemetry_snapshots(database, plant_code, aggregate_code, start, end)
            if candidate.timestamp == timestamp
        ),
        None,
    )
    if snapshot is None:
        raise ValueError(f"нет физически допустимой пары давления в {timestamp.isoformat()}")

    rows = database.measurements_in_window(
        plant_code, aggregate_code, start, end, include_station=True
    )
    aggregate_values: dict[str, list[float]] = {}
    station_values: dict[str, list[float]] = {}
    for row in rows:
        if row["value"] == 0:
            continue
        target = station_values if row["is_station"] else aggregate_values
        target.setdefault(row["metric"], []).append(float(row["value"]))
    if any(metric in station_values for metric in ("q_day", "runtime", "energy")):
        raise ValueError("станционный расход, наработка или энергия не распределены по агрегатам")

    plant = database.plant(plant_code)
    q_day = _single(aggregate_values, "q_day", required=False)
    runtime = _single(aggregate_values, "runtime", required=False)
    energy = _single(aggregate_values, "energy", required=False)
    q_fact = _median(aggregate_values, "flow_rate", required=False)
    uses_daily_flow = q_fact is None and q_day is not None and runtime is not None
    uses_daily_power = energy is not None and runtime is not None
    annual_runtime = _annual_runtime(
        database,
        plant_code,
        aggregate_code,
        end,
        track_clarifications=track_clarifications,
    )
    regime = RegimeMeasurement(
        rho=_median(aggregate_values, "density", required=False)
        or _required_plant_value(plant, "default_density", "density"),
        p_in=snapshot.p_in_mpa,
        p_out=snapshot.p_out_mpa,
        q_day=q_day,
        t=runtime,
        w=energy,
        q_fact=q_fact,
        p_electric=energy / runtime if uses_daily_power else snapshot.power_kw,
        nu=_median(aggregate_values, "viscosity", required=False) or plant["default_viscosity"],
        p_bg=snapshot.p_bg_mpa,
        t_year=annual_runtime or 8760.0,
    )
    aggregate = database.aggregate(plant_code, aggregate_code)
    passport = database.active_passport(plant_code, aggregate_code, start)
    audit = audit_aggregate(
        _aggregate_spec(aggregate, passport, regime=regime), Branch(plant["branch"])
    )
    return SnapshotAudit(
        audit=audit,
        snapshot=snapshot,
        uses_daily_flow=uses_daily_flow,
        uses_daily_power=uses_daily_power,
        annual_runtime_is_assumed=annual_runtime is None,
    )


def _operating_pressures(
    rows: list[dict], *, require_daily_pressure_coverage: bool
) -> tuple[float, float, float | None]:
    """Усреднить давления из пар, ближайших к положительной мощности агрегата."""
    power_times: list[datetime] = []
    pressure_by_time: dict[datetime, dict[str, float]] = {}
    p_bg_points: list[tuple[datetime, float]] = []
    for row in rows:
        timestamp = datetime.fromisoformat(row["timestamp"])
        value = float(row["value"])
        if row["is_station"]:
            if row["metric"] == "p_bg":
                p_bg_points.append((timestamp, value))
            continue
        if row["metric"] == "power" and value > 0:
            power_times.append(timestamp)
        if row["metric"] in {"p_in", "p_out"}:
            pressure_by_time.setdefault(timestamp, {})[row["metric"]] = value

    pairs = [
        (timestamp, values["p_in"], values["p_out"])
        for timestamp, values in pressure_by_time.items()
        if {"p_in", "p_out"} <= values.keys()
    ]
    operating_pairs = []
    for power_time in power_times:
        if not pairs:
            break
        pair = min(pairs, key=lambda candidate: abs(candidate[0] - power_time))
        if abs(pair[0] - power_time) <= _PRESSURE_POWER_MAX_GAP and _is_stable_pressure_pair(
            pair, pressure_by_time
        ):
            operating_pairs.append(pair)
    if not operating_pairs:
        raise ValueError(
            "нет согласованной пары p_вх/p_вых с p_вых > p_вх рядом с положительной мощностью "
            "в выбранном окне"
        )
    if (
        require_daily_pressure_coverage
        and len(operating_pairs) / len(power_times) < _MIN_PRESSURE_COVERAGE
    ):
        raise ValueError(
            f"давление покрывает только {len(operating_pairs)} из {len(power_times)} "
            "точек положительной мощности в выбранном окне"
        )

    selected_pairs = operating_pairs if require_daily_pressure_coverage else [operating_pairs[-1]]
    p_bg = []
    for timestamp, _, _ in selected_pairs:
        if p_bg_points:
            nearest = min(p_bg_points, key=lambda point: abs(point[0] - timestamp))
            if abs(nearest[0] - timestamp) <= _PRESSURE_POWER_MAX_GAP:
                p_bg.append(nearest[1])
    return (
        float(mean(pair[1] for pair in selected_pairs)),
        float(mean(pair[2] for pair in selected_pairs)),
        float(mean(p_bg)) if p_bg else None,
    )


def _is_stable_pressure_pair(
    pair: tuple[datetime, float, float], pressure_by_time: dict[datetime, dict[str, float]]
) -> bool:
    timestamp, p_in, p_out = pair
    if p_out <= p_in:
        return False
    return not any(
        candidate_timestamp != timestamp
        and abs(candidate_timestamp - timestamp) <= _PRESSURE_STABILITY_WINDOW
        and abs(candidate_value - value) / abs((candidate_timestamp - timestamp).total_seconds())
        > _PRESSURE_STABILITY_MAX_RATE_MPA_PER_SECOND
        for metric, value in (("p_in", p_in), ("p_out", p_out))
        for candidate_timestamp, candidate_values in pressure_by_time.items()
        if (candidate_value := candidate_values.get(metric)) is not None
    )


def _is_usable_snapshot(snapshot: TelemetrySnapshot) -> bool:
    return (
        snapshot.is_stable
        and snapshot.power_kw is not None
        and snapshot.power_kw > 0
        and snapshot.power_gap is not None
        and snapshot.power_gap <= _PRESSURE_POWER_MAX_GAP
        and (snapshot.p_bg_mpa is None or snapshot.p_out_mpa > snapshot.p_bg_mpa)
    )


def run_telemetry_audit(
    database: AuditDatabase,
    plant_code: str,
    aggregate_code: str,
    start: datetime,
    end: datetime,
    *,
    track_clarifications: bool = True,
    require_daily_pressure_coverage: bool = True,
) -> AuditResult:
    """Провести аудит по паспорту и временному окну без YAML-режима."""
    plant = database.plant(plant_code)
    aggregate = database.aggregate(plant_code, aggregate_code)
    passport = database.active_passport(plant_code, aggregate_code, start)
    _annual_runtime(
        database,
        plant_code,
        aggregate_code,
        end,
        track_clarifications=track_clarifications,
    )
    spec = _aggregate_spec(
        aggregate,
        passport,
        regime=build_regime(
            database,
            plant_code,
            aggregate_code,
            start,
            end,
            require_daily_pressure_coverage=require_daily_pressure_coverage,
        ),
    )
    return audit_aggregate(spec, Branch(plant["branch"]))


def telemetry_day_status(
    database: AuditDatabase,
    plant_code: str,
    aggregate_code: str,
    day: date,
) -> str:
    """Вернуть единый статус пригодности суток для календаря и экрана анализа."""
    start = datetime.combine(day, time.min)
    end = start + timedelta(days=1)
    snapshots = telemetry_snapshots(database, plant_code, aggregate_code, start, end)
    if not snapshots:
        return "insufficient"
    try:
        run_telemetry_audit(
            database,
            plant_code,
            aggregate_code,
            start,
            end,
            track_clarifications=False,
        )
    except (ArithmeticError, KeyError, ValueError):
        try:
            run_snapshot_audit(
                database,
                plant_code,
                aggregate_code,
                start,
                end,
                snapshots[-1].timestamp,
                track_clarifications=False,
            )
        except (ArithmeticError, KeyError, ValueError):
            return "insufficient"
        return "snapshot"
    return "ready"


def telemetry_date_statuses(
    database: AuditDatabase,
    plant_code: str,
    aggregate_code: str,
    dates: list[date],
) -> dict[date, str]:
    """Вернуть статусы дней телеметрии через единый расчёт пригодности суток."""
    return {
        day: telemetry_day_status(database, plant_code, aggregate_code, day)
        for day in dates
    }


def object_from_database(
    database: AuditDatabase, plant_code: str, at: datetime, *, aggregate_code: str | None = None
) -> ObjectSpec:
    """Собрать UI-спеку объекта исключительно из БД."""
    plant = database.plant(plant_code)
    aggregates = (
        [database.aggregate(plant_code, aggregate_code)]
        if aggregate_code is not None
        else database.aggregates(plant_code)
    )
    return ObjectSpec(
        id=plant["code"],
        name=plant["name"],
        water_type=plant["water_type"],
        branch=plant["branch"],
        source="SQLite telemetry",
        aggregates=[
            _aggregate_spec(
                aggregate, database.active_passport(plant_code, aggregate["code"], at)
            )
            for aggregate in aggregates
        ],
    )


def _aggregate_spec(
    aggregate: dict, passport: dict, *, regime: RegimeMeasurement | None = None
) -> AggregateSpec:
    return AggregateSpec(
        id=aggregate["code"],
        role=aggregate["role"],
        pump=PumpSpec(
            model=passport["pump_model"],
            kind=passport["pump_kind"],
            q_nom=passport["pump_q_nom"],
            h_nom=passport["pump_h_nom"],
            eta_nom=passport["pump_eta_nom"],
            power_nom=passport["pump_power_nom"],
            n_rpm=passport["pump_n_rpm"],
            curve_qh=json.loads(passport["pump_curve_qh_json"]),
            curve_qeta=json.loads(passport["pump_curve_qeta_json"]),
        ),
        motor=MotorSpec(
            model=passport["motor_model"],
            synchronous=bool(passport["motor_synchronous"]),
            p_nom=passport["motor_p_nom"],
            eta_nom=passport["motor_eta_nom"],
            cos_phi=passport["motor_cos_phi"],
            voltage_kv=passport["motor_voltage_kv"],
            i_nom=passport["motor_i_nom"],
            n_rpm=passport["motor_n_rpm"],
        ),
        transmission=TransmissionSpec(
            model=passport["transmission_model"],
            ratio=passport["transmission_ratio"],
            efficiency=passport["transmission_eff"],
        ),
        vfd=bool(passport["vfd"]),
        regime=regime,
    )


def _median(
    values: dict[str, list[float]],
    metric: str,
    fallback: dict[str, list[float]] | None = None,
    *,
    required: bool = True,
) -> float | None:
    points = values.get(metric) or (fallback or {}).get(metric)
    if not points:
        if required:
            raise ValueError(f"нет telemetry metric {metric} в выбранном окне")
        return None
    return float(median(points))


def _single(values: dict[str, list[float]], metric: str, *, required: bool) -> float | None:
    points = values.get(metric, [])
    if not points:
        if required:
            raise ValueError(f"нет telemetry metric {metric} в выбранном окне")
        return None
    if len(set(points)) != 1:
        raise ValueError(f"несколько значений {metric} в выбранном окне")
    return points[0]


def _required_plant_value(plant: dict, field: str, metric: str) -> float:
    value = plant[field]
    if value is None:
        raise ValueError(f"нет telemetry metric {metric} и паспортного значения объекта")
    return float(value)
