"""Постоянное SQLite-хранилище объектов ППД, паспортов и телеметрии."""

from __future__ import annotations

import json
import math
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .measurement_quality import usable_measurement


_UNITS = {
    "p_in": "МПа",
    "p_out": "МПа",
    "p_bg": "МПа",
    "pressure_unassigned": "не подтверждена",
    "power": "кВт",
    "power_daily_reported": "кВт",
    "energy": "кВт·ч",
    "q_day": "м³/сут",
    "flow_rate": "м³/ч",
    "runtime": "ч",
    "density": "кг/м³",
    "viscosity": "сСт",
    "level": "мм",
    "pump_state": "",
}

# Текущая версия схемы: migrate() доводит любую более старую БД до неё.
SCHEMA_VERSION = 21

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

CREATE TABLE equipment_journal (
    id INTEGER PRIMARY KEY,
    aggregate_id INTEGER NOT NULL REFERENCES aggregates(id),
    seq INTEGER NOT NULL,
    component TEXT NOT NULL CHECK (component IN ('pump', 'motor', 'transmission', 'vfd')),
    effective_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (
        reason IN ('repair', 'replacement', 'passport', 'inspection', 'correction')
    ),
    evidence TEXT NOT NULL CHECK (evidence IN ('documented', 'estimate')),
    source TEXT NOT NULL,
    author TEXT NOT NULL,
    comment TEXT NOT NULL,
    changes_json TEXT NOT NULL,
    reset_fields_json TEXT NOT NULL DEFAULT '[]',
    supersedes_id INTEGER REFERENCES equipment_journal(id),
    superseded_by_id INTEGER REFERENCES equipment_journal(id)
);
CREATE UNIQUE INDEX ux_equipment_journal_seq
    ON equipment_journal (aggregate_id, seq);
CREATE UNIQUE INDEX ux_equipment_journal_supersedes
    ON equipment_journal (supersedes_id);
CREATE INDEX ix_equipment_journal_aggregate_effective
    ON equipment_journal (aggregate_id, effective_at);

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


@dataclass(frozen=True)
class TelemetryMeasurement:
    plant_code: str
    aggregate_code: str | None
    timestamp: datetime
    metric: str
    value: float
    unit: str
    quality: str | None = None
    technical_place_code: str | None = None
    source_kind: str | None = None
    source_file: str | None = None
    source_sheet: str | None = None
    source_row: int | None = None
    source_tag: str | None = None
    source_label: str | None = None


class RevisionConflict(RuntimeError):
    """Оптимистическая блокировка паспорта: переданная ревизия устарела."""

    def __init__(self, expected: str, actual: str):
        super().__init__(f"ревизия паспорта изменилась: ожидалась {expected}, актуальная {actual}")
        self.expected = expected
        self.actual = actual


