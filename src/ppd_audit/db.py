"""Постоянное SQLite-хранилище объектов ППД, паспортов и телеметрии."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


_UNITS = {
    "p_in": "МПа",
    "p_out": "МПа",
    "p_bg": "МПа",
    "power": "кВт",
    "energy": "кВт·ч",
    "q_day": "м³/сут",
    "flow_rate": "м³/ч",
    "runtime": "ч",
    "density": "кг/м³",
    "viscosity": "сСт",
    "level": "мм",
    "pump_state": "",
}

_SCHEMA_V1 = """
CREATE TABLE ngdu (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE plants (
    id INTEGER PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    ngdu_id INTEGER NOT NULL REFERENCES ngdu(id),
    water_type TEXT NOT NULL CHECK (water_type IN ('пресная', 'агрессивная', 'пластовая')),
    branch TEXT NOT NULL CHECK (branch IN ('кнс', 'перекачка')),
    is_example INTEGER NOT NULL DEFAULT 0 CHECK (is_example IN (0, 1))
);

CREATE TABLE technical_places (
    id INTEGER PRIMARY KEY,
    plant_id INTEGER NOT NULL REFERENCES plants(id),
    code TEXT NOT NULL,
    name TEXT NOT NULL,
    UNIQUE (plant_id, code)
);

CREATE TABLE aggregates (
    id INTEGER PRIMARY KEY,
    technical_place_id INTEGER NOT NULL REFERENCES technical_places(id),
    code TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'работа',
    UNIQUE (technical_place_id, code)
);

CREATE TABLE aggregate_passports (
    id INTEGER PRIMARY KEY,
    aggregate_id INTEGER NOT NULL REFERENCES aggregates(id),
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    pump_model TEXT NOT NULL,
    pump_kind TEXT NOT NULL CHECK (pump_kind IN ('центробежный', 'объёмный')),
    pump_q_nom REAL,
    pump_h_nom REAL,
    pump_eta_nom REAL,
    pump_power_nom REAL,
    pump_n_rpm REAL,
    pump_curve_qh_json TEXT NOT NULL DEFAULT '[]',
    pump_curve_qeta_json TEXT NOT NULL DEFAULT '[]',
    motor_model TEXT NOT NULL,
    motor_synchronous INTEGER NOT NULL DEFAULT 0 CHECK (motor_synchronous IN (0, 1)),
    motor_p_nom REAL,
    motor_eta_nom REAL,
    motor_cos_phi REAL,
    motor_voltage_kv REAL,
    motor_i_nom REAL,
    motor_n_rpm REAL,
    transmission_eff REAL NOT NULL DEFAULT 1.0,
    vfd INTEGER NOT NULL DEFAULT 0 CHECK (vfd IN (0, 1)),
    UNIQUE (aggregate_id, valid_from)
);

CREATE TABLE telemetry_measurements (
    id INTEGER PRIMARY KEY,
    plant_id INTEGER NOT NULL REFERENCES plants(id),
    technical_place_id INTEGER REFERENCES technical_places(id),
    aggregate_id INTEGER REFERENCES aggregates(id),
    timestamp TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT NOT NULL,
    quality TEXT
);

CREATE INDEX ix_telemetry_measurements_aggregate_metric_timestamp
    ON telemetry_measurements (aggregate_id, metric, timestamp);
CREATE INDEX ix_telemetry_measurements_plant_metric_timestamp
    ON telemetry_measurements (plant_id, metric, timestamp);
"""

_SCHEMA_V2 = """
CREATE UNIQUE INDEX ux_telemetry_measurements_scope_timestamp_metric
    ON telemetry_measurements (
        plant_id,
        COALESCE(technical_place_id, -1),
        COALESCE(aggregate_id, -1),
        timestamp,
        metric
    );
"""

_SCHEMA_V3 = """
ALTER TABLE plants ADD COLUMN default_density REAL;
ALTER TABLE plants ADD COLUMN default_viscosity REAL;
"""

_SCHEMA_V4 = """
UPDATE plants
SET name = CASE code
    WHEN 'kns10bn' THEN 'КНС-10'
    WHEN 'kns129ln' THEN 'КНС-129'
    WHEN 'kns138ln' THEN 'КНС-138'
    WHEN 'kns13ln' THEN 'КНС-13'
    WHEN 'kns14an' THEN 'КНС-14'
    WHEN 'kns154bn' THEN 'КНС-154'
    WHEN 'kns155bn' THEN 'КНС-155'
    WHEN 'kns155tbn' THEN 'КНС-155т'
    WHEN 'kns85en' THEN 'КНС-85'
    WHEN 'kns97pren' THEN 'КНС-97/2'
    ELSE name
END;
"""

_SCHEMA_V6 = """
UPDATE plants SET is_active = 1 WHERE code = 'kns10bn';
UPDATE aggregates
SET code = 'НА-2 ПР'
WHERE id IN (
    SELECT a.id FROM aggregates a
    JOIN technical_places tp ON tp.id = a.technical_place_id
    JOIN plants p ON p.id = tp.plant_id
    WHERE p.code = 'kns97pren' AND tp.code = 'main' AND a.code = 'НА-02'
);
UPDATE aggregates
SET code = 'НА-3'
WHERE id IN (
    SELECT a.id FROM aggregates a
    JOIN technical_places tp ON tp.id = a.technical_place_id
    JOIN plants p ON p.id = tp.plant_id
    WHERE p.code = 'kns97pren' AND tp.code = 'kns97-en' AND a.code = 'НА-03'
);
UPDATE telemetry_measurements
SET technical_place_id = (
    SELECT main.id FROM technical_places main
    JOIN plants p ON p.id = main.plant_id
    WHERE p.code = 'kns97pren' AND main.code = 'main'
)
WHERE technical_place_id IN (
    SELECT en.id FROM technical_places en
    JOIN plants p ON p.id = en.plant_id
    WHERE p.code = 'kns97pren' AND en.code = 'kns97-en'
);
UPDATE aggregates
SET technical_place_id = (
    SELECT main.id FROM technical_places main
    JOIN plants p ON p.id = main.plant_id
    WHERE p.code = 'kns97pren' AND main.code = 'main'
)
WHERE technical_place_id IN (
    SELECT en.id FROM technical_places en
    JOIN plants p ON p.id = en.plant_id
    WHERE p.code = 'kns97pren' AND en.code = 'kns97-en'
);
DELETE FROM technical_places
WHERE code = 'kns97-en' AND plant_id = (SELECT id FROM plants WHERE code = 'kns97pren');
"""

_SCHEMA_V7 = """
CREATE TABLE IF NOT EXISTS parameter_clarifications (
    id INTEGER PRIMARY KEY,
    aggregate_id INTEGER NOT NULL REFERENCES aggregates(id),
    field TEXT NOT NULL,
    provisional_value TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
    UNIQUE (aggregate_id, field)
);

CREATE INDEX IF NOT EXISTS ix_parameter_clarifications_aggregate
    ON parameter_clarifications (aggregate_id, status);
"""

_SCHEMA_V9 = """
ALTER TABLE telemetry_measurements ADD COLUMN source_kind TEXT;
ALTER TABLE telemetry_measurements ADD COLUMN source_file TEXT;
ALTER TABLE telemetry_measurements ADD COLUMN source_sheet TEXT;
ALTER TABLE telemetry_measurements ADD COLUMN source_row INTEGER;
ALTER TABLE telemetry_measurements ADD COLUMN source_tag TEXT;
ALTER TABLE telemetry_measurements ADD COLUMN source_label TEXT;
"""


@dataclass(frozen=True)
class TelemetryMeasurement:
    plant_code: str
    aggregate_code: str | None
    timestamp: datetime
    metric: str
    value: float
    unit: str
    quality: str | None = None
    technical_place_code: str = "main"
    source_kind: str | None = None
    source_file: str | None = None
    source_sheet: str | None = None
    source_row: int | None = None
    source_tag: str | None = None
    source_label: str | None = None


DATABASE_PATH_ENV = "PPD_DATABASE_PATH"


def default_database_path() -> Path:
    from .config import project_root

    override = os.getenv(DATABASE_PATH_ENV)
    if override:
        return Path(override)
    return project_root() / "telemetry.sqlite"


def telemetry_units() -> dict[str, str]:
    """Допустимые metric и их canonical units для ручного ввода."""
    return dict(_UNITS)


class AuditDatabase:
    """SQLite repository. БД хранит только canonical telemetry и паспорта."""

    def __init__(self, path: Path | str):
        self.path = Path(path)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def migrate(self) -> None:
        with self._connection() as connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version < 1:
                connection.executescript(_SCHEMA_V1)
                connection.execute("PRAGMA user_version = 1")
            if version < 2:
                connection.executescript(_SCHEMA_V2)
                connection.execute("PRAGMA user_version = 2")
            if version < 3:
                connection.executescript(_SCHEMA_V3)
                connection.execute("PRAGMA user_version = 3")
            if version < 4:
                connection.executescript(_SCHEMA_V4)
                connection.execute("PRAGMA user_version = 4")
            if version < 5:
                columns = {row[1] for row in connection.execute("PRAGMA table_info(plants)")}
                if "is_active" not in columns:
                    connection.execute(
                        "ALTER TABLE plants ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1 "
                        "CHECK (is_active IN (0, 1))"
                    )
                connection.execute("UPDATE plants SET name = 'КНС-97' WHERE code = 'kns97pren'")
                connection.execute("UPDATE plants SET is_active = 0 WHERE code = 'kns10bn'")
                connection.execute("PRAGMA user_version = 5")
            if version < 6:
                connection.executescript(_SCHEMA_V6)
                connection.execute("PRAGMA user_version = 6")
            if version < 7:
                connection.executescript(_SCHEMA_V7)
                connection.execute("PRAGMA user_version = 7")
            if version < 8:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(aggregate_passports)")
                }
                if "transmission_model" not in columns:
                    connection.execute(
                        "ALTER TABLE aggregate_passports ADD COLUMN transmission_model TEXT"
                    )
                if "transmission_ratio" not in columns:
                    connection.execute(
                        "ALTER TABLE aggregate_passports ADD COLUMN transmission_ratio REAL"
                    )
                connection.execute("PRAGMA user_version = 8")
            if version < 9:
                connection.executescript(_SCHEMA_V9)
                connection.execute("PRAGMA user_version = 9")

    def upsert_ngdu(self, name: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO ngdu(name) VALUES (?) ON CONFLICT(name) DO NOTHING", (name,)
            )

    def upsert_plant(
        self,
        code: str,
        name: str,
        ngdu_name: str,
        water_type: str,
        branch: str,
        *,
        is_example: bool = False,
        default_density: float | None = None,
        default_viscosity: float | None = None,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO ngdu(name) VALUES (?) ON CONFLICT(name) DO NOTHING", (ngdu_name,)
            )
            ngdu_id = self._id(connection, "SELECT id FROM ngdu WHERE name = ?", ngdu_name)
            connection.execute(
                """
                INSERT INTO plants(
                    code, name, ngdu_id, water_type, branch, is_example, default_density,
                    default_viscosity
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(code) DO UPDATE SET
                    name = excluded.name,
                    ngdu_id = excluded.ngdu_id,
                    water_type = excluded.water_type,
                    branch = excluded.branch,
                    is_example = excluded.is_example,
                    default_density = excluded.default_density,
                    default_viscosity = excluded.default_viscosity
                """,
                (
                    code,
                    name,
                    ngdu_id,
                    water_type,
                    branch,
                    int(is_example),
                    default_density,
                    default_viscosity,
                ),
            )
            plant_id = self._id(connection, "SELECT id FROM plants WHERE code = ?", code)
            connection.execute(
                """
                INSERT INTO technical_places(plant_id, code, name) VALUES (?, 'main', ?)
                ON CONFLICT(plant_id, code) DO UPDATE SET name = excluded.name
                """,
                (plant_id, name),
            )

    def upsert_technical_place(self, plant_code: str, code: str, name: str) -> None:
        with self._connection() as connection:
            plant_id = self._id(connection, "SELECT id FROM plants WHERE code = ?", plant_code)
            connection.execute(
                """
                INSERT INTO technical_places(plant_id, code, name) VALUES (?, ?, ?)
                ON CONFLICT(plant_id, code) DO UPDATE SET name = excluded.name
                """,
                (plant_id, code, name),
            )

    def upsert_aggregate(
        self,
        plant_code: str,
        code: str,
        role: str,
        *,
        technical_place_code: str = "main",
    ) -> None:
        with self._connection() as connection:
            place_id = self._technical_place_id(connection, plant_code, technical_place_code)
            connection.execute(
                """
                INSERT INTO aggregates(technical_place_id, code, role) VALUES (?, ?, ?)
                ON CONFLICT(technical_place_id, code) DO UPDATE SET role = excluded.role
                """,
                (place_id, code, role),
            )

    def add_passport(
        self,
        plant_code: str,
        aggregate_code: str,
        *,
        valid_from: datetime,
        pump_model: str,
        pump_kind: str,
        pump_q_nom: float | None,
        pump_h_nom: float | None,
        pump_eta_nom: float | None,
        motor_model: str,
        motor_p_nom: float | None,
        motor_eta_nom: float | None,
        technical_place_code: str = "main",
        **extra: Any,
    ) -> None:
        with self._connection() as connection:
            aggregate_id = self._aggregate_id(
                connection, plant_code, aggregate_code, technical_place_code
            )
            fields = {
                "pump_power_nom": extra.get("pump_power_nom"),
                "pump_n_rpm": extra.get("pump_n_rpm"),
                "pump_curve_qh_json": extra.get("pump_curve_qh_json", "[]"),
                "pump_curve_qeta_json": extra.get("pump_curve_qeta_json", "[]"),
                "motor_synchronous": int(extra.get("motor_synchronous", False)),
                "motor_cos_phi": extra.get("motor_cos_phi"),
                "motor_voltage_kv": extra.get("motor_voltage_kv"),
                "motor_i_nom": extra.get("motor_i_nom"),
                "motor_n_rpm": extra.get("motor_n_rpm"),
                "transmission_model": extra.get("transmission_model"),
                "transmission_ratio": extra.get("transmission_ratio"),
                "transmission_eff": extra.get("transmission_eff", 1.0),
                "vfd": int(extra.get("vfd", False)),
                "valid_to": self._iso(extra.get("valid_to")),
            }
            connection.execute(
                """
                INSERT INTO aggregate_passports(
                    aggregate_id, valid_from, valid_to, pump_model, pump_kind, pump_q_nom,
                    pump_h_nom, pump_eta_nom, pump_power_nom, pump_n_rpm, pump_curve_qh_json,
                    pump_curve_qeta_json, motor_model, motor_synchronous, motor_p_nom,
                    motor_eta_nom, motor_cos_phi, motor_voltage_kv, motor_i_nom, motor_n_rpm,
                    transmission_model, transmission_ratio, transmission_eff, vfd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(aggregate_id, valid_from) DO UPDATE SET
                    valid_to = excluded.valid_to,
                    pump_model = excluded.pump_model,
                    pump_kind = excluded.pump_kind,
                    pump_q_nom = excluded.pump_q_nom,
                    pump_h_nom = excluded.pump_h_nom,
                    pump_eta_nom = excluded.pump_eta_nom,
                    pump_power_nom = excluded.pump_power_nom,
                    pump_n_rpm = excluded.pump_n_rpm,
                    pump_curve_qh_json = excluded.pump_curve_qh_json,
                    pump_curve_qeta_json = excluded.pump_curve_qeta_json,
                    motor_model = excluded.motor_model,
                    motor_synchronous = excluded.motor_synchronous,
                    motor_p_nom = excluded.motor_p_nom,
                    motor_eta_nom = excluded.motor_eta_nom,
                    motor_cos_phi = excluded.motor_cos_phi,
                    motor_voltage_kv = excluded.motor_voltage_kv,
                    motor_i_nom = excluded.motor_i_nom,
                    motor_n_rpm = excluded.motor_n_rpm,
                    transmission_model = excluded.transmission_model,
                    transmission_ratio = excluded.transmission_ratio,
                    transmission_eff = excluded.transmission_eff,
                    vfd = excluded.vfd
                """,
                (
                    aggregate_id,
                    self._iso(valid_from),
                    fields["valid_to"],
                    pump_model,
                    pump_kind,
                    pump_q_nom,
                    pump_h_nom,
                    pump_eta_nom,
                    fields["pump_power_nom"],
                    fields["pump_n_rpm"],
                    fields["pump_curve_qh_json"],
                    fields["pump_curve_qeta_json"],
                    motor_model,
                    fields["motor_synchronous"],
                    motor_p_nom,
                    motor_eta_nom,
                    fields["motor_cos_phi"],
                    fields["motor_voltage_kv"],
                    fields["motor_i_nom"],
                    fields["motor_n_rpm"],
                    fields["transmission_model"],
                    fields["transmission_ratio"],
                    fields["transmission_eff"],
                    fields["vfd"],
                ),
            )

    def add_measurement(
        self,
        plant_code: str,
        aggregate_code: str | None,
        timestamp: datetime,
        metric: str,
        value: float,
        unit: str,
        *,
        quality: str | None = None,
        technical_place_code: str = "main",
        source_kind: str | None = None,
        source_file: str | None = None,
        source_sheet: str | None = None,
        source_row: int | None = None,
        source_tag: str | None = None,
        source_label: str | None = None,
    ) -> None:
        self.add_measurements(
            [
                TelemetryMeasurement(
                    plant_code=plant_code,
                    aggregate_code=aggregate_code,
                    timestamp=timestamp,
                    metric=metric,
                    value=value,
                    unit=unit,
                    quality=quality,
                    technical_place_code=technical_place_code,
                    source_kind=source_kind,
                    source_file=source_file,
                    source_sheet=source_sheet,
                    source_row=source_row,
                    source_tag=source_tag,
                    source_label=source_label,
                )
            ]
        )

    def add_measurements(self, measurements: Iterator[TelemetryMeasurement]) -> int:
        """Идемпотентно записать canonical telemetry пачкой."""
        stored = 0
        with self._connection() as connection:
            ids: dict[tuple[str, str, str | None], tuple[int, int, int | None]] = {}
            rows = []
            for measurement in measurements:
                expected_unit = _UNITS.get(measurement.metric)
                if expected_unit is None:
                    raise ValueError(f"неподдерживаемая telemetry metric: {measurement.metric}")
                if measurement.unit != expected_unit:
                    raise ValueError(
                        f"для {measurement.metric} нужна единица {expected_unit}, "
                        f"получена {measurement.unit}"
                    )
                key = (
                    measurement.plant_code,
                    measurement.technical_place_code,
                    measurement.aggregate_code,
                )
                if key not in ids:
                    plant_id = self._id(
                        connection, "SELECT id FROM plants WHERE code = ?", measurement.plant_code
                    )
                    place_id = self._technical_place_id(
                        connection, measurement.plant_code, measurement.technical_place_code
                    )
                    aggregate_id = (
                        self._aggregate_id(
                            connection,
                            measurement.plant_code,
                            measurement.aggregate_code,
                            measurement.technical_place_code,
                        )
                        if measurement.aggregate_code
                        else None
                    )
                    ids[key] = (plant_id, place_id, aggregate_id)
                rows.append(
                    (
                        *ids[key],
                        self._iso(measurement.timestamp),
                        measurement.metric,
                        measurement.value,
                        measurement.unit,
                        measurement.quality,
                        measurement.source_kind,
                        measurement.source_file,
                        measurement.source_sheet,
                        measurement.source_row,
                        measurement.source_tag,
                        measurement.source_label,
                    )
                )
            connection.executemany(
                """
                INSERT INTO telemetry_measurements(
                    plant_id, technical_place_id, aggregate_id, timestamp, metric, value,
                    unit, quality, source_kind, source_file, source_sheet, source_row,
                    source_tag, source_label
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT DO UPDATE SET value = excluded.value, unit = excluded.unit,
                    quality = excluded.quality, source_kind = excluded.source_kind,
                    source_file = excluded.source_file, source_sheet = excluded.source_sheet,
                    source_row = excluded.source_row, source_tag = excluded.source_tag,
                    source_label = excluded.source_label
                """,
                rows,
            )
            stored = len(rows)
        return stored

    def measurements(
        self,
        plant_code: str,
        aggregate_code: str | None = None,
        *,
        technical_place_code: str = "main",
    ) -> list[dict[str, Any]]:
        with self._connection() as connection:
            query = """
                SELECT tm.timestamp, tm.metric, tm.value, tm.unit, tm.quality,
                       tm.source_kind, tm.source_file, tm.source_sheet, tm.source_row,
                       tm.source_tag, tm.source_label,
                       ngdu.name AS ngdu_name
                FROM telemetry_measurements tm
                JOIN plants p ON p.id = tm.plant_id
                JOIN ngdu ON ngdu.id = p.ngdu_id
                WHERE p.code = ?
            """
            params: list[str] = [plant_code]
            if aggregate_code:
                query += " AND tm.aggregate_id = ?"
                params.append(
                    str(
                        self._aggregate_id(
                            connection, plant_code, aggregate_code, technical_place_code
                        )
                    )
                )
            query += " ORDER BY tm.timestamp, tm.id"
            return [dict(row) for row in connection.execute(query, params)]

    def annual_runtime(
        self,
        plant_code: str,
        aggregate_code: str,
        end: datetime,
        *,
        technical_place_code: str = "main",
    ) -> float | None:
        """Суммировать 365 непрерывных суток наработки до конца окна."""
        start = end - timedelta(days=365)
        with self._connection() as connection:
            aggregate_id = self._aggregate_id(
                connection, plant_code, aggregate_code, technical_place_code
            )
            rows = list(
                connection.execute(
                    """
                    SELECT DATE(timestamp) AS day, SUM(value) AS runtime
                    FROM telemetry_measurements
                    WHERE aggregate_id = ? AND metric = 'runtime'
                      AND timestamp >= ? AND timestamp < ?
                    GROUP BY DATE(timestamp)
                    ORDER BY day
                    """,
                    (aggregate_id, self._iso(start), self._iso(end)),
                )
            )
        expected_days = {start.date() + timedelta(days=offset) for offset in range(365)}
        if len(rows) != 365 or {date.fromisoformat(row["day"]) for row in rows} != expected_days:
            return None
        return sum(float(row["runtime"]) for row in rows)

    def measurements_in_window(
        self,
        plant_code: str,
        aggregate_code: str,
        start: datetime,
        end: datetime,
        *,
        technical_place_code: str = "main",
        include_station: bool = False,
    ) -> list[dict[str, Any]]:
        """Измерения агрегата за полуоткрытый интервал [start, end)."""
        with self._connection() as connection:
            aggregate_id = self._aggregate_id(
                connection, plant_code, aggregate_code, technical_place_code
            )
            query = """
                SELECT tm.timestamp, tm.metric, tm.value, tm.unit, tm.quality,
                       tm.source_kind, tm.source_file, tm.source_sheet, tm.source_row,
                       tm.source_tag, tm.source_label,
                       tm.aggregate_id IS NULL AS is_station
                FROM telemetry_measurements tm
                JOIN plants p ON p.id = tm.plant_id
                WHERE p.code = ? AND tm.timestamp >= ? AND tm.timestamp < ?
                  AND (tm.aggregate_id = ?
            """
            params: list[str | int] = [
                plant_code,
                self._iso(start),
                self._iso(end),
                aggregate_id,
            ]
            if include_station:
                query += " OR tm.aggregate_id IS NULL"
            query += ") ORDER BY tm.timestamp, tm.id"
            return [dict(row) for row in connection.execute(query, params)]

    def state_measurements_in_window(
        self,
        plant_code: str,
        aggregate_code: str,
        start: datetime,
        end: datetime,
        *,
        technical_place_code: str = "main",
        include_end: bool = False,
    ) -> list[dict[str, Any]]:
        """Изменения состояния плюс предыдущее и, при необходимости, конечное значение."""
        with self._connection() as connection:
            aggregate_id = self._aggregate_id(
                connection, plant_code, aggregate_code, technical_place_code
            )
            select = """
                SELECT tm.timestamp, tm.metric, tm.value, tm.unit, tm.quality,
                       tm.source_kind, tm.source_file, tm.source_sheet, tm.source_row,
                       tm.source_tag, tm.source_label,
                       tm.aggregate_id IS NULL AS is_station
                FROM telemetry_measurements tm
                JOIN plants p ON p.id = tm.plant_id
                WHERE p.code = ?
            """
            end_operator = "<=" if include_end else "<"
            in_window = list(
                connection.execute(
                    select
                    + f"""
                        AND tm.timestamp >= ? AND tm.timestamp {end_operator} ?
                        AND (
                            (tm.aggregate_id = ? AND tm.metric IN ('p_in', 'p_out', 'power'))
                            OR (tm.aggregate_id IS NULL AND tm.metric = 'p_bg')
                        )
                        ORDER BY tm.timestamp, tm.id
                    """,
                    (plant_code, self._iso(start), self._iso(end), aggregate_id),
                )
            )
            previous = []
            for aggregate_scope, metric in (
                (True, "p_in"),
                (True, "p_out"),
                (True, "power"),
                (False, "p_bg"),
            ):
                scope = "tm.aggregate_id = ?" if aggregate_scope else "tm.aggregate_id IS NULL"
                params: list[str | int] = [plant_code]
                if aggregate_scope:
                    params.append(aggregate_id)
                params.extend((metric, self._iso(start)))
                row = connection.execute(
                    select
                    + f"""
                        AND {scope} AND tm.metric = ? AND tm.timestamp < ?
                        ORDER BY tm.timestamp DESC, tm.id DESC LIMIT 1
                    """,
                    params,
                ).fetchone()
                if row is not None:
                    previous.append(row)
        rows = sorted([*previous, *in_window], key=lambda row: row["timestamp"])
        return [dict(row) for row in rows]

    def plant(self, plant_code: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT p.code, p.name, p.water_type, p.branch, p.default_density,
                       p.default_viscosity, ngdu.name AS ngdu_name
                FROM plants p JOIN ngdu ON ngdu.id = p.ngdu_id
                WHERE p.code = ?
                """,
                (plant_code,),
            ).fetchone()
            if row is None:
                raise KeyError(plant_code)
            return dict(row)

    def aggregate(self, plant_code: str, aggregate_code: str) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT a.code, a.role
                FROM aggregates a
                JOIN technical_places tp ON tp.id = a.technical_place_id
                JOIN plants p ON p.id = tp.plant_id
                WHERE p.code = ? AND tp.code = 'main' AND a.code = ?
                """,
                (plant_code, aggregate_code),
            ).fetchone()
            if row is None:
                raise KeyError(f"{plant_code}/main/{aggregate_code}")
            return dict(row)

    def aggregates(self, plant_code: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT a.code, a.role
                    FROM aggregates a
                    JOIN technical_places tp ON tp.id = a.technical_place_id
                    JOIN plants p ON p.id = tp.plant_id
                    WHERE p.code = ? AND tp.code = 'main'
                    ORDER BY a.code
                    """,
                    (plant_code,),
                )
            ]

    def has_measurements(self) -> bool:
        with self._connection() as connection:
            row = connection.execute("SELECT 1 FROM telemetry_measurements LIMIT 1").fetchone()
        return row is not None

    def telemetry_source_files(self) -> list[str]:
        with self._connection() as connection:
            return [
                row["source_file"]
                for row in connection.execute(
                    """
                    SELECT DISTINCT source_file
                    FROM telemetry_measurements
                    WHERE source_file IS NOT NULL
                    ORDER BY source_file
                    """
                )
            ]

    def telemetry_dates(self, plant_code: str, aggregate_code: str) -> list[date]:
        with self._connection() as connection:
            aggregate_id = self._aggregate_id(connection, plant_code, aggregate_code, "main")
            return [
                date.fromisoformat(row["day"])
                for row in connection.execute(
                    """
                    SELECT DISTINCT substr(timestamp, 1, 10) AS day
                    FROM telemetry_measurements
                    WHERE aggregate_id = ?
                    ORDER BY day
                    """,
                    (aggregate_id,),
                )
            ]

    def plants(self, *, include_examples: bool = False) -> list[dict[str, Any]]:
        with self._connection() as connection:
            query = """
                SELECT p.code, p.name, ngdu.name AS ngdu_name, p.water_type, p.branch, p.is_example
                FROM plants p JOIN ngdu ON ngdu.id = p.ngdu_id
            """
            conditions = []
            if not include_examples:
                conditions.append("p.is_example = 0")
            if conditions:
                query += f" WHERE {' AND '.join(conditions)}"
            query += " ORDER BY ngdu.name, p.name"
            return [
                {**dict(row), "is_example": bool(row["is_example"])}
                for row in connection.execute(query)
            ]

    def active_passport(
        self,
        plant_code: str,
        aggregate_code: str,
        at: datetime,
        *,
        technical_place_code: str = "main",
    ) -> dict[str, Any]:
        with self._connection() as connection:
            aggregate_id = self._aggregate_id(
                connection, plant_code, aggregate_code, technical_place_code
            )
            row = connection.execute(
                """
                SELECT * FROM aggregate_passports
                WHERE aggregate_id = ? AND valid_from <= ? AND (valid_to IS NULL OR valid_to >= ?)
                ORDER BY valid_from DESC LIMIT 1
                """,
                (aggregate_id, self._iso(at), self._iso(at)),
            ).fetchone()
            if row is None:
                raise KeyError(f"нет действующего паспорта {plant_code}/{aggregate_code}")
            return dict(row)

    def upsert_clarification(
        self,
        plant_code: str,
        aggregate_code: str,
        *,
        field: str,
        provisional_value: str,
        reason: str,
    ) -> None:
        """Зафиксировать временно принятое паспортное значение для уточнения."""
        with self._connection() as connection:
            aggregate_id = self._aggregate_id(connection, plant_code, aggregate_code, "main")
            connection.execute(
                """
                INSERT INTO parameter_clarifications(
                    aggregate_id, field, provisional_value, reason
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(aggregate_id, field) DO UPDATE SET
                    provisional_value = excluded.provisional_value,
                    reason = excluded.reason,
                    status = 'open'
                """,
                (aggregate_id, field, provisional_value, reason),
            )

    def resolve_clarification(self, plant_code: str, aggregate_code: str, *, field: str) -> None:
        """Закрыть уточнение, когда его значение получено из данных."""
        with self._connection() as connection:
            aggregate_id = self._aggregate_id(connection, plant_code, aggregate_code, "main")
            connection.execute(
                """
                UPDATE parameter_clarifications
                SET status = 'resolved'
                WHERE aggregate_id = ? AND field = ?
                """,
                (aggregate_id, field),
            )

    def clarifications(self, plant_code: str, aggregate_code: str) -> list[dict[str, str]]:
        """Вернуть открытые уточнения параметров выбранного агрегата."""
        with self._connection() as connection:
            aggregate_id = self._aggregate_id(connection, plant_code, aggregate_code, "main")
            return [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT field, provisional_value, reason, status
                    FROM parameter_clarifications
                    WHERE aggregate_id = ? AND status = 'open'
                    ORDER BY field
                    """,
                    (aggregate_id,),
                )
            ]

    def open_clarifications(self, plant_code: str | None = None) -> list[dict[str, str]]:
        """Вернуть открытые уточнения, при необходимости — одного объекта."""
        with self._connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT
                        plants.code AS plant_code,
                        plants.name AS plant_name,
                        aggregates.code AS aggregate_code,
                        parameter_clarifications.field,
                        parameter_clarifications.provisional_value,
                        parameter_clarifications.reason
                    FROM parameter_clarifications
                    JOIN aggregates ON aggregates.id = parameter_clarifications.aggregate_id
                    JOIN technical_places ON technical_places.id = aggregates.technical_place_id
                    JOIN plants ON plants.id = technical_places.plant_id
                    WHERE parameter_clarifications.status = 'open'
                      AND (? IS NULL OR plants.code = ?)
                    ORDER BY plants.name, aggregates.code, parameter_clarifications.field
                    """,
                    (plant_code, plant_code),
                )
            ]

    @staticmethod
    def _id(connection: sqlite3.Connection, query: str, value: str) -> int:
        row = connection.execute(query, (value,)).fetchone()
        if row is None:
            raise KeyError(value)
        return int(row[0])

    def _technical_place_id(
        self, connection: sqlite3.Connection, plant_code: str, technical_place_code: str
    ) -> int:
        row = connection.execute(
            """
            SELECT tp.id FROM technical_places tp
            JOIN plants p ON p.id = tp.plant_id
            WHERE p.code = ? AND tp.code = ?
            """,
            (plant_code, technical_place_code),
        ).fetchone()
        if row is None:
            raise KeyError(f"{plant_code}/{technical_place_code}")
        return int(row[0])

    def _aggregate_id(
        self,
        connection: sqlite3.Connection,
        plant_code: str,
        aggregate_code: str,
        technical_place_code: str,
    ) -> int:
        row = connection.execute(
            """
            SELECT a.id FROM aggregates a
            JOIN technical_places tp ON tp.id = a.technical_place_id
            JOIN plants p ON p.id = tp.plant_id
            WHERE p.code = ? AND tp.code = ? AND a.code = ?
            """,
            (plant_code, technical_place_code, aggregate_code),
        ).fetchone()
        if row is None:
            raise KeyError(f"{plant_code}/{technical_place_code}/{aggregate_code}")
        return int(row[0])

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return value.isoformat() if value else None
