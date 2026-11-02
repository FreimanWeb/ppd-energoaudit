"""Dated equipment values: legacy snapshots plus independent immutable field changes."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from .spec import EquipmentData


FIELD_COLUMNS = {
    "pump.model": "pump_model",
    "pump.kind": "pump_kind",
    "pump.q_nom": "pump_q_nom",
    "pump.h_nom": "pump_h_nom",
    "pump.eta_nom": "pump_eta_nom",
    "pump.power_nom": "pump_power_nom",
    "pump.n_rpm": "pump_n_rpm",
    "pump.curve_qh": "pump_curve_qh_json",
    "pump.curve_qeta": "pump_curve_qeta_json",
    "pump.curve_source": "pump_curve_source_json",
    "motor.model": "motor_model",
    "motor.synchronous": "motor_synchronous",
    "motor.p_nom": "motor_p_nom",
    "motor.eta_nom": "motor_eta_nom",
    "motor.cos_phi": "motor_cos_phi",
    "motor.voltage_kv": "motor_voltage_kv",
    "motor.i_nom": "motor_i_nom",
    "motor.n_rpm": "motor_n_rpm",
    "transmission.model": "transmission_model",
    "transmission.ratio": "transmission_ratio",
    "transmission.efficiency": "transmission_eff",
    "vfd": "vfd",
}
_JSON_FIELDS = {key for key, column in FIELD_COLUMNS.items() if column.endswith("_json")}
_BOOL_FIELDS = {"vfd", "motor.synchronous"}
_BINDING_FIELDS = {
    "pump.model",
    "pump.kind",
    "pump.n_rpm",
    "pump.q_nom",
    "pump.h_nom",
    "pump.eta_nom",
    "motor.n_rpm",
    "transmission.ratio",
    "pump.curve_qh",
    "pump.curve_qeta",
}
_DEFAULT_EQUIPMENT = EquipmentData().model_dump(mode="json")
DEFAULT_VALUES = {
    key: _DEFAULT_EQUIPMENT[key.split(".")[0]][key.split(".")[1]]
    if "." in key
    else _DEFAULT_EQUIPMENT[key]
    for key in FIELD_COLUMNS
}


def has_value(value: Any) -> bool:
    return value is not None and value != "" and value != []


def passport_values(row: dict) -> dict:
    values = {}
    for key, column in FIELD_COLUMNS.items():
        value = row.get(column)
        if key in _JSON_FIELDS:
            value = json.loads(value) if value is not None else DEFAULT_VALUES[key]
        elif key in _BOOL_FIELDS:
            value = bool(value)
        values[key] = value
    return values


def passport_columns(values: dict) -> dict:
    result = {}
    for key, column in FIELD_COLUMNS.items():
        value = values[key]
        if key in _JSON_FIELDS:
            value = json.dumps(value, ensure_ascii=False) if value is not None else None
        elif key in _BOOL_FIELDS:
            value = int(value)
        result[column] = value
    return result


def _legacy_origins(snapshot: dict, revisions: dict) -> dict:
    chain = []
    cursor = snapshot
    seen = set()
    while cursor and cursor.get("revision") and cursor["revision"] not in seen:
        seen.add(cursor["revision"])
        record = revisions.get(cursor["revision"])
        if record is None:
            break
        chain.append(record)
        cursor = json.loads(record["before_json"]) if record["before_json"] else None
    origins = {}
    if cursor and cursor.get("source"):
        for key in json.loads(cursor.get("confirmed_fields_json") or "[]"):
            origins[key] = {
                name: cursor.get(name) for name in ("source", "author", "comment", "recorded_at")
            }
    for record in reversed(chain):
        after = json.loads(record["after_json"])
        before = json.loads(record["before_json"]) if record.get("before_json") else None
        current = passport_values(after)
        previous = passport_values(before) if before else {}
        confirmed = set(json.loads(after.get("confirmed_fields_json") or "[]"))
        old_confirmed = (
            set(json.loads(before.get("confirmed_fields_json") or "[]")) if before else set()
        )
        for key, value in current.items():
            if previous.get(key) != value or key in confirmed - old_confirmed:
                if has_value(value) and record.get("source"):
                    origins[key] = {
                        name: record.get(name)
                        for name in ("source", "author", "comment", "recorded_at")
                    }
                else:
                    origins.pop(key, None)
    return origins


class EquipmentResolver:
    """Preloaded once per aggregate/read transaction; no SQL in point resolution."""

    def __init__(
        self, aggregate_id: int, passports: list[dict], revisions: list[dict], journal: list[dict]
    ):
        self.aggregate_id = aggregate_id
        self.passports = sorted(passports, key=lambda row: (row["valid_from"], row["id"]))
        revision_map = {row["revision"]: row for row in revisions if row["action"] != "baseline"}
        self.origins = {row["id"]: _legacy_origins(row, revision_map) for row in self.passports}
        self.legacy_changes = []
        previous = {}
        previous_origins = {}
        previous_confirmed = set()
        for row in self.passports:
            values = passport_values(row)
            origins = self.origins[row["id"]]
            confirmed = set(json.loads(row.get("confirmed_fields_json") or "[]"))
            changed = {
                key
                for key in FIELD_COLUMNS
                if values[key] != previous.get(key)
                # Losing old bookkeeping is not a new observation of that value.
                or bool(origins.get(key))
                and origins.get(key) != previous_origins.get(key)
                or key in confirmed - previous_confirmed
                and bool(origins.get(key))
            }
            self.legacy_changes.append((datetime.fromisoformat(row["valid_from"]), changed))
            previous, previous_origins, previous_confirmed = values, origins, confirmed
        self.journal = []
        for row in journal:
            if row["superseded_by_id"] is None:
                self.journal.append({
                    **row,
                    "at": datetime.fromisoformat(row["effective_at"]),
                    "changes": json.loads(row["changes_json"]),
                    "resets": {
                        key: DEFAULT_VALUES[key] for key in json.loads(row["reset_fields_json"])
                    },
                })
        self.journal.sort(key=lambda row: (row["at"], row["seq"]))

    def resolve(self, at: datetime, output_origins: dict | None = None) -> dict | None:
        stamp = at.isoformat()
        baseline = next(
            (
                row
                for row in reversed(self.passports)
                if row["valid_from"] <= stamp
                and (row["valid_to"] is None or stamp <= row["valid_to"])
            ),
            None,
        )
        active = [row for row in self.journal if row["at"] <= at]
        if baseline is None and not active:
            return None
        values = passport_values(baseline) if baseline else DEFAULT_VALUES.copy()
        origins = dict(self.origins[baseline["id"]]) if baseline else {}
        confirmed = (
            set(json.loads(baseline.get("confirmed_fields_json") or "[]")) if baseline else set()
        )
        legacy_times = {}
        for when, fields in self.legacy_changes:
            if when > at:
                break
            for key in fields:
                legacy_times[key] = when
        winning = {}
        for record in active:
            for key, value in {**record["resets"], **record["changes"]}.items():
                if legacy_times.get(key, datetime.min) > record["at"]:
                    continue
                values[key] = value
                winning[key] = (record["at"], record["seq"])
                origins[key] = {
                    **{
                        name: record[name]
                        for name in (
                            "source",
                            "author",
                            "comment",
                            "recorded_at",
                            "effective_at",
                            "evidence",
                            "reason",
                        )
                    },
                    "journal_id": record["id"],
                    "reset": key not in record["changes"],
                }
                if (
                    record["evidence"] == "documented"
                    and key in record["changes"]
                    and has_value(value)
                ):
                    confirmed.add(key)
                else:
                    confirmed.discard(key)
        source = values["pump.curve_source"]
        if source is not None:
            source = dict(source)
            latest_binding = max(
                (winning[key] for key in _BINDING_FIELDS if key in winning), default=None
            )
            source_time = winning.get("pump.curve_source")
            if latest_binding is not None and (source_time is None or latest_binding > source_time):
                source["verified"] = False
            if any(
                origins.get(key, {}).get("evidence") == "estimate"
                for key in ("pump.curve_source", "pump.curve_qh", "pump.curve_qeta")
            ):
                source["verified"] = False
            values["pump.curve_source"] = source
        row = (
            dict(baseline)
            if baseline
            else {
                "id": None,
                "aggregate_id": self.aggregate_id,
                "valid_from": min(r["effective_at"] for r in active),
                "valid_to": None,
                "revision": 0,
                "source": None,
                "author": None,
                "comment": "",
                "recorded_at": None,
            }
        )
        row.update(passport_columns(values))
        if winning:
            row["valid_from"] = max(
                row["valid_from"], max(time[0].isoformat() for time in winning.values())
            )
            latest = max(
                (origins[key] for key in winning), key=lambda origin: origin["recorded_at"]
            )
            row.update({
                name: latest[name] for name in ("source", "author", "comment", "recorded_at")
            })
        future = [record["effective_at"] for record in self.journal if record["at"] > at]
        future.extend(p["valid_from"] for p in self.passports if p["valid_from"] > stamp)
        if future:
            row["valid_to"] = min(future + ([row["valid_to"]] if row["valid_to"] else []))
        row["confirmed_fields_json"] = json.dumps(sorted(confirmed))
        if output_origins is not None:
            output_origins.update(origins)
        return row