class JournalConflict(RuntimeError):
    """Коллизия журнала оборудования: пересечение значений или недопустимая правка."""


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
    """SQLite repository: canonical telemetry, паспорта и тарифы электроэнергии."""

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
                columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(telemetry_measurements)")
                }
                for column, column_type in (
                    ("source_kind", "TEXT"),
                    ("source_file", "TEXT"),
                    ("source_sheet", "TEXT"),
                    ("source_row", "INTEGER"),
                    ("source_tag", "TEXT"),
                    ("source_label", "TEXT"),
                ):
                    if column not in columns:
                        connection.execute(
                            f"ALTER TABLE telemetry_measurements ADD COLUMN {column} {column_type}"
                        )
                connection.execute("PRAGMA user_version = 9")
            # The other v10 branch added runtimes without tariff tables.
            if version < 11:
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS electricity_tariffs (
                        year INTEGER PRIMARY KEY CHECK (year BETWEEN 1 AND 9999),
                        rub_per_kwh REAL NOT NULL CHECK (
                            rub_per_kwh > 0 AND rub_per_kwh < 1e308
                        ),
                        source TEXT NOT NULL CHECK (length(trim(source)) > 0)
                    )"""
                )
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(electricity_tariffs)")
                }
                if "year" in columns:
                    connection.execute(
                        "INSERT INTO electricity_tariffs(year, rub_per_kwh, source) "
                        "VALUES (?, ?, ?) "
                        "ON CONFLICT(year) DO NOTHING",
                        (2026, 5.17, "Н. Н. Алаева (ВШН), сообщение от 16.10.2026 08:49"),
                    )
                connection.execute("PRAGMA user_version = 10")
            if version < 11:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(electricity_tariffs)")
                }
                if "year" in columns:
                    connection.execute(
                        "ALTER TABLE electricity_tariffs RENAME TO electricity_tariffs_yearly"
                    )
                    connection.execute(
                        """CREATE TABLE electricity_tariffs (
                            valid_from TEXT PRIMARY KEY NOT NULL CHECK (length(valid_from) = 10),
                            valid_to TEXT NOT NULL CHECK (
                                length(valid_to) = 10 AND valid_to >= valid_from
                            ),
                            rub_per_kwh REAL NOT NULL CHECK (
                                rub_per_kwh > 0 AND rub_per_kwh < 1e308
                            ),
                            source TEXT NOT NULL CHECK (length(trim(source)) > 0)
                        )"""
                    )
                    connection.execute(
                        """INSERT INTO electricity_tariffs
                           (valid_from, valid_to, rub_per_kwh, source)
                           SELECT printf('%04d-01-01', year), printf('%04d-12-31', year),
                                  rub_per_kwh, source FROM electricity_tariffs_yearly"""
                    )
                    connection.execute("DROP TABLE electricity_tariffs_yearly")
                connection.execute(
                    """INSERT INTO electricity_tariffs(valid_from, valid_to, rub_per_kwh, source)
                       VALUES ('2025-01-01', '2025-12-31', 4.68, ?)
                       ON CONFLICT(valid_from) DO NOTHING""",
                    ("Указание пользователя от 18.10.2026",),
                )
                connection.execute("PRAGMA user_version = 11")
            if version < 12:
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS plant_density_defaults (
                        plant_code TEXT NOT NULL REFERENCES plants(code),
                        available_from TEXT NOT NULL,
                        density_kgm3 REAL NOT NULL CHECK (density_kgm3 > 0),
                        source TEXT NOT NULL,
                        PRIMARY KEY(plant_code, available_from)
                    )"""
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS well_measurements (
                        plant_code TEXT NOT NULL REFERENCES plants(code),
                        well_code TEXT NOT NULL,
                        observed_at TEXT NOT NULL,
                        grain TEXT NOT NULL CHECK (grain IN ('snapshot','month','day')),
                        record_kind TEXT NOT NULL,
                        metric TEXT NOT NULL,
                        value REAL NOT NULL,
                        unit TEXT NOT NULL,
                        study_type TEXT NOT NULL,
                        source_file TEXT NOT NULL,
                        source_sheet TEXT NOT NULL,
                        source_row INTEGER NOT NULL,
                        exported_at TEXT NOT NULL,
                        PRIMARY KEY(plant_code, well_code, observed_at, record_kind,
                                    metric, source_file, source_sheet, source_row)
                    )"""
                )
                connection.execute("PRAGMA user_version = 12")

            if version < 13:
                columns = {row[1] for row in connection.execute("PRAGMA table_info(aggregates)")}
                if "runtime_total_h" not in columns:
                    connection.execute("ALTER TABLE aggregates ADD COLUMN runtime_total_h REAL")
                connection.execute("PRAGMA user_version = 13")
            if version < 14:
                columns = {row[1] for row in connection.execute("PRAGMA table_info(plants)")}
                if "operator_visible" not in columns:
                    connection.execute(
                        "ALTER TABLE plants ADD COLUMN operator_visible INTEGER NOT NULL "
                        "DEFAULT 1 CHECK (operator_visible IN (0, 1))"
                    )
                connection.execute("PRAGMA user_version = 14")
            if version < 15:
                self._migrate_measurement_semantics(connection)
                connection.execute("PRAGMA user_version = 15")
            if version < 16:
                self._migrate_source_numbers(connection)
                connection.execute("PRAGMA user_version = 16")
            if version < 17:
                connection.execute(
                    """UPDATE telemetry_measurements
                       SET metric = 'pressure_unassigned', unit = 'не подтверждена',
                           quality = 'unit_unconfirmed' ||
                               CASE WHEN coalesce(quality, '') = '' THEN ''
                               ELSE '; source_quality=' || quality END
                       WHERE source_kind IN ('excel', 'json_draft')
                         AND metric = 'p_out'
                         AND source_label = 'Датчик давления на выкиде'"""
                )
                connection.execute(
                    """UPDATE telemetry_measurements
                       SET unit = 'не подтверждена',
                           quality = 'unit_unconfirmed' ||
                               CASE WHEN coalesce(quality, '') = '' THEN ''
                               ELSE '; source_quality=' || quality END
                       WHERE unit != 'не подтверждена'
                         AND source_kind IN ('excel', 'json_draft', 'scada')
                         AND (
                             (metric = 'runtime' AND source_label LIKE '%мин%')
                             OR (metric IN ('p_in', 'p_out', 'p_bg') AND (
                                 plant_id IN (SELECT id FROM plants WHERE code = 'kns10bn')
                                 OR technical_place_id IN (
                                     SELECT tp.id FROM technical_places tp
                                     JOIN plants p ON p.id = tp.plant_id
                                     WHERE p.code = 'kns97pren' AND tp.code = 'kns97'
                                 )
                             ))
                         )"""
                )
                connection.execute("PRAGMA user_version = 17")
            if version < 18:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(aggregate_passports)")
                }
                if "pump_curve_source_json" not in columns:
                    connection.execute(
                        "ALTER TABLE aggregate_passports ADD COLUMN pump_curve_source_json TEXT"
                    )
                connection.execute("PRAGMA user_version = 18")
            if version < 19:
                columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(aggregate_passports)")
                }
                for column, column_type in (
                    ("source", "TEXT"),
                    ("comment", "TEXT"),
                    ("author", "TEXT"),
                    ("recorded_at", "TEXT"),
                    ("confirmed_fields_json", "TEXT NOT NULL DEFAULT '[]'"),
                    ("revision", "INTEGER NOT NULL DEFAULT 0"),
                ):
                    if column not in columns:
                        connection.execute(
                            f"ALTER TABLE aggregate_passports ADD COLUMN {column} {column_type}"
                        )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS aggregate_passport_revisions (
                        id INTEGER PRIMARY KEY,
                        aggregate_id INTEGER NOT NULL REFERENCES aggregates(id),
                        seq INTEGER NOT NULL,
                        action TEXT NOT NULL CHECK (action IN ('insert', 'supersede')),
                        valid_from TEXT NOT NULL,
                        recorded_at TEXT NOT NULL,
                        source TEXT NOT NULL,
                        comment TEXT NOT NULL,
                        author TEXT NOT NULL,
                        confirmed_fields_json TEXT NOT NULL DEFAULT '[]',
                        before_json TEXT,
                        after_json TEXT NOT NULL
                    )"""
                )
                connection.execute(
                    """CREATE UNIQUE INDEX IF NOT EXISTS ux_passport_revisions_seq
                       ON aggregate_passport_revisions (aggregate_id, seq)"""
                )
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS manual_measurements (
                        id INTEGER PRIMARY KEY,
                        aggregate_id INTEGER NOT NULL REFERENCES aggregates(id),
                        measured_at TEXT NOT NULL,
                        regime_json TEXT NOT NULL,
                        source TEXT NOT NULL,
                        comment TEXT NOT NULL,
                        author TEXT NOT NULL,
                        recorded_at TEXT NOT NULL
                    )"""
                )
                connection.execute(
                    """CREATE INDEX IF NOT EXISTS ix_manual_measurements_aggregate
                       ON manual_measurements (aggregate_id, measured_at)"""
                )
                connection.execute("PRAGMA user_version = 19")
            if version < 20:
                columns = {
                    row[1]: row
                    for row in connection.execute("PRAGMA table_info(aggregate_passports)")
                }
                if columns["transmission_eff"][3]:
                    # Сохраняем значения и FK/ID, снимая только NOT NULL с одного поля.
                    # NULL означает неизвестный КПД, а не идеальную передачу.
                    connection.execute("SAVEPOINT nullable_transmission")
                    connection.execute(
                        "ALTER TABLE aggregate_passports ADD COLUMN "
                        "_transmission_eff_v20 REAL DEFAULT 1.0"
                    )
                    connection.execute(
                        "UPDATE aggregate_passports SET _transmission_eff_v20 = transmission_eff"
                    )
                    connection.execute(
                        "ALTER TABLE aggregate_passports DROP COLUMN transmission_eff"
                    )
                    connection.execute(
                        "ALTER TABLE aggregate_passports RENAME COLUMN "
                        "_transmission_eff_v20 TO transmission_eff"
                    )
                    connection.execute("RELEASE nullable_transmission")
                connection.execute("PRAGMA user_version = 20")
            if version < 21:
                connection.execute(
                    """CREATE TABLE IF NOT EXISTS equipment_journal (
                        id INTEGER PRIMARY KEY,
                        aggregate_id INTEGER NOT NULL REFERENCES aggregates(id),
                        seq INTEGER NOT NULL,
                        component TEXT NOT NULL CHECK (
                            component IN ('pump', 'motor', 'transmission', 'vfd')
                        ),
                        effective_at TEXT NOT NULL,
                        recorded_at TEXT NOT NULL,
                        reason TEXT NOT NULL CHECK (
                            reason IN (
                                'repair', 'replacement', 'passport', 'inspection', 'correction'
                            )
                        ),
                        evidence TEXT NOT NULL CHECK (evidence IN ('documented', 'estimate')),
                        source TEXT NOT NULL,
                        author TEXT NOT NULL,
                        comment TEXT NOT NULL,
                        changes_json TEXT NOT NULL,
                        reset_fields_json TEXT NOT NULL DEFAULT '[]',
                        supersedes_id INTEGER REFERENCES equipment_journal(id),
                        superseded_by_id INTEGER REFERENCES equipment_journal(id)
                    )"""
                )
                connection.execute(
                    """CREATE UNIQUE INDEX IF NOT EXISTS ux_equipment_journal_seq
                       ON equipment_journal (aggregate_id, seq)"""
                )
                connection.execute(
                    """CREATE UNIQUE INDEX IF NOT EXISTS ux_equipment_journal_supersedes
                       ON equipment_journal (supersedes_id)"""
                )
                connection.execute(
                    """CREATE INDEX IF NOT EXISTS ix_equipment_journal_aggregate_effective
                       ON equipment_journal (aggregate_id, effective_at)"""
                )
                connection.execute("PRAGMA user_version = 21")

    @staticmethod
    def _migrate_source_numbers(connection: sqlite3.Connection) -> None:
        for plant, mapping in (
            ("kns14an", {"ГНУ REDA 1000-1300": "НА-2", "СИН61.02.100": "НА-1"}),
            ("kns155tbn", {"ЦНС 180-1422(-3)": "НА-2", "ЦНС 180-1050": "НА-3"}),
            ("kns129ln", {"ГНУ 750-1100": "НА-2"}),
        ):
            rows = connection.execute(
                """SELECT a.id, a.code,
                          (SELECT pump_model FROM aggregate_passports ap
                           WHERE ap.aggregate_id = a.id
                           ORDER BY valid_from DESC LIMIT 1) AS pump_model
                   FROM aggregates a
                   JOIN technical_places tp ON tp.id = a.technical_place_id
                   JOIN plants p ON p.id = tp.plant_id
                   WHERE p.code = ? AND a.code IN ('НА-1', 'НА-2')""",
                (plant,),
            ).fetchall()
            changes = [
                (row["id"], mapping[row["pump_model"]])
                for row in rows
                if row["pump_model"] in mapping and row["code"] != mapping[row["pump_model"]]
            ]
            for aggregate_id, _ in changes:
                connection.execute(
                    "UPDATE aggregates SET code = ? WHERE id = ?",
                    (f"source-number-migration-{aggregate_id}", aggregate_id),
                )
            for aggregate_id, code in changes:
                connection.execute(
                    "UPDATE aggregates SET code = ? WHERE id = ?", (code, aggregate_id)
                )

    @staticmethod
    def _migrate_measurement_semantics(connection: sqlite3.Connection) -> None:
        connection.execute(
            """UPDATE telemetry_measurements SET metric = 'power_daily_reported'
               WHERE metric = 'power' AND (
                   lower(coalesce(source_sheet, '')) = 'r1020'
                   OR coalesce(source_file, '') LIKE '%проток%'
                   OR coalesce(source_file, '') LIKE '%Проток%')"""
        )
        plant = connection.execute("SELECT id FROM plants WHERE code = 'kns97pren'").fetchone()
        if plant is not None:
            for code, name, aggregates in (
                ("kns97", "КНС-97", ("НА-1", "НА-3")),
                ("kns97pr", "КНС-97ПР", ("НА-2 ПР",)),
            ):
                connection.execute(
                    "INSERT INTO technical_places(plant_id, code, name) VALUES (?, ?, ?) "
                    "ON CONFLICT(plant_id, code) DO NOTHING",
                    (plant[0], code, name),
                )
                place = connection.execute(
                    "SELECT id FROM technical_places WHERE plant_id = ? AND code = ?",
                    (plant[0], code),
                ).fetchone()[0]
                for aggregate in aggregates:
                    connection.execute(
                        "UPDATE aggregates SET technical_place_id = ? WHERE code = ? AND "
                        "technical_place_id IN "
                        "(SELECT id FROM technical_places WHERE plant_id = ?)",
                        (place, aggregate, plant[0]),
                    )
                pattern = "%КНС-97 ПР ЕН%" if code == "kns97pr" else "%КНС-97 ЕН%"
                connection.execute(
                    "UPDATE telemetry_measurements SET technical_place_id = ? "
                    "WHERE plant_id = ? AND aggregate_id IS NULL AND source_file LIKE ?",
                    (place, plant[0], pattern),
                )
            connection.execute(
                """UPDATE telemetry_measurements SET technical_place_id =
                       (SELECT technical_place_id FROM aggregates WHERE id = aggregate_id)
                   WHERE plant_id = ? AND aggregate_id IS NOT NULL""",
                (plant[0],),
            )
        for field in ("pump_eta_nom", "motor_eta_nom"):
            connection.execute(
                f"""UPDATE aggregate_passports SET {field} = NULL
                    WHERE abs({field} - ?) < 1e-12 AND aggregate_id IN (
                        SELECT aggregate_id FROM parameter_clarifications
                        WHERE field = ? AND status = 'open' AND reason LIKE '%√0,9%')""",
                (math.sqrt(0.9), field),
            )
            connection.execute(
                """UPDATE parameter_clarifications
                   SET provisional_value = 'не задано',
                       reason = 'Искусственное разложение √0,9 удалено; нужен паспорт изготовителя.'
                   WHERE field = ? AND status = 'open' AND reason LIKE '%√0,9%'
                     AND aggregate_id IN (
                         SELECT aggregate_id FROM aggregate_passports
                         WHERE pump_eta_nom IS NULL OR motor_eta_nom IS NULL)""",
                (field,),
            )

    def set_operator_visible(self, plant_code: str, visible: bool) -> None:
        """Флаг доступности объекта оператору; синхронизируется из YAML при запуске."""
        with self._connection() as connection:
            connection.execute(
                "UPDATE plants SET operator_visible = ? WHERE code = ?",
                (int(bool(visible)), plant_code),
            )

    def set_default_density(self, plant_code: str, density: float) -> None:
        """Плотность агента объекта, кг/м³: используется, если в окне нет замера."""
        with self._connection() as connection:
            updated = connection.execute(
                "UPDATE plants SET default_density = ? WHERE code = ?", (density, plant_code)
            ).rowcount
        if not updated:
            raise KeyError(plant_code)

    def set_runtime_total(
        self,
        plant_code: str,
        aggregate_code: str,
        hours: float | None,
        *,
        technical_place_code: str | None = None,
    ) -> None:
        """Наработка агрегата с начала эксплуатации, ч."""
        with self._connection() as connection:
            aggregate_id = self._aggregate_id(
                connection, plant_code, aggregate_code, technical_place_code
            )
            connection.execute(
                "UPDATE aggregates SET runtime_total_h = ? WHERE id = ?", (hours, aggregate_id)
            )

    def station_metric_events(
        self,
        plant_code: str,
        metric: str,
        start: datetime,
        end: datetime,
        *,
        technical_place_code: str | None = None,
    ) -> list[tuple[datetime, float | None]]:
        """События станционной метрики за [start, end) и последнее событие до start.

        Давления пишутся по изменению значения, поэтому значение на начало окна —
        это последнее событие перед ним.
        """
        with self._connection() as connection:
            plant_id = self._id(connection, "SELECT id FROM plants WHERE code = ?", plant_code)
            place_id = self._technical_place_id(connection, plant_code, technical_place_code)
            previous = connection.execute(
                """
                SELECT timestamp, value, metric, unit, quality FROM telemetry_measurements
                WHERE plant_id = ? AND technical_place_id = ?
                  AND aggregate_id IS NULL AND metric = ? AND timestamp < ?
                ORDER BY timestamp DESC, id DESC LIMIT 1
                """,
                (plant_id, place_id, metric, self._iso(start)),
            ).fetchone()
            rows = connection.execute(
                """
                SELECT timestamp, value, metric, unit, quality FROM telemetry_measurements
                WHERE plant_id = ? AND technical_place_id = ?
                  AND aggregate_id IS NULL AND metric = ?
                  AND timestamp >= ? AND timestamp < ?
                ORDER BY timestamp, id
                """,
                (plant_id, place_id, metric, self._iso(start), self._iso(end)),
            ).fetchall()
        events = ([previous] if previous else []) + list(rows)
        return [
            (
                datetime.fromisoformat(row["timestamp"]),
                row["value"] if usable_measurement(row) else None,
            )
            for row in events
        ]

    def last_station_timestamp(
        self,
        plant_code: str,
        metric: str,
        *,
        technical_place_code: str | None = None,
    ) -> datetime | None:
        """Время последнего события станционной метрики."""
        with self._connection() as connection:
            place_id = self._technical_place_id(connection, plant_code, technical_place_code)
            row = connection.execute(
                """
                SELECT MAX(tm.timestamp) AS timestamp
                FROM telemetry_measurements tm JOIN plants p ON p.id = tm.plant_id
                WHERE p.code = ? AND tm.technical_place_id = ?
                  AND tm.aggregate_id IS NULL AND tm.metric = ?
                """,
                (plant_code, place_id, metric),
            ).fetchone()
        return datetime.fromisoformat(row["timestamp"]) if row and row["timestamp"] else None

    def plant_density_default(self, plant_code: str, at: date) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """SELECT density_kgm3, available_from, source FROM plant_density_defaults
                   WHERE plant_code = ? AND available_from <= ?
                   ORDER BY available_from DESC LIMIT 1""",
                (plant_code, at.isoformat()),
            ).fetchone()
            return dict(row) if row else None

    def seed_confirmed_density_defaults(self) -> None:
        with self._connection() as connection:
            connection.executemany(
                """INSERT INTO plant_density_defaults
                   (plant_code, available_from, density_kgm3, source)
                   SELECT code, '2026-10-16', ?, ? FROM plants WHERE code = ?
                   ON CONFLICT(plant_code, available_from) DO NOTHING""",
                [
                    (
                        rho,
                        "Н. Н. Алаева (ВШН), сообщение от 16.10.2026 08:46; "
                        "дата начала применимости неизвестна, указана дата получения",
                        code,
                    )
                    for code, rho in (("knsopu", 1142), ("kns54an", 1138), ("kns97pren", 1000))
                ],
            )

    def add_well_measurements(self, rows: list[dict]) -> None:
        for row in rows:
            date.fromisoformat(row["observed_at"])
            date.fromisoformat(row["exported_at"])
            if not math.isfinite(row["value"]) or row["value"] < 0:
                raise ValueError("Некорректное измерение скважины")
        with self._connection() as connection:
            connection.executemany(
                """INSERT INTO well_measurements VALUES
                   (:plant_code,:well_code,:observed_at,:grain,:record_kind,:metric,:value,:unit,
                    :study_type,:source_file,:source_sheet,:source_row,:exported_at)
                   ON CONFLICT DO UPDATE SET value=excluded.value, unit=excluded.unit,
                       study_type=excluded.study_type, exported_at=excluded.exported_at""",
                rows,
            )

    def wells(self, plant_code: str) -> list[dict]:
        with self._connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    """SELECT well_code AS code, max(observed_at) AS latest_at,
                          max(CASE WHEN record_kind='current' THEN observed_at END) AS current_at
                   FROM well_measurements WHERE plant_code=?
                   GROUP BY well_code ORDER BY well_code""",
                    (plant_code,),
                )
            ]

    def well_history(self, plant_code: str, well_code: str) -> list[dict]:
        with self._connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    """SELECT * FROM well_measurements WHERE plant_code=? AND well_code=?
                   ORDER BY observed_at, record_kind, source_file,
                            source_sheet, source_row, metric""",
                    (plant_code, well_code),
                )
            ]

    def electricity_tariff(self, at: date) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """SELECT valid_from, valid_to, rub_per_kwh, source FROM electricity_tariffs
                   ORDER BY max(julianday(valid_from) - julianday(?),
                                julianday(?) - julianday(valid_to), 0), valid_from DESC LIMIT 1""",
                (at.isoformat(), at.isoformat()),
            ).fetchone()
            return dict(row) if row else None

    def upsert_electricity_tariff(
        self, valid_from: date, valid_to: date, rub_per_kwh: float, *, source: str
    ) -> None:
        if type(valid_from) is not date or type(valid_to) is not date or valid_to < valid_from:
            raise ValueError("Укажите корректный диапазон дат тарифа: начало не позже окончания")
        if (
            isinstance(rub_per_kwh, bool)
            or not isinstance(rub_per_kwh, (int, float))
            or not math.isfinite(rub_per_kwh)
            or not 0 < rub_per_kwh < 1e308
        ):
            raise ValueError("Тариф должен быть конечным положительным числом в руб/кВт·ч")
        if not source.strip():
            raise ValueError("Укажите источник тарифа")
        start, end = valid_from.isoformat(), valid_to.isoformat()
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            overlap = connection.execute(
                """SELECT 1 FROM electricity_tariffs
                   WHERE valid_from <= ? AND valid_to >= ? AND valid_from != ? LIMIT 1""",
                (end, start, start),
            ).fetchone()
            if overlap:
                raise ValueError("Диапазон тарифа пересекается с существующим периодом")
            connection.execute(
                """INSERT INTO electricity_tariffs(valid_from, valid_to, rub_per_kwh, source)
                   VALUES (?, ?, ?, ?) ON CONFLICT(valid_from) DO UPDATE SET
                       valid_to = excluded.valid_to,
                       rub_per_kwh = excluded.rub_per_kwh, source = excluded.source""",
                (start, end, rub_per_kwh, source),
            )

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
        operator_visible: bool = True,
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
                    code, name, ngdu_id, water_type, branch, is_example, operator_visible,
                    default_density, default_viscosity
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    int(operator_visible),
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

    def upsert_technical_place(
        self,
        plant_code: str,
        code: str,
        name: str,
        *,
        update_existing: bool = True,
    ) -> None:
        with self._connection() as connection:
            plant_id = self._id(connection, "SELECT id FROM plants WHERE code = ?", plant_code)
            conflict = "DO UPDATE SET name = excluded.name" if update_existing else "DO NOTHING"
            connection.execute(
                "INSERT INTO technical_places(plant_id, code, name) VALUES (?, ?, ?) "
                "ON CONFLICT(plant_id, code) " + conflict,
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
        technical_place_code: str | None = None,
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
                "pump_curve_source_json": extra.get("pump_curve_source_json"),
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
                    pump_curve_qeta_json, pump_curve_source_json, motor_model, motor_synchronous,
                    motor_p_nom, motor_eta_nom, motor_cos_phi, motor_voltage_kv,
                    motor_i_nom, motor_n_rpm, transmission_model, transmission_ratio,
                    transmission_eff, vfd
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    pump_curve_source_json = excluded.pump_curve_source_json,
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
                    fields["pump_curve_source_json"],
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
        technical_place_code: str | None = None,
        source_kind: str | None = None,
        source_file: str | None = None,
        source_sheet: str | None = None,
        source_row: int | None = None,
        source_tag: str | None = None,
        source_label: str | None = None,
    ) -> None:
        self.add_measurements([
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
        ])

    def add_measurements(self, measurements: Iterator[TelemetryMeasurement]) -> int:
        """Идемпотентно записать canonical telemetry пачкой."""
        stored = 0
        with self._connection() as connection:
            ids: dict[tuple[str, str | None, str | None], tuple[int, int, int | None]] = {}
            rows = []
            for measurement in measurements:
                expected_unit = _UNITS.get(measurement.metric)
                if expected_unit is None:
                    raise ValueError(f"неподдерживаемая telemetry metric: {measurement.metric}")
                unknown_unit = (
                    measurement.unit == "не подтверждена"
                    and (measurement.quality or "").split(";")[0] == "unit_unconfirmed"
                )
                if measurement.unit != expected_unit and not unknown_unit:
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
                    place_id = (
                        connection.execute(
                            "SELECT technical_place_id FROM aggregates WHERE id = ?",
                            (aggregate_id,),
                        ).fetchone()[0]
                        if aggregate_id is not None
                        else self._technical_place_id(
                            connection, measurement.plant_code, measurement.technical_place_code
                        )
                    )
                    ids[key] = (plant_id, place_id, aggregate_id)
                rows.append((
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
                ))
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
        technical_place_code: str | None = None,
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

    def manual_measurement(self, measurement_id: int) -> dict[str, Any] | None:
        """Прочитать один ручной замер по id (None, если запись не существует)."""
        with self._connection() as connection:
            return self._manual_measurement_row(connection, measurement_id)

    def manual_measurements(self, plant_code: str, aggregate_code: str) -> list[dict[str, Any]]:
        """Все ручные замеры агрегата, новые последними."""
        with self._connection() as connection:
            aggregate_id = self._aggregate_id(connection, plant_code, aggregate_code, None)
            rows = connection.execute(
                """SELECT mm.*, p.code AS plant_code, a.code AS aggregate_code
                   FROM manual_measurements mm
                   JOIN aggregates a ON a.id = mm.aggregate_id
                   JOIN technical_places tp ON tp.id = a.technical_place_id
                   JOIN plants p ON p.id = tp.plant_id
                   WHERE mm.aggregate_id = ?
                   ORDER BY mm.measured_at, mm.id""",
                (aggregate_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    @staticmethod
    def _manual_measurement_row(
        connection: sqlite3.Connection, measurement_id: int
    ) -> dict[str, Any] | None:
        row = connection.execute(
            """SELECT mm.*, p.code AS plant_code, a.code AS aggregate_code
               FROM manual_measurements mm
               JOIN aggregates a ON a.id = mm.aggregate_id
               JOIN technical_places tp ON tp.id = a.technical_place_id
               JOIN plants p ON p.id = tp.plant_id
               WHERE mm.id = ?""",
            (measurement_id,),
        ).fetchone()
        return dict(row) if row else None

    def annual_runtime(
        self,
        plant_code: str,
        aggregate_code: str,
        end: datetime,
        *,
        technical_place_code: str | None = None,
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
                    SELECT DATE(timestamp) AS day, metric, value, unit, quality
                    FROM telemetry_measurements
                    WHERE aggregate_id = ? AND metric = 'runtime'
                      AND timestamp >= ? AND timestamp < ?
                    ORDER BY day
                    """,
                    (aggregate_id, self._iso(start), self._iso(end)),
                )
            )
        expected_days = {start.date() + timedelta(days=offset) for offset in range(365)}
        if (
            len(rows) != 365
            or {date.fromisoformat(row["day"]) for row in rows} != expected_days
            or not all(usable_measurement(row) for row in rows)
        ):
            return None
        return sum(float(row["value"]) for row in rows)

    def measurements_in_window(
        self,
        plant_code: str,
        aggregate_code: str,
        start: datetime,
        end: datetime,
        *,
        technical_place_code: str | None = None,
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
                query += (
                    " OR (tm.aggregate_id IS NULL AND tm.technical_place_id = "
                    "(SELECT technical_place_id FROM aggregates WHERE id = ?))"
                )
                params.append(aggregate_id)
            query += ") ORDER BY tm.timestamp, tm.id"
            return [dict(row) for row in connection.execute(query, params)]

    def state_measurements_in_window(
        self,
        plant_code: str,
        aggregate_code: str,
        start: datetime,
        end: datetime,
        *,
        technical_place_code: str | None = None,
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
                            OR (tm.aggregate_id IS NULL AND tm.metric = 'p_bg'
                                AND tm.technical_place_id = (
                                    SELECT technical_place_id FROM aggregates WHERE id = ?))
                        )
                        ORDER BY tm.timestamp, tm.id
                    """,
                    (plant_code, self._iso(start), self._iso(end), aggregate_id, aggregate_id),
                )
            )
            previous = []
            for aggregate_scope, metric in (
                (True, "p_in"),
                (True, "p_out"),
                (True, "power"),
                (False, "p_bg"),
            ):
                scope = (
                    "tm.aggregate_id = ?"
                    if aggregate_scope
                    else "tm.aggregate_id IS NULL AND tm.technical_place_id = "
                    "(SELECT technical_place_id FROM aggregates WHERE id = ?)"
                )
                params: list[str | int] = [plant_code]
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
            aggregate_id = self._aggregate_id(connection, plant_code, aggregate_code, None)
            row = connection.execute(
                """SELECT a.code, a.role, a.runtime_total_h,
                          tp.code AS technical_place_code, tp.name AS technical_place_name
                   FROM aggregates a JOIN technical_places tp ON tp.id = a.technical_place_id
                   WHERE a.id = ?""",
                (aggregate_id,),
            ).fetchone()
            return dict(row)

    def aggregates(self, plant_code: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    """
                    SELECT a.code, a.role, a.runtime_total_h,
                           tp.code AS technical_place_code, tp.name AS technical_place_name
                    FROM aggregates a
                    JOIN technical_places tp ON tp.id = a.technical_place_id
                    JOIN plants p ON p.id = tp.plant_id
                    WHERE p.code = ?
                    ORDER BY a.code
                    """,
                    (plant_code,),
                )
            ]

    def has_measurements(self, source_kind: str | None = None) -> bool:
        query = "SELECT 1 FROM telemetry_measurements"
        params: tuple = ()
        if source_kind is not None:
            query += " WHERE source_kind = ?"
            params = (source_kind,)
        with self._connection() as connection:
            row = connection.execute(f"{query} LIMIT 1", params).fetchone()
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

    def last_day_with_daily_totals(
        self, plant_code: str, aggregate_code: str, *, metric: str = "q_day"
    ) -> date | None:
        """Последние сутки, за которые есть суточный итог.

        Дашборд открывается именно на них: у оборвавшегося последнего дня
        выгрузки суточных итогов нет, и открывать его по умолчанию значит
        встречать пользователя сообщением о непригодном режиме.
        """
        with self._connection() as connection:
            aggregate_id = self._aggregate_id(connection, plant_code, aggregate_code, None)
            row = connection.execute(
                """
                SELECT MAX(substr(timestamp, 1, 10)) AS day
                FROM telemetry_measurements
                WHERE aggregate_id = ? AND metric = ?
                """,
                (aggregate_id, metric),
            ).fetchone()
        return date.fromisoformat(row["day"]) if row and row["day"] else None

    def telemetry_dates(self, plant_code: str, aggregate_code: str) -> list[date]:
        with self._connection() as connection:
            aggregate_id = self._aggregate_id(connection, plant_code, aggregate_code, None)
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
        technical_place_code: str | None = None,
    ) -> dict[str, Any]:
        """Действующие на момент значения паспорта, собранные по полям.

        Возвращает строку формы aggregate_passports; значения — композиция
        базовых снимков и записей журнала оборудования на момент `at`.
        """
        with self._connection() as connection:
            connection.execute("BEGIN")
            aggregate_id = self._aggregate_id(
                connection, plant_code, aggregate_code, technical_place_code
            )
            row = self._equipment_resolver(connection, aggregate_id).resolve(at)
            if row is None:
                raise KeyError(f"нет действующего паспорта {plant_code}/{aggregate_code}")
            return row

    def passports_at(self, aggregate_id: int, moments: list[datetime]) -> dict[str, Any]:
        """Собранные паспортные строки на список моментов одним чтением.

        Ключ — moment.isoformat(), значение — та же строка, что выдаёт
        active_passport, или None, если на момент нет действующих данных.
        """
        with self._connection() as connection:
            connection.execute("BEGIN")
            resolver = self._equipment_resolver(connection, aggregate_id)
            return {moment.isoformat(): resolver.resolve(moment) for moment in moments}

    def passport_at(
        self, plant_code: str, aggregate_code: str, at: datetime
    ) -> dict[str, Any] | None:
        """Собранные значения на момент или None — в отличие от active_passport."""
        with self._connection() as connection:
            connection.execute("BEGIN")
            aggregate_id = self._aggregate_id(connection, plant_code, aggregate_code, None)
            return self._equipment_resolver(connection, aggregate_id).resolve(at)

    def equipment_head_revision(self, plant_code: str, aggregate_code: str) -> int:
        """Номер последней записи журнала оборудования (0 — только базовые снимки)."""
        with self._connection() as connection:
            connection.execute("BEGIN")
            aggregate_id = self._aggregate_id(connection, plant_code, aggregate_code, None)
            return self._journal_head(connection, aggregate_id)

    @staticmethod
    def _journal_head(connection: sqlite3.Connection, aggregate_id: int) -> int:
        row = connection.execute(
            "SELECT max(seq) AS head FROM equipment_journal WHERE aggregate_id = ?",
            (aggregate_id,),
        ).fetchone()
        return int(row["head"] or 0)

    def equipment_journal(self, plant_code: str, aggregate_code: str) -> list[dict[str, Any]]:
        """Все записи журнала агрегата по возрастанию seq (включая superseded)."""
        with self._connection() as connection:
            connection.execute("BEGIN")
            aggregate_id = self._aggregate_id(connection, plant_code, aggregate_code, None)
            return self._journal_rows(connection, aggregate_id)

    @staticmethod
    def _journal_rows(connection: sqlite3.Connection, aggregate_id: int) -> list[dict[str, Any]]:
        return [
            dict(row)
            for row in connection.execute(
                """SELECT * FROM equipment_journal
                   WHERE aggregate_id = ? ORDER BY seq, id""",
                (aggregate_id,),
            )
        ]

    def equipment_revisions(self, plant_code: str, aggregate_code: str) -> list[dict[str, Any]]:
        """Полные записи изменений, последние первыми, включая исходные паспорта."""
        with self._connection() as connection:
            connection.execute("BEGIN")
            aggregate_id = self._aggregate_id(connection, plant_code, aggregate_code, None)
            return self._equipment_revisions(connection, aggregate_id)

    def equipment_snapshot(
        self, plant_code: str, aggregate_code: str, at: datetime
    ) -> tuple[dict[str, Any] | None, int, list[dict[str, Any]], dict[str, Any]]:
        """Значения, голова журнала, архив истории и происхождение полей одной
        транзакцией чтения — иначе конкурентная запись может выдать старые
        значения с новым токеном и обойти защиту от потери правок."""
        with self._connection() as connection:
            connection.execute("BEGIN")
            aggregate_id = self._aggregate_id(connection, plant_code, aggregate_code, None)
            resolver = self._equipment_resolver(connection, aggregate_id)
            origins: dict[str, Any] = {}
            passport = resolver.resolve(at, origins)
            head = self._journal_head(connection, aggregate_id)
            return passport, head, self._equipment_revisions(connection, aggregate_id), origins

    def _equipment_revisions(self, connection, aggregate_id: int) -> list[dict[str, Any]]:
        revisions = [
            dict(row)
            for row in connection.execute(
                """SELECT id, aggregate_id, seq AS revision, action, valid_from,
                          recorded_at, source, comment, author, confirmed_fields_json,
                          before_json, after_json
                   FROM aggregate_passport_revisions
                   WHERE aggregate_id = ? ORDER BY seq DESC, id DESC""",
                (aggregate_id,),
            )
        ]
        versioned = {row["valid_from"] for row in revisions}
        baselines = [
            {
                "id": -row["id"],
                "aggregate_id": aggregate_id,
                "revision": 0,
                "action": "baseline",
                "valid_from": row["valid_from"],
                "recorded_at": None,
                "source": row["source"],
                "comment": row["comment"],
                "author": row["author"],
                "confirmed_fields_json": row["confirmed_fields_json"],
                "before_json": None,
                "after_json": json.dumps(dict(row), ensure_ascii=False),
            }
            for row in connection.execute(
                "SELECT * FROM aggregate_passports WHERE aggregate_id = ? ORDER BY valid_from",
                (aggregate_id,),
            )
            if row["valid_from"] not in versioned
        ]
        return revisions + baselines

    def _equipment_resolver(self, connection: sqlite3.Connection, aggregate_id: int):
        from .equipment_journal import EquipmentResolver

        passports = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM aggregate_passports WHERE aggregate_id = ? ORDER BY valid_from, id",
                (aggregate_id,),
            )
        ]
        return EquipmentResolver(
            aggregate_id,
            passports,
            self._equipment_revisions(connection, aggregate_id),
            self._journal_rows(connection, aggregate_id),
        )

    def journal_snapshot(self, plant_code: str, aggregate_code: str):
        with self._connection() as connection:
            connection.execute("BEGIN")
            aggregate_id = self._aggregate_id(connection, plant_code, aggregate_code, None)
            return (
                self._journal_head(connection, aggregate_id),
                self._journal_rows(connection, aggregate_id),
                self._equipment_revisions(connection, aggregate_id),
            )

    def append_equipment_change(
        self,
        plant_code: str,
        aggregate_code: str,
        *,
        component: str,
        effective_at: datetime,
        expected_revision: str,
        changes: dict[str, Any],
        reset_fields: list[str],
        reason: str,
        evidence: str,
        source: str,
        author: str,
        comment: str,
        supersedes_id: int | None,
        recorded_at: datetime,
    ):
        """Append and supersede atomically; existing values/history are never overwritten."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            aggregate_id = self._aggregate_id(connection, plant_code, aggregate_code, None)
            head = self._journal_head(connection, aggregate_id)
            if expected_revision != str(head):
                raise RevisionConflict(expected_revision, str(head))
            original = None
            if supersedes_id is not None:
                original = connection.execute(
                    "SELECT * FROM equipment_journal WHERE id = ? AND aggregate_id = ?",
                    (supersedes_id, aggregate_id),
                ).fetchone()
                if original is None:
                    raise KeyError("исправляемая запись не найдена в журнале агрегата")
                if original["superseded_by_id"] is not None:
                    raise JournalConflict("запись уже исправлена; загрузите актуальную историю")
                if component != original["component"]:
                    raise JournalConflict("исправление не может менять компонент записи")
                if set(changes) != set(json.loads(original["changes_json"])):
                    raise JournalConflict("исправление должно содержать исходный набор параметров")
                reset_fields = json.loads(original["reset_fields_json"])
            affected = set(changes) | set(reset_fields)
            for row in self._journal_rows(connection, aggregate_id):
                if row["superseded_by_id"] is not None or row["id"] == supersedes_id:
                    continue
                if row["effective_at"] == effective_at.isoformat():
                    other = set(json.loads(row["changes_json"])) | set(
                        json.loads(row["reset_fields_json"])
                    )
                    if affected & other:
                        raise JournalConflict(
                            "на эту дату уже есть запись параметра; используйте исправление"
                        )
            cursor = connection.execute(
                """INSERT INTO equipment_journal
                (aggregate_id, seq, component, effective_at, recorded_at, reason, evidence,
                 source, author, comment, changes_json, reset_fields_json, supersedes_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    aggregate_id,
                    head + 1,
                    component,
                    effective_at.isoformat(),
                    recorded_at.isoformat(),
                    reason,
                    evidence,
                    source,
                    author,
                    comment,
                    json.dumps(changes, ensure_ascii=False),
                    json.dumps(reset_fields),
                    supersedes_id,
                ),
            )
            if original is not None:
                connection.execute(
                    "UPDATE equipment_journal SET superseded_by_id = ? WHERE id = ?",
                    (cursor.lastrowid, supersedes_id),
                )
            return (
                head + 1,
                self._journal_rows(connection, aggregate_id),
                self._equipment_revisions(connection, aggregate_id),
            )

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
            aggregate_id = self._aggregate_id(connection, plant_code, aggregate_code, None)
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
            aggregate_id = self._aggregate_id(connection, plant_code, aggregate_code, None)
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
            aggregate_id = self._aggregate_id(connection, plant_code, aggregate_code, None)
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
        self, connection: sqlite3.Connection, plant_code: str, technical_place_code: str | None
    ) -> int:
        rows = connection.execute(
            """SELECT tp.id FROM technical_places tp JOIN plants p ON p.id = tp.plant_id
               WHERE p.code = ? AND (? IS NULL OR tp.code = ?)""",
            (plant_code, technical_place_code, technical_place_code),
        ).fetchall()
        if not rows:
            raise KeyError(f"{plant_code}/{technical_place_code}")
        if len(rows) != 1:
            raise ValueError(f"Для {plant_code} необходимо указать гидравлическую группу")
        return int(rows[0][0])

    def _aggregate_id(
        self,
        connection: sqlite3.Connection,
        plant_code: str,
        aggregate_code: str,
        technical_place_code: str | None,
    ) -> int:
        rows = connection.execute(
            """SELECT a.id FROM aggregates a
               JOIN technical_places tp ON tp.id = a.technical_place_id
               JOIN plants p ON p.id = tp.plant_id
               WHERE p.code = ? AND a.code = ? AND (? IS NULL OR tp.code = ?)""",
            (plant_code, aggregate_code, technical_place_code, technical_place_code),
        ).fetchall()
        if not rows:
            raise KeyError(f"{plant_code}/{technical_place_code}/{aggregate_code}")
        if len(rows) != 1:
            raise ValueError(f"Неоднозначный агрегат {plant_code}/{aggregate_code}")
        return int(rows[0][0])

    @staticmethod
    def _iso(value: datetime | None) -> str | None:
        return value.isoformat() if value else None
