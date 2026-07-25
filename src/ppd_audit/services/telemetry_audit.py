"""Построение расчётного режима из временного окна SQLite-телеметрии."""

from __future__ import annotations

import json
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
            pair, pairs
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
    pair: tuple[datetime, float, float], pairs: list[tuple[datetime, float, float]]
) -> bool:
    timestamp, p_in, p_out = pair
    if p_out <= p_in:
        return False
    return not any(
        candidate != pair
        and abs(candidate[0] - timestamp) <= _PRESSURE_STABILITY_WINDOW
        and max(abs(candidate[1] - p_in), abs(candidate[2] - p_out))
        / abs((candidate[0] - timestamp).total_seconds())
        > _PRESSURE_STABILITY_MAX_RATE_MPA_PER_SECOND
        for candidate in pairs
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
    annual_runtime = database.annual_runtime(plant_code, aggregate_code, end)
    if track_clarifications:
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


def telemetry_date_statuses(
    database: AuditDatabase,
    plant_code: str,
    aggregate_code: str,
    dates: list[date],
) -> dict[date, str]:
    """Вернуть пригодность дней телеметрии для расчёта агрегата."""
    statuses = {}
    for day in dates:
        start = datetime.combine(day, time.min)
        try:
            run_telemetry_audit(
                database,
                plant_code,
                aggregate_code,
                start,
                start + timedelta(days=1),
                track_clarifications=False,
            )
        except (ArithmeticError, KeyError, ValueError):
            try:
                run_telemetry_audit(
                    database,
                    plant_code,
                    aggregate_code,
                    start,
                    start + timedelta(days=1),
                    track_clarifications=False,
                    require_daily_pressure_coverage=False,
                )
            except (ArithmeticError, KeyError, ValueError):
                statuses[day] = "insufficient"
            else:
                statuses[day] = "snapshot"
        else:
            statuses[day] = "ready"
    return statuses


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
