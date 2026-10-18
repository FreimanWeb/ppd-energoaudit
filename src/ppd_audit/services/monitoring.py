"""Read-only monitoring: daily balances and synchronous measurements stay separate."""

from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..core.audit import ETA_VFD_DEFAULT
from ..core.specific_energy import sec_calc, sec_optimal
from ..db import AuditDatabase
from .telemetry_audit import telemetry_snapshots


METRICS = ("q_day", "energy", "flow_rate", "power", "p_in", "p_out")
FIELDS = (
    "sec_kwh_m3",
    "sec_calc_kwh_m3",
    "sec_optimal_kwh_m3",
    "efficiency",
    "nominal_efficiency",
    "flow_m3h",
    "power_kw",
    "p_in_mpa",
    "p_out_mpa",
    "volume_m3",
    "energy_kwh",
)


def _nonnegative(value):
    return value if value is not None and math.isfinite(value) and value >= 0 else None


def _load(database, object_id=None, start=None, end=None, aggregate_code=None, history_days=30):
    with closing(sqlite3.connect(database.path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        plants = [
            dict(row)
            for row in conn.execute("""
            SELECT p.code, p.name, p.water_type, n.name AS ngdu_name
            FROM plants p JOIN ngdu n ON n.id = p.ngdu_id
            WHERE (p.is_example = 0 OR p.code = 'demo-ppd')
            ORDER BY n.name, p.name
        """)
        ]
        aggregates = [
            dict(row)
            for row in conn.execute("""
            SELECT p.code AS object_id, a.code, a.role, a.id
            FROM aggregates a JOIN technical_places tp ON tp.id = a.technical_place_id
            JOIN plants p ON p.id = tp.plant_id WHERE tp.code = 'main'
        """)
        ]
        params = [aggregate_code, aggregate_code]
        query = """
            WITH latest AS (
                SELECT tm.plant_id, MAX(tm.timestamp) AS latest_at FROM telemetry_measurements tm
                JOIN technical_places tp ON tp.id = tm.technical_place_id
                LEFT JOIN aggregates a ON a.id = tm.aggregate_id
                WHERE tm.metric IN ('q_day','energy','flow_rate','power','p_in','p_out')
                  AND tp.code = 'main' AND (? IS NULL OR a.code = ?)
                GROUP BY tm.plant_id
            )
            SELECT p.code AS object_id, tm.aggregate_id, tm.timestamp, tm.metric, tm.value,
                   tm.quality, l.latest_at
            FROM telemetry_measurements tm JOIN plants p ON p.id = tm.plant_id
            JOIN technical_places tp ON tp.id = tm.technical_place_id
            JOIN latest l ON l.plant_id = tm.plant_id
            WHERE (p.is_example = 0 OR p.code = 'demo-ppd') AND tp.code = 'main'
              AND tm.metric IN ('q_day','energy','flow_rate','power','p_in','p_out')
        """
        if object_id:
            query += " AND p.code = ?"
            params.append(object_id)
        if start is not None:
            query += " AND tm.timestamp >= ? AND tm.timestamp < ?"
            params.extend((
                start.isoformat() + "T00:00:00",
                (end + timedelta(days=1)).isoformat() + "T00:00:00",
            ))
        else:
            query += " AND tm.timestamp >= replace(datetime(l.latest_at, ?), ' ', 'T')"
            params.append(f"-{history_days} days")
        query += " ORDER BY tm.timestamp, tm.id"
        rows = [dict(row) for row in conn.execute(query, params)]
    return plants, aggregates, rows


def _totals(scopes, left, right):
    """Use station meters or matched aggregate meters, never mix the two scopes."""
    station = scopes.get(None, {})
    groups = (
        [station]
        if left in station or right in station
        else [group for group in scopes.values() if left in group or right in group]
    )
    present_left = [g.get(left) for g in groups if left in g]
    present_right = [g.get(right) for g in groups if right in g]
    a = sum(present_left) if present_left and all(v is not None for v in present_left) else None
    b = sum(present_right) if present_right and all(v is not None for v in present_right) else None
    matched = bool(groups) and all(
        (
            g.get(left) is not None
            and g.get(right) is not None
            and ((g[left] > 0 and g[right] > 0) or (g[left] == 0 and g[right] == 0))
        )
        for g in groups
    )
    return a, b, a / b if matched and a is not None and a > 0 and b else None


def _points(rows, aggregate_id=None):
    daily = defaultdict(lambda: defaultdict(dict))
    instant = defaultdict(lambda: defaultdict(dict))
    daily_at = {}
    has_interval = any(row["metric"] == "flow_rate" for row in rows)
    for row in rows:
        stamp, scope, metric = row["timestamp"], row["aggregate_id"], row["metric"]
        value = (
            _nonnegative(row["value"]) if row["quality"] in (None, "", "good", "ready") else None
        )
        if metric in ("q_day", "energy"):
            day = stamp[:10]
            daily[day][scope][metric] = value
            daily_at[day] = max(daily_at.get(day, stamp), stamp)
        else:
            instant[stamp][scope][metric] = value
    points = {}
    for day, scopes in daily.items():
        energy, volume, sec = _totals(scopes, "energy", "q_day")
        stamp = daily_at[day]
        points[stamp] = {
            "timestamp": stamp,
            **dict.fromkeys(FIELDS),
            "volume_m3": volume,
            "energy_kwh": energy,
            "sec_kwh_m3": sec,
            "basis": "daily",
        }
    for stamp, scopes in instant.items():
        point = points.setdefault(
            stamp, {"timestamp": stamp, **dict.fromkeys(FIELDS), "basis": "none"}
        )
        power, flow, sec = _totals(scopes, "power", "flow_rate")
        pressure = scopes.get(aggregate_id, {})
        point.update(
            power_kw=power,
            flow_m3h=flow,
            p_in_mpa=pressure.get("p_in"),
            p_out_mpa=pressure.get("p_out"),
        )
        if any("flow_rate" in metrics for metrics in scopes.values()):
            point.update(basis="interval", sec_kwh_m3=sec)
            p_in, p_out = point["p_in_mpa"], point["p_out_mpa"]
            # Station efficiency needs matched hydraulic boundaries; do not average efficiencies.
            if (
                aggregate_id is not None
                and sec
                and p_in is not None
                and p_out is not None
                and p_out > p_in
            ):
                point["efficiency"] = _nonnegative((p_out - p_in) / (3.6 * sec))
                if point["efficiency"] is not None and point["efficiency"] > 1:
                    point["efficiency"] = None
    for point in points.values():
        point["quality"] = "ready" if point["sec_kwh_m3"] is not None else "partial"
        point["snapshot_timestamp"] = None
    bases = {point["basis"] for point in points.values()} - {"none"}
    basis = "mixed" if len(bases) > 1 else next(iter(bases), "none")
    return points, basis, has_interval


def _gap_points(points, start, end, interval):
    stamp = datetime.combine(start, time.min)
    finish = datetime.combine(end + timedelta(days=1), time.min)
    step = timedelta(hours=2) if interval else timedelta(days=1)
    anchors = [key for key, point in points.items() if point["basis"] == "interval"]
    if interval and anchors:
        anchor = datetime.fromisoformat(min(anchors))
        midnight = anchor.replace(hour=0, minute=0, second=0, microsecond=0)
        stamp += (anchor - midnight) % step
    observed_days = {stamp[:10] for stamp in points}
    while stamp < finish:
        key = stamp.isoformat()
        if key not in points and (interval or key[:10] not in observed_days):
            points[key] = {
                "timestamp": key,
                **dict.fromkeys(FIELDS),
                "basis": "none",
                "quality": "missing",
                "snapshot_timestamp": None,
            }
        stamp += step
    return sorted(points.values(), key=lambda point: point["timestamp"])


def _add_reference_points(database, aggregate_id, points, snapshots):
    """Ориентиры по парным давлениям и паспорту, действовавшему в момент измерения."""
    if not snapshots:
        return points
    with closing(sqlite3.connect(database.path.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        passports = [
            dict(row)
            for row in conn.execute(
                "SELECT * FROM aggregate_passports WHERE aggregate_id = ? ORDER BY valid_from DESC",
                (aggregate_id,),
            )
        ]
    mapped = {point["timestamp"]: point for point in points}
    for snapshot in snapshots:
        stamp = snapshot.timestamp.isoformat()
        passport = next(
            (
                p
                for p in passports
                if p["valid_from"] <= stamp and (p["valid_to"] is None or stamp <= p["valid_to"])
            ),
            None,
        )
        if passport is None:
            continue
        factors = [
            passport["motor_eta_nom"],
            passport["pump_eta_nom"],
            passport["transmission_eff"],
            ETA_VFD_DEFAULT if passport["vfd"] else 1.0,
        ]
        if any(
            value is None or not math.isfinite(value) or not 0 < value <= 1 for value in factors
        ):
            continue
        eta = math.prod(factors)
        point = mapped.setdefault(
            stamp,
            {
                "timestamp": stamp,
                **dict.fromkeys(FIELDS),
                "basis": "none",
                "quality": "partial",
                "snapshot_timestamp": stamp,
            },
        )
        point["nominal_efficiency"] = eta
        point["sec_calc_kwh_m3"] = sec_calc(snapshot.p_out_mpa, snapshot.p_in_mpa, eta)
        if (
            snapshot.p_bg_mpa is not None
            and snapshot.p_in_mpa <= snapshot.p_bg_mpa <= snapshot.p_out_mpa
        ):
            point["sec_optimal_kwh_m3"] = sec_optimal(snapshot.p_bg_mpa, snapshot.p_in_mpa, eta)
    return sorted(mapped.values(), key=lambda point: point["timestamp"])


def _comparison(points):
    latest = points[-1] if points else None
    if not latest or latest["sec_kwh_m3"] is None:
        return None
    previous = next(
        (
            point
            for point in reversed(points[:-1])
            if point["basis"] == latest["basis"] and point["sec_kwh_m3"] is not None
        ),
        None,
    )
    return (
        ((latest["sec_kwh_m3"] / previous["sec_kwh_m3"] - 1) * 100)
        if previous and previous["sec_kwh_m3"] > 0
        else None
    )


def monitoring_objects(
    database: AuditDatabase, *, now=None, history_days=30, history_end=None
) -> dict:
    now = now or datetime.now(UTC)
    plants, _, rows = _load(database, history_days=history_days)
    by_object = defaultdict(list)
    for row in rows:
        by_object[row["object_id"]].append(row)
    history_by_object = defaultdict(list)
    if history_end is not None:
        if history_end == date.max:
            raise ValueError("Конец периода выходит за допустимый диапазон.")
        history_start = date.fromordinal(max(1, history_end.toordinal() - history_days + 1))
        _, _, history_rows = _load(database, start=history_start, end=history_end)
        for row in history_rows:
            history_by_object[row["object_id"]].append(row)
    objects = []
    for plant in plants:
        object_rows = by_object[plant["code"]]
        mapped, basis, _ = _points(object_rows)
        points = sorted(mapped.values(), key=lambda point: point["timestamp"])
        comparable = [p for p in points if p["sec_kwh_m3"] is not None]
        latest = comparable[-1] if comparable else None
        latest_at = object_rows[-1]["timestamp"] if object_rows else None
        change = _comparison(comparable)
        kpi_points = {p["timestamp"]: p for p in points if p["basis"] != "none"}
        period_start = date.fromisoformat(points[0]["timestamp"][:10]) if points else None
        period_end = date.fromisoformat(latest_at[:10]) if latest_at else None
        history_basis = basis
        if history_end is not None:
            historic, history_basis, _ = _points(history_by_object[plant["code"]])
            kpi_points = {stamp: p for stamp, p in historic.items() if p["basis"] != "none"}
            period_start, period_end = history_start, history_end
        history = (
            _gap_points(
                kpi_points,
                period_start,
                period_end,
                history_basis in ("interval", "mixed"),
            )
            if period_start is not None
            else []
        )
        status = "unknown" if change is None else "attention" if change > 10 else "normal"
        age = None
        if latest_at:
            measured = datetime.fromisoformat(latest_at)
            measured = (
                measured.replace(tzinfo=ZoneInfo("Europe/Moscow"))
                if measured.tzinfo is None
                else measured
            )
            age = (now.astimezone(UTC) - measured).total_seconds() / 3600
        # shortcut: freshness tolerates one missed delivery; tune with the actual telemetry SLA.
        tolerance = 48 if latest and latest["basis"] == "daily" else 4
        objects.append({
            **plant,
            "status": status,
            "data_status": "missing" if age is None else "stale" if age > tolerance else "fresh",
            "latest_at": latest_at,
            "basis": latest["basis"] if latest else "none",
            "sec_kwh_m3": latest["sec_kwh_m3"] if latest else None,
            "efficiency": latest["efficiency"] if latest else None,
            "change_pct": change,
            "kpi_at": latest["timestamp"] if latest else None,
            "history": [{"timestamp": p["timestamp"], "value": p["sec_kwh_m3"]} for p in history],
            "note": ("Сравнение с предыдущей точкой той же базы; изменение режима не исключено.")
            if change is not None
            else "Недостаточно сопоставимых данных для оценки изменения.",
        })
    objects.sort(
        key=lambda item: ({"attention": 0, "unknown": 1, "normal": 2}[item["status"]], item["name"])
    )
    return {"generated_at": now.isoformat(), "interval_hours": 2, "objects": objects}


def object_timeline(
    database: AuditDatabase,
    object_id: str,
    aggregate_id: str | None = None,
    start: date | None = None,
    end: date | None = None,
) -> dict:
    plants, aggregates, rows = _load(database, object_id, aggregate_code=aggregate_id)
    if object_id not in {plant["code"] for plant in plants}:
        raise KeyError(object_id)
    object_aggregates = [a for a in aggregates if a["object_id"] == object_id]
    selected = next((a for a in object_aggregates if a["code"] == aggregate_id), None)
    if aggregate_id is not None and selected is None:
        raise KeyError(f"{object_id}/{aggregate_id}")
    if selected:
        rows = [row for row in rows if row["aggregate_id"] == selected["id"]]
    latest_at = rows[-1]["timestamp"] if rows else None
    end = end or (date.fromisoformat(latest_at[:10]) if latest_at else date.today())
    start = start or date.fromordinal(max(1, end.toordinal() - 29))
    if end < start or (end - start).days > 366 or end == date.max:
        raise ValueError("Период должен быть от 1 до 367 дней, конец не раньше начала.")
    # Explicit historical windows must query their own rows, not the latest portfolio window.
    _, _, period_rows = _load(database, object_id, start, end)
    if selected:
        period_rows = [row for row in period_rows if row["aggregate_id"] == selected["id"]]
    mapped, basis, interval = _points(period_rows, selected["id"] if selected else None)
    points = _gap_points(mapped, start, end, interval)
    observed = [point for point in points if point["quality"] != "missing"]
    if selected:
        snapshots = telemetry_snapshots(
            database,
            object_id,
            aggregate_id,
            datetime.combine(start, time.min),
            datetime.combine(end + timedelta(days=1), time.min),
        )
        snapshots_at = {snapshot.timestamp.isoformat() for snapshot in snapshots}
        last_snapshot_by_day = {stamp[:10]: stamp for stamp in sorted(snapshots_at)}
        for point in points:
            stamp = point["timestamp"]
            if point["quality"] == "missing":
                continue
            if point["basis"] == "daily":
                point["snapshot_timestamp"] = last_snapshot_by_day.get(stamp[:10])
            elif stamp in snapshots_at:
                point["snapshot_timestamp"] = stamp
        points = _add_reference_points(database, selected["id"], points, snapshots)
    change = _comparison(observed)
    observations = []
    if change is not None:
        observations.append({
            "title": f"Изменение УРЭ: {change:+.1f}%",
            "tone": "warn" if change > 10 else "neutral",
            "detail": (
                "Сравнение с предыдущей точкой той же базы. Проверьте расход, давления "
                "и состав работающих агрегатов; причина не установлена."
            ),
        })
    if any(point["quality"] == "missing" for point in points):
        observations.append({
            "title": "Есть пропуски измерений",
            "tone": "warn",
            "detail": "Пропуски показаны разрывами; значения не интерполируются.",
        })
    notes = [
        "Суточные УРЭ = энергия / объём за сутки. Мгновенный КПД из них не рассчитывается.",
        (
            "Интервальные УРЭ = синхронные мощность / расход. "
            "КПД агрегата — по синхронным давлениям, расходу и мощности."
        ),
        "Станционный УРЭ — отношение сопоставимых сумм; станционный КПД не усредняется.",
        "Показаны измерения основного технического места.",
        (
            "Расчётный УРЭ = (p_вых − p_вх)/(3,6 × паспортный КПД); "
            "оптимальный по БГ = (p_БГ − p_вх)/(3,6 × паспортный КПД). "
            "Ориентиры используют парные давления и паспорт на момент измерения, "
            "а не постоянную норму или оценку фактической экономии."
        ),
        (
            "Суточный факт УРЭ и ориентиры по отдельным замерам давления имеют разную "
            "временную базу; их разность не является суточной оценкой потерь."
        ),
        (
            "Для оценки свежести время без offset принято Europe/Moscow; "
            "часовой пояс нужно подтвердить при подключении новой телеметрии."
        ),
    ]
    return {
        "object_id": object_id,
        "aggregate_id": aggregate_id,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "interval_hours": 2,
        "basis": basis,
        "latest_at": latest_at,
        "points": points,
        "observations": observations,
        "aggregates": [{"code": a["code"], "role": a["role"]} for a in object_aggregates],
        "notes": notes,
    }
