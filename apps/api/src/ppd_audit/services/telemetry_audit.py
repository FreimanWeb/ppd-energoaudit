"""Построение расчётного режима из временного окна SQLite-телеметрии."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from itertools import pairwise
from statistics import mean, median
from zoneinfo import ZoneInfo

from ..core.audit import AuditResult, audit_aggregate
from ..db import AuditDatabase
from ..measurement_quality import usable_measurement
from ..spec import (
    AggregateSpec,
    Branch,
    EquipmentData,
    ObjectSpec,
    RegimeMeasurement,
)
from .manual_data import (
    apply_equipment_override,
    equipment_from_passport,
    manual_measurement,
)
from .telemetry_quality import TelemetryQuality, assess_telemetry_quality


_PRESSURE_STABILITY_WINDOW = timedelta(minutes=1)
_PRESSURE_STABILITY_MAX_RATE_MPA_PER_SECOND = 0.02
_MIN_PRESSURE_COVERAGE = 0.8
_POWER_INTERVAL = timedelta(minutes=30)


@dataclass(frozen=True)
class TelemetrySnapshot:
    """Один снимок режима: давления действуют с последнего изменения."""

    timestamp: datetime
    p_in_mpa: float
    p_out_mpa: float
    p_bg_mpa: float | None
    p_bg_age: timedelta | None
    power_kw: float | None
    power_age: timedelta | None
    is_stable: bool


@dataclass(frozen=True)
class SnapshotAudit:
    """Расчёт по выбранному снимку и явно зафиксированные допущения."""

    audit: AuditResult
    snapshot: TelemetrySnapshot
    uses_daily_flow: bool
    uses_daily_power: bool
    quality: TelemetryQuality
    sources: dict[str, str]


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
        if not usable_measurement(row):
            continue
        target = station_values if row["is_station"] else aggregate_values
        target.setdefault(row["metric"], []).append(float(row["value"]))

    if any(metric in station_values for metric in ("q_day", "runtime", "energy")):
        raise ValueError("станционный расход, наработка или энергия не распределены по агрегатам")
    plant = database.plant(plant_code)
    density = database.plant_density_default(plant_code, start.date())
    if density:
        plant["default_density"] = density["density_kgm3"]
    state_rows = database.state_measurements_in_window(plant_code, aggregate_code, start, end)
    p_in, p_out, p_bg = _operating_pressures(
        state_rows,
        start,
        end,
        require_daily_pressure_coverage=require_daily_pressure_coverage,
    )
    q_day = _single(aggregate_values, "q_day", required=False)
    runtime = _single(aggregate_values, "runtime", required=False)
    energy = _single(aggregate_values, "energy", required=False)
    power_values = [power for _, power, _ in _power_states(start, end, state_rows)]

    return RegimeMeasurement(
        rho=_median(aggregate_values, "density", required=False)
        or _required_plant_value(plant, "default_density", "density"),
        p_in=p_in,
        p_out=p_out,
        q_day=q_day,
        t=runtime,
        w=energy,
        q_fact=_median(aggregate_values, "flow_rate", required=False),
        power_daily_reported=_single(aggregate_values, "power_daily_reported", required=False),
        p_electric=(
            float(median(power_values))
            if power_values
            else energy / runtime
            if energy is not None and runtime
            else None
        ),
        nu=_median(aggregate_values, "viscosity", required=False) or plant["default_viscosity"],
        p_bg=p_bg,
        t_year=database.annual_runtime(plant_code, aggregate_code, end),
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
    """Вернуть пары давлений на измеренных точках Q, если есть канал расхода."""
    state_rows = database.state_measurements_in_window(plant_code, aggregate_code, start, end)
    pressure_rows = [row for row in state_rows if row["metric"] != "power"]
    flow_rows = [
        row
        for row in database.measurements_in_window(plant_code, aggregate_code, start, end)
        if not row["is_station"] and row["metric"] == "flow_rate"
    ]
    sample_times = (
        sorted({
            datetime.fromisoformat(row["timestamp"])
            for row in flow_rows
            if usable_measurement(row) and float(row["value"]) > 0
        })
        if flow_rows
        else None
    )
    power_points = _power_states(start, end, state_rows, sample_times=sample_times)

    snapshots = []
    unstable_changes = _unstable_pressure_change_times(pressure_rows)
    for timestamp, p_in, p_out, p_bg, p_bg_age, power, power_age in _pressure_states_at(
        power_points, pressure_rows
    ):
        pair = (timestamp, p_in, p_out)
        if p_out <= p_in:
            continue
        snapshots.append(
            TelemetrySnapshot(
                timestamp=timestamp,
                p_in_mpa=p_in,
                p_out_mpa=p_out,
                p_bg_mpa=p_bg,
                p_bg_age=p_bg_age,
                power_kw=power,
                power_age=power_age,
                is_stable=_is_stable_pressure_pair(pair, unstable_changes),
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
                "Нет полного непрерывного года ежедневной наработки; "
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
    equipment_override: EquipmentData | None = None,
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
    state_rows = database.state_measurements_in_window(plant_code, aggregate_code, start, end)
    aggregate_values: dict[str, list[float]] = {}
    station_values: dict[str, list[float]] = {}
    for row in rows:
        if not usable_measurement(row):
            continue
        target = station_values if row["is_station"] else aggregate_values
        target.setdefault(row["metric"], []).append(float(row["value"]))
    if any(metric in station_values for metric in ("q_day", "runtime", "energy")):
        raise ValueError("станционный расход, наработка или энергия не распределены по агрегатам")

    plant = database.plant(plant_code)
    density = database.plant_density_default(plant_code, start.date())
    if density:
        plant["default_density"] = density["density_kgm3"]
    q_day = _single(aggregate_values, "q_day", required=False)
    runtime = _single(aggregate_values, "runtime", required=False)
    energy = _single(aggregate_values, "energy", required=False)
    q_fact = next(
        (
            float(row["value"])
            for row in rows
            if not row["is_station"]
            and row["metric"] == "flow_rate"
            and datetime.fromisoformat(row["timestamp"]) == timestamp
            and usable_measurement(row)
        ),
        None,
    )
    if q_fact is not None and q_fact <= 0:
        raise ValueError("Для режимного УРЭ нужна положительная подача в выбранный момент")
    uses_daily_flow = q_fact is None and q_day is not None and runtime is not None
    uses_daily_power = snapshot.power_kw is None and energy is not None and runtime is not None
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
        power_daily_reported=_single(aggregate_values, "power_daily_reported", required=False),
        p_electric=energy / runtime if uses_daily_power else snapshot.power_kw,
        nu=_median(aggregate_values, "viscosity", required=False) or plant["default_viscosity"],
        p_bg=snapshot.p_bg_mpa,
        t_year=annual_runtime,
    )
    aggregate = database.aggregate(plant_code, aggregate_code)
    passport = database.active_passport(plant_code, aggregate_code, timestamp)
    agg_spec = _aggregate_spec(aggregate, passport, regime=regime)
    if equipment_override is not None:
        agg_spec = apply_equipment_override(agg_spec, equipment_override)
    audit = audit_aggregate(agg_spec, Branch(plant["branch"]))
    integrated_energy, powered_hours = _power_reconciliation(start, end, state_rows)
    integrated_flow = _integrated_flow_rate(start, end, rows)
    quality = assess_telemetry_quality(
        eta_unit=audit.regime.eta_unit,
        uses_daily_flow=uses_daily_flow,
        uses_daily_power=uses_daily_power,
        energy_kwh=energy,
        integrated_energy_kwh=integrated_energy,
        runtime_hours=runtime,
        powered_hours=powered_hours,
        q_day_m3=q_day,
        integrated_flow_m3=integrated_flow,
    )
    sources = _regime_sources(
        [row for row in rows if usable_measurement(row)],
        state_rows,
        timestamp,
        uses_daily_flow,
        uses_daily_power,
    )
    if density and not aggregate_values.get("density"):
        sources["ρ"] = f"{density['source']}; доступно с {density['available_from']}"
    return SnapshotAudit(
        audit=audit,
        snapshot=snapshot,
        uses_daily_flow=uses_daily_flow,
        uses_daily_power=uses_daily_power,
        quality=quality,
        sources=sources,
    )


def _operating_pressures(
    state_rows: list[dict],
    start: datetime,
    end: datetime,
    *,
    require_daily_pressure_coverage: bool,
) -> tuple[float, float, float | None]:
    """Усреднить актуальные на момент мощности давления работающего агрегата."""
    pressure_rows = [row for row in state_rows if row["metric"] != "power"]
    power_points = [
        (timestamp, power)
        for timestamp, power, _ in _power_states(start, end, state_rows)
        if power > 0
    ]

    unstable_changes = _unstable_pressure_change_times(pressure_rows)
    operating_pairs = [
        (timestamp, p_in, p_out, p_bg)
        for timestamp, p_in, p_out, p_bg, _, _, _ in _pressure_states_at(
            power_points, pressure_rows
        )
        if (
            p_out > p_in
            and (p_bg is None or p_out > p_bg)
            and _is_stable_pressure_pair((timestamp, p_in, p_out), unstable_changes)
        )
    ]
    if not operating_pairs:
        raise ValueError(
            "нет актуальных p_вх/p_вых с p_вых > p_вх в момент положительной мощности "
            "в выбранном окне"
        )
    if (
        require_daily_pressure_coverage
        and len(operating_pairs) / len(power_points) < _MIN_PRESSURE_COVERAGE
    ):
        raise ValueError(
            f"давление покрывает только {len(operating_pairs)} из {len(power_points)} "
            "точек положительной мощности в выбранном окне"
        )

    selected_pairs = operating_pairs if require_daily_pressure_coverage else [operating_pairs[-1]]
    p_bg = [pair[3] for pair in selected_pairs if pair[3] is not None]
    return (
        float(mean(pair[1] for pair in selected_pairs)),
        float(mean(pair[2] for pair in selected_pairs)),
        float(mean(p_bg)) if p_bg else None,
    )


def _power_states(
    start: datetime,
    end: datetime,
    state_rows: list[dict],
    *,
    sample_times: list[datetime] | None = None,
) -> list[tuple[datetime, float, timedelta]]:
    """Удерживать предыдущее P_эл на заданных точках или на 30-минутной сетке."""
    updates = sorted(
        [
            (
                datetime.fromisoformat(row["timestamp"]),
                float(row["value"]) if usable_measurement(row) else None,
            )
            for row in state_rows
            if not row["is_station"] and row["metric"] == "power"
        ],
        key=lambda update: update[0],
    )
    if not updates:
        return []
    if sample_times is None:
        window_updates = [timestamp for timestamp, _ in updates if start <= timestamp < end]
        if not _is_fixed_power_series(updates):
            sample_times = window_updates
        else:
            sample_times = list(_power_slots(start, end, updates[0][0]))

    states = []
    update_index = 0
    value: float | None = None
    changed_at: datetime | None = None
    for timestamp in sample_times:
        while update_index < len(updates) and updates[update_index][0] <= timestamp:
            changed_at, value = updates[update_index]
            update_index += 1
        if value is not None and changed_at is not None:
            states.append((timestamp, value, timestamp - changed_at))
    return states


def _power_reconciliation(
    start: datetime, end: datetime, state_rows: list[dict]
) -> tuple[float | None, float | None]:
    """Вернуть W и T из полного 30-минутного ряда мощности, иначе не сравнивать."""
    updates = [
        (datetime.fromisoformat(row["timestamp"]), float(row["value"]))
        for row in state_rows
        if not row["is_station"] and row["metric"] == "power"
    ]
    if not updates or not _is_fixed_power_series(updates):
        return None, None
    states = _power_states(start, end, state_rows)
    expected_slots = int((end - start) / _POWER_INTERVAL)
    if len(states) != expected_slots or states[0][0] != start:
        return None, None
    interval_hours = _POWER_INTERVAL.total_seconds() / 3600
    return (
        sum(power * interval_hours for _, power, _ in states),
        sum(interval_hours for _, power, _ in states if power > 0),
    )


def _integrated_flow_rate(start: datetime, end: datetime, rows: list[dict]) -> float | None:
    """Интегрировать Q только для полного равномерного ряда с началом в окне."""
    flow_rows = [
        row
        for row in rows
        if not row["is_station"]
        and row["metric"] == "flow_rate"
        and start <= datetime.fromisoformat(row["timestamp"]) < end
    ]
    if not all(usable_measurement(row) for row in flow_rows):
        return None
    points = sorted(
        (
            datetime.fromisoformat(row["timestamp"]),
            float(row["value"]),
        )
        for row in flow_rows
    )
    if len(points) < 2 or points[0][0] != start:
        return None
    intervals = {later - earlier for (earlier, _), (later, _) in pairwise(points)}
    if len(intervals) != 1:
        return None
    interval = intervals.pop()
    if interval <= timedelta() or points[-1][0] + interval != end:
        return None
    hours = interval.total_seconds() / 3600
    return sum(value * hours for _, value in points)


def _regime_sources(
    rows: list[dict],
    state_rows: list[dict],
    timestamp: datetime,
    uses_daily_flow: bool,
    uses_daily_power: bool,
) -> dict[str, str]:
    """Источники раздельных суточных показателей и входов выбранного снимка."""
    sources = {
        "p_вх": _latest_source(state_rows, "p_in", timestamp),
        "p_вых": _latest_source(state_rows, "p_out", timestamp),
        "P_сут_отч": _measurement_source(rows, "power_daily_reported"),
        "p_БГ": _latest_source(state_rows, "p_bg", timestamp),
        "ρ": _measurement_source(rows, "density"),
        "Q_сут": _measurement_source(rows, "q_day"),
        "W_сут": _measurement_source(rows, "energy"),
        "T_сут": _measurement_source(rows, "runtime"),
    }
    if not uses_daily_flow:
        sources["Q"] = _measurement_source(rows, "flow_rate", timestamp=timestamp)
    if not uses_daily_power:
        sources["P_эл"] = _latest_source(state_rows, "power", timestamp)
    return {metric: source for metric, source in sources.items() if source is not None}


def _latest_source(rows: list[dict], metric: str, timestamp: datetime) -> str | None:
    candidates = [
        row
        for row in rows
        if row["metric"] == metric and datetime.fromisoformat(row["timestamp"]) <= timestamp
    ]
    return _source_reference(candidates[-1]) if candidates else None


def _measurement_source(
    rows: list[dict],
    metric: str,
    *,
    timestamp: datetime | None = None,
) -> str | None:
    candidates = [
        row
        for row in rows
        if not row["is_station"]
        and row["metric"] == metric
        and (timestamp is None or datetime.fromisoformat(row["timestamp"]) == timestamp)
    ]
    return _source_reference(candidates[-1]) if candidates else None


def _source_reference(row: dict) -> str | None:
    parts = [
        row.get("source_kind"),
        row.get("source_file"),
        row.get("source_sheet"),
        str(row["source_row"]) if row.get("source_row") is not None else None,
        row.get("source_tag"),
        row.get("source_label"),
    ]
    values = [str(part) for part in parts if part not in (None, "")]
    return " · ".join(values) if values else None


def _is_fixed_power_series(updates: list[tuple[datetime, float]]) -> bool:
    return all(
        timestamp.minute % 30 == 0 and timestamp.second == 0 and timestamp.microsecond == 0
        for timestamp, _ in updates
    )


def _power_slots(start: datetime, end: datetime, anchor: datetime):
    offset = (start - anchor) % _POWER_INTERVAL
    timestamp = start if offset == timedelta() else start + _POWER_INTERVAL - offset
    while timestamp < end:
        yield timestamp
        timestamp += _POWER_INTERVAL


def _pressure_states_at(
    power_points: list[tuple[datetime, float] | tuple[datetime, float, timedelta]],
    pressure_rows: list[dict],
) -> list[tuple[datetime, float, float, float | None, timedelta | None, float, timedelta | None]]:
    """Сопоставить мощности с последним изменением давления на тот же момент."""
    updates = sorted(
        [
            (
                datetime.fromisoformat(row["timestamp"]),
                row["metric"],
                float(row["value"]) if usable_measurement(row) else None,
                bool(row["is_station"]),
            )
            for row in pressure_rows
        ],
        key=lambda update: update[0],
    )
    state: dict[str, float] = {}
    p_bg_timestamp: datetime | None = None
    update_index = 0
    states = []
    for point in sorted(power_points, key=lambda point: point[0]):
        timestamp, power = point[:2]
        power_age = point[2] if len(point) == 3 else None
        while update_index < len(updates) and updates[update_index][0] <= timestamp:
            update_timestamp, metric, value, is_station = updates[update_index]
            if value is None:
                state.pop(metric, None)
                if metric == "p_bg":
                    p_bg_timestamp = None
                update_index += 1
                continue
            if is_station:
                if metric == "p_bg":
                    state[metric] = value
                    p_bg_timestamp = update_timestamp
            else:
                state[metric] = value
            update_index += 1
        if {"p_in", "p_out"} <= state.keys():
            states.append((
                timestamp,
                state["p_in"],
                state["p_out"],
                state.get("p_bg"),
                timestamp - p_bg_timestamp if p_bg_timestamp else None,
                power,
                power_age,
            ))
    return states


def _unstable_pressure_change_times(pressure_rows: list[dict]) -> list[datetime]:
    """Моменты быстрых изменений p_вх/p_вых, исключаемые как переходный режим."""
    previous: dict[str, tuple[datetime, float]] = {}
    unstable = []
    updates = sorted(
        [
            (
                datetime.fromisoformat(row["timestamp"]),
                row["metric"],
                float(row["value"]),
            )
            for row in pressure_rows
            if not row["is_station"]
            and row["metric"] in {"p_in", "p_out"}
            and usable_measurement(row)
        ],
        key=lambda update: update[0],
    )
    for timestamp, metric, value in updates:
        if metric in previous:
            previous_timestamp, previous_value = previous[metric]
            elapsed = (timestamp - previous_timestamp).total_seconds()
            if (
                elapsed
                and abs(value - previous_value) / elapsed
                > _PRESSURE_STABILITY_MAX_RATE_MPA_PER_SECOND
            ):
                unstable.append(timestamp)
        previous[metric] = (timestamp, value)
    return unstable


def _is_stable_pressure_pair(
    pair: tuple[datetime, float, float], unstable_change_times: list[datetime]
) -> bool:
    timestamp, p_in, p_out = pair
    if p_out <= p_in:
        return False
    return not any(
        abs(change_time - timestamp) <= _PRESSURE_STABILITY_WINDOW
        for change_time in unstable_change_times
    )


def _is_usable_snapshot(snapshot: TelemetrySnapshot) -> bool:
    return (
        snapshot.is_stable
        and snapshot.power_kw is not None
        and snapshot.power_kw > 0
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
    density = database.plant_density_default(plant_code, start.date())
    if density:
        plant["default_density"] = density["density_kgm3"]
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
        daily_pressure_coverage_is_complete = False
    else:
        daily_pressure_coverage_is_complete = True
    try:
        snapshot_audit = run_snapshot_audit(
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
    if not snapshot_audit.quality.allows_economic_conclusions:
        return "unfit"
    return "ready" if daily_pressure_coverage_is_complete else "snapshot"


def telemetry_date_statuses(
    database: AuditDatabase,
    plant_code: str,
    aggregate_code: str,
    dates: list[date],
) -> dict[date, str]:
    """Вернуть статусы дней телеметрии через единый расчёт пригодности суток."""
    return {day: telemetry_day_status(database, plant_code, aggregate_code, day) for day in dates}


def object_from_database(
    database: AuditDatabase,
    plant_code: str,
    at: datetime,
    *,
    aggregate_code: str | None = None,
    equipment_override: EquipmentData | None = None,
) -> ObjectSpec:
    """Собрать UI-спеку объекта исключительно из БД.

    equipment_override — временный сценарий: заменяет оборудование целевого
    агрегата только в возвращаемой спеке, в БД ничего не пишет.
    """
    plant = database.plant(plant_code)
    density = database.plant_density_default(plant_code, at.date())
    if density:
        plant["default_density"] = density["density_kgm3"]
    aggregates = (
        [database.aggregate(plant_code, aggregate_code)]
        if aggregate_code is not None
        else database.aggregates(plant_code)
    )

    def _spec(aggregate: dict) -> AggregateSpec:
        spec = _aggregate_spec(
            aggregate, database.active_passport(plant_code, aggregate["code"], at)
        )
        if equipment_override is not None and (
            aggregate_code is None or aggregate["code"] == aggregate_code
        ):
            spec = apply_equipment_override(spec, equipment_override)
        return spec

    return ObjectSpec(
        id=plant["code"],
        name=plant["name"],
        water_type=plant["water_type"],
        branch=plant["branch"],
        source="SQLite telemetry",
        technical_places={
            aggregate["technical_place_code"]: aggregate["technical_place_name"]
            for aggregate in aggregates
        },
        aggregates=[_spec(aggregate) for aggregate in aggregates],
    )


def _aggregate_spec(
    aggregate: dict, passport: dict, *, regime: RegimeMeasurement | None = None
) -> AggregateSpec:
    equipment = equipment_from_passport(passport)
    return AggregateSpec(
        id=aggregate["code"],
        technical_place_code=aggregate.get("technical_place_code", "main"),
        role=aggregate["role"],
        pump=equipment.pump,
        motor=equipment.motor,
        transmission=equipment.transmission,
        vfd=equipment.vfd,
        runtime_total_h=aggregate.get("runtime_total_h"),
        regime=regime,
    )


def run_manual_audit(
    database: AuditDatabase,
    plant_code: str,
    aggregate_code: str,
    measurement_id: int,
    *,
    equipment_override: EquipmentData | None = None,
) -> tuple[AuditResult, dict]:
    """Аудит по явно выбранному ручному замеру и паспорту на момент замера."""
    row = manual_measurement(database, plant_code, aggregate_code, measurement_id)
    measured_at = datetime.fromisoformat(row["measured_at"])
    regime = RegimeMeasurement(**json.loads(row["regime_json"]))
    plant = database.plant(plant_code)
    aggregate = database.aggregate(plant_code, aggregate_code)
    passport = database.active_passport(plant_code, aggregate_code, measured_at)
    spec = _aggregate_spec(aggregate, passport, regime=regime)
    if equipment_override is not None:
        spec = apply_equipment_override(spec, equipment_override)
    return audit_aggregate(spec, Branch(plant["branch"])), row


def run_field_trip_audit(
    database: AuditDatabase,
    plant_code: str,
    aggregate_code: str,
    regime: RegimeMeasurement,
    *,
    equipment_override: EquipmentData | None = None,
) -> AuditResult:
    """Аудит выездного режима с паспортом БД на момент измерения.

    YAML хранит только исходный замер; оборудование собирается из базовых
    паспортов и журнала на measured_at. Без действующих сведений — KeyError,
    без подстановки оборудования из YAML.
    """
    measured_at = (
        datetime.combine(regime.measured_at, time.min)
        if regime.measured_at is not None
        else datetime.now(ZoneInfo("Europe/Moscow")).replace(tzinfo=None)
    )
    plant = database.plant(plant_code)
    aggregate = database.aggregate(plant_code, aggregate_code)
    passport = database.active_passport(plant_code, aggregate_code, measured_at)
    spec = _aggregate_spec(aggregate, passport, regime=regime)
    if equipment_override is not None:
        spec = apply_equipment_override(spec, equipment_override)
    return audit_aggregate(spec, Branch(plant["branch"]))


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
