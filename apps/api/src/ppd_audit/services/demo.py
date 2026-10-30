"""Изолированный синтетический объект для демонстрации операторского сценария."""

from calendar import monthrange
from datetime import date, datetime, timedelta
from math import pi, sin
from zoneinfo import ZoneInfo

from ..db import AuditDatabase, TelemetryMeasurement


DEMO_OBJECT_ID = "demo-ppd"
_SOURCE = "synthetic://demo-ppd/v1"


def seed_demo(database: AuditDatabase, now: datetime | None = None) -> int:
    """Добавить недостающие 2-часовые отсчёты, не меняя существующие записи."""
    now = now or datetime.now(ZoneInfo("Europe/Moscow"))
    if now.tzinfo is not None:
        now = now.astimezone(ZoneInfo("Europe/Moscow")).replace(tzinfo=None)
    end = now.replace(hour=now.hour // 2 * 2, minute=0, second=0, microsecond=0)
    with database._connection() as connection:
        existing = connection.execute(
            "SELECT id FROM plants WHERE code = ?",
            (DEMO_OBJECT_ID,),
        ).fetchone()
        latest = dict(
            connection.execute(
                """SELECT a.code, MAX(tm.timestamp) FROM telemetry_measurements tm
               JOIN plants p ON p.id = tm.plant_id
               LEFT JOIN aggregates a ON a.id = tm.aggregate_id
               WHERE p.code = ? GROUP BY a.code""",
                (DEMO_OBJECT_ID,),
            ).fetchall()
        )
        passports = {
            row[0]
            for row in connection.execute(
                """SELECT a.code FROM aggregate_passports ap
                   JOIN aggregates a ON a.id = ap.aggregate_id
                   JOIN technical_places tp ON tp.id = a.technical_place_id
                   JOIN plants p ON p.id = tp.plant_id WHERE p.code = ?""",
                (DEMO_OBJECT_ID,),
            )
        }
    starts = {
        code: max(
            end - timedelta(days=90),
            datetime.fromisoformat(latest[code]) + timedelta(hours=2),
        )
        if code in latest
        else end - timedelta(days=90)
        for code in ("НА-1", "НА-2", None)
    }
    if existing is None:
        database.upsert_plant(
            DEMO_OBJECT_ID,
            "Демо · КНС",
            "Демонстрационный объект",
            "пресная",
            "кнс",
            is_example=True,
            default_density=1000,
            default_viscosity=1,
        )
    for code, flow_nom, eta_nom, power_nom in (
        ("НА-1", 120, 0.78, 630),
        ("НА-2", 100, 0.8, 500),
    ):
        database.upsert_aggregate(DEMO_OBJECT_ID, code, "работа")
        if code not in passports:
            database.add_passport(
                DEMO_OBJECT_ID,
                code,
                valid_from=datetime(1970, 1, 1),
                pump_model=f"Демо ЦНС {flow_nom}-1000",
                pump_kind="центробежный",
                pump_q_nom=flow_nom,
                pump_h_nom=1000,
                pump_eta_nom=eta_nom,
                motor_model=f"Демо ЭД {power_nom}",
                motor_p_nom=power_nom,
                motor_eta_nom=0.96,
                motor_cos_phi=0.9,
                motor_voltage_kv=6,
                pump_n_rpm=3000,
                motor_n_rpm=3000,
                transmission_eff=1,
                vfd=True,
            )
    records = []
    at = min(starts.values())
    while at <= end:
        daily = sin(2 * pi * at.hour / 24)
        flow = 120 + 3 * daily
        # shortcut: фиксированный учебный эпизод деградации; менять при сценариях с событиями.
        degradation = min(1, max(0, (at - datetime(2026, 10, 10)).total_seconds() / (8 * 86400)))
        power = flow * (4.5 + 0.7 * degradation)
        second_flow = 100 + 2 * sin(2 * pi * at.hour / 24 + pi / 3)
        values = [
            ("НА-1", "p_in", 0.5, "МПа"),
            ("НА-1", "p_out", 10.5, "МПа"),
            ("НА-1", "flow_rate", flow, "м³/ч"),
            ("НА-1", "power", power, "кВт"),
            ("НА-1", "density", 1000, "кг/м³"),
            ("НА-1", "viscosity", 1, "сСт"),
            ("НА-2", "p_in", 0.5, "МПа"),
            ("НА-2", "p_out", 10.5, "МПа"),
            ("НА-2", "flow_rate", second_flow, "м³/ч"),
            ("НА-2", "power", second_flow * (4.25 + 0.15 * degradation), "кВт"),
            ("НА-2", "density", 1000, "кг/м³"),
            ("НА-2", "viscosity", 1, "сСт"),
            (None, "p_bg", 9.5, "МПа"),
        ]
        records.extend(
            TelemetryMeasurement(
                plant_code=DEMO_OBJECT_ID,
                aggregate_code=aggregate,
                timestamp=at,
                metric=metric,
                value=value,
                unit=unit,
                source_kind="demo",
                source_file=_SOURCE,
                source_label="Синтетическая телеметрия · учебный сценарий",
            )
            for aggregate, metric, value, unit in values
            if at >= starts[aggregate]
        )
        at += timedelta(hours=2)
    _seed_well_history(database, now.date())
    return database.add_measurements(iter(records))


def _seed_well_history(database: AuditDatabase, today: date) -> None:
    wells = database.wells(DEMO_OBJECT_ID)
    if len(wells) == 6 and all((well["current_at"] or "") >= today.isoformat() for well in wells):
        return
    rows = []

    def add(code, at, kind, metrics, study_type=""):
        for index, (metric, value, unit) in enumerate(metrics, start=1):
            rows.append({
                "plant_code": DEMO_OBJECT_ID,
                "well_code": code,
                "observed_at": at.isoformat(),
                "grain": "month" if kind == "monthly_actual" else "day",
                "record_kind": kind,
                "metric": metric,
                "value": round(value, 2),
                "unit": unit,
                "study_type": study_type,
                "source_file": _SOURCE,
                "source_sheet": "Синтетическая история скважин",
                "source_row": index,
                "exported_at": at.isoformat(),
            })

    for number in range(1, 7):
        code = str(number)
        for offset in range(12, 0, -1):
            year, month = divmod(today.year * 12 + today.month - 1 - offset, 12)
            at = date(year, month + 1, 1)
            seasonal = sin(2 * pi * at.month / 12 + number / 3)
            flow = 820 + number * 15 + 35 * seasonal
            add(
                code,
                at,
                "monthly_actual",
                [
                    ("p_well", 72 + number + 3 * seasonal, "атм"),
                    ("p_bg", 96 + 2 * seasonal, "атм"),
                    ("flow_m3_day", flow, "м³/сут"),
                    ("injection_volume_m3", flow * monthrange(year, month + 1)[1], "м³"),
                ],
            )
            if offset in (9, 3):
                add(
                    code,
                    at.replace(day=15),
                    "study",
                    [
                        ("p_reservoir", 115 + number, "атм"),
                        ("p_bottomhole", 155 + number + seasonal, "атм"),
                        ("density_kgm3", 1000, "кг/м³"),
                    ],
                    "КВД",
                )
        add(
            code,
            today,
            "current",
            [
                ("p_well", 72 + number, "атм"),
                ("p_bg", 96, "атм"),
                ("flow_m3_day", 820 + number * 15, "м³/сут"),
            ],
        )
    database.add_well_measurements(rows)


def demo_network() -> dict:
    """Небольшая синтетическая сеть; длины в м, диаметры и стенки в мм."""
    segments = []
    for identifier, origin, target, length in [
        ("main", "Демо · КНС", "Развилка", 1000),
        ("a", "Развилка", "скв. 1", 800),
        ("b", "Развилка", "скв. 2", 1000),
        ("c", "Развилка", "скв. 3", 1200),
        ("d", "Развилка", "скв. 4", 800),
        ("e", "Развилка", "скв. 5", 1000),
        ("f", "Развилка", "скв. 6", 1200),
    ]:
        segments.append({
            "id": identifier,
            "pipeline_id": identifier,
            "pipeline_name": identifier,
            "purpose": "Напорный",
            "from_node": origin,
            "to_node": target,
            "start_m": 0,
            "end_m": length,
            "length_m": length,
            "outer_diameter_mm": 200,
            "wall_thickness_mm": 5,
            "source_sheet": "Синтетическая сеть",
            "source_row": len(segments) + 1,
        })
    return {
        "object_id": DEMO_OBJECT_ID,
        "root_node": "Демо · КНС",
        "is_synthetic": True,
        "source_file": _SOURCE,
        "exported_at": None,
        "warnings": ["Демонстрационная сеть и все её параметры синтетические."],
        "segments": segments,
        "wells": [{"id": str(number)} for number in range(1, 7)],
    }
