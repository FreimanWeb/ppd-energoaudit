"""Equipment journal input and read-only access to legacy passports/measurements."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..db import AuditDatabase
from ..equipment_journal import DEFAULT_VALUES, FIELD_COLUMNS
from ..equipment_parameters import EQUIPMENT_PARAMETERS
from ..spec import (
    AggregateSpec,
    EquipmentData,
    MotorSpec,
    PumpKind,
    PumpSpec,
    RegimeMeasurement,
    TransmissionSpec,
)


EQUIPMENT_FIELD_KEYS = frozenset(FIELD_COLUMNS)


class JournalWriteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    component: Literal["pump", "motor", "transmission", "vfd"]
    effective_at: datetime
    expected_revision: str
    changes: dict[str, Any]
    reason: Literal["repair", "replacement", "passport", "inspection", "correction"]
    evidence: Literal["documented", "estimate"]
    source: str
    author: str
    comment: str = ""
    supersedes_id: int | None = Field(default=None, gt=0)

    @field_validator("source", "author")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("источник и автор записи обязательны")
        return value.strip()

    @field_validator("effective_at")
    @classmethod
    def local_date(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            raise ValueError("effective_at задаётся в локальном времени без UTC offset")
        return value

    @model_validator(mode="after")
    def validate_changes(self):
        if not self.changes:
            raise ValueError("выберите хотя бы один изменяемый параметр")
        allowed = {
            key
            for key in FIELD_COLUMNS
            if key == self.component or key.startswith(self.component + ".")
        }
        if set(self.changes) - allowed:
            raise ValueError("неизвестный параметр или параметр другого компонента")
        if (self.reason == "correction") != (self.supersedes_id is not None):
            raise ValueError(
                "исправление требует supersedes_id; для нового события его не указывают"
            )
        if self.reason == "replacement" and self.component in {"pump", "motor"}:
            model = self.changes.get(self.component + ".model")
            if not isinstance(model, str) or not model.strip():
                raise ValueError("для замены укажите модель нового оборудования")
            if self.component == "pump" and "pump.kind" not in self.changes:
                raise ValueError("для замены насоса явно укажите его тип")
        data = EquipmentData().model_dump(mode="json")
        for key, value in self.changes.items():
            if isinstance(value, bool) and key not in {"vfd", "motor.synchronous"}:
                raise ValueError(
                    "числовой или текстовый параметр не может быть логическим значением"
                )
            if key in {"vfd", "motor.synchronous"} and not isinstance(value, bool):
                raise ValueError("признак оборудования задаётся true или false")
            if (
                key == "pump.curve_source"
                and isinstance(value, dict)
                and self.evidence == "estimate"
            ):
                value = {**value, "verified": False}
            if "." in key:
                group, field = key.split(".")
                data[group][field] = value
            else:
                data[key] = value
        validated = EquipmentData.model_validate(data).model_dump(mode="json")
        self.changes = {
            key: validated[key.split(".")[0]][key.split(".")[1]] if "." in key else validated[key]
            for key in self.changes
        }
        return self


def equipment_from_passport(passport: dict[str, Any]) -> EquipmentData:
    """Read legacy/composed values without rejecting unrelated historical ranges."""
    return EquipmentData.model_construct(
        pump=PumpSpec(
            model=passport["pump_model"],
            kind=PumpKind(passport["pump_kind"]),
            q_nom=passport["pump_q_nom"],
            h_nom=passport["pump_h_nom"],
            eta_nom=passport["pump_eta_nom"],
            power_nom=passport["pump_power_nom"],
            n_rpm=passport["pump_n_rpm"],
            curve_qh=json.loads(passport["pump_curve_qh_json"]),
            curve_qeta=json.loads(passport["pump_curve_qeta_json"]),
            curve_source=json.loads(passport["pump_curve_source_json"])
            if passport["pump_curve_source_json"]
            else None,
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
    )


def passport_fields_from_equipment(equipment: EquipmentData) -> dict[str, Any]:
    from ..equipment_journal import passport_columns

    data = equipment.model_dump(mode="json")
    return passport_columns({
        key: data[key.split(".")[0]][key.split(".")[1]] if "." in key else data[key]
        for key in FIELD_COLUMNS
    })


def apply_equipment_override(spec: AggregateSpec, override: EquipmentData) -> AggregateSpec:
    scenario = override.model_copy(deep=True)
    if scenario.pump.curve_source is not None:
        scenario.pump.curve_source.verified = False
    return spec.model_copy(
        update={
            "pump": scenario.pump,
            "motor": scenario.motor,
            "transmission": scenario.transmission,
            "vfd": scenario.vfd,
        }
    )


def _history_item(record: dict[str, Any]) -> dict[str, Any]:
    item = {
        "id": record["id"] if record["id"] is not None else -(record["revision"] + 1),
        "revision": str(record["revision"]),
        "action": record["action"],
        "valid_from": record["valid_from"],
        "valid_to": None,
        **{name: record[name] for name in ("recorded_at", "source", "comment", "author")},
        "confirmed_fields": json.loads(record["confirmed_fields_json"] or "[]"),
    }
    if record.get("after_json"):
        after = json.loads(record["after_json"])
        item["equipment"] = equipment_from_passport(after).model_dump(mode="json")
        item["valid_to"] = after.get("valid_to")
    if record.get("before_json"):
        item["superseded"] = equipment_from_passport(json.loads(record["before_json"])).model_dump(
            mode="json"
        )
    return item


def equipment_view(
    database: AuditDatabase, object_id: str, aggregate_id: str, at: datetime
) -> dict[str, Any]:
    passport, head, records, origins = database.equipment_snapshot(object_id, aggregate_id, at)
    result = {
        "passport_id": passport["id"] if passport else None,
        "revision": str(head),
        "valid_from": passport["valid_from"] if passport else None,
        "valid_to": passport["valid_to"] if passport else None,
        "equipment": (
            equipment_from_passport(passport) if passport else EquipmentData()
        ).model_dump(mode="json"),
        "provenance": None,
        "history": [_history_item(row) for row in records],
    }
    if passport and (origins or passport.get("recorded_at")):
        result["provenance"] = {
            **{name: passport.get(name) for name in ("source", "comment", "author", "recorded_at")},
            "confirmed_fields": json.loads(passport["confirmed_fields_json"] or "[]"),
            "field_sources": origins,
        }
    return result


def _journal_response(snapshot) -> dict:
    head, rows, history = snapshot
    items = []
    for row in reversed(rows):
        items.append({
            **{
                name: row[name]
                for name in (
                    "id",
                    "component",
                    "effective_at",
                    "recorded_at",
                    "reason",
                    "evidence",
                    "source",
                    "author",
                    "comment",
                    "supersedes_id",
                )
            },
            "changes": json.loads(row["changes_json"]),
            "resets": {key: DEFAULT_VALUES[key] for key in json.loads(row["reset_fields_json"])},
            "superseded_by": row["superseded_by_id"],
        })
    return {
        "revision": str(head),
        "items": items,
        "legacy_history": [_history_item(row) for row in history],
        "parameters": EQUIPMENT_PARAMETERS,
    }


def equipment_journal_view(database: AuditDatabase, object_id: str, aggregate_id: str) -> dict:
    return _journal_response(database.journal_snapshot(object_id, aggregate_id))


def save_journal_entry(
    database: AuditDatabase, object_id: str, aggregate_id: str, request: JournalWriteRequest
) -> dict:
    reset_fields = []
    if request.reason == "replacement":
        reset_fields = sorted(
            key
            for key in FIELD_COLUMNS
            if (key == request.component or key.startswith(request.component + "."))
            and key not in request.changes
        )
    return _journal_response(
        database.append_equipment_change(
            object_id,
            aggregate_id,
            component=request.component,
            effective_at=request.effective_at,
            expected_revision=request.expected_revision,
            changes=request.changes,
            reset_fields=reset_fields,
            reason=request.reason,
            evidence=request.evidence,
            source=request.source,
            author=request.author,
            comment=request.comment,
            supersedes_id=request.supersedes_id,
            recorded_at=datetime.now(UTC),
        )
    )


def _measurement_item(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "measured_at": row["measured_at"],
        "source": row["source"],
        "comment": row["comment"],
        "author": row["author"],
        "regime": RegimeMeasurement(**json.loads(row["regime_json"])).model_dump(mode="json"),
    }


def manual_measurements_view(
    database: AuditDatabase, object_id: str, aggregate_id: str
) -> dict[str, Any]:
    return {
        "items": [
            _measurement_item(row) for row in database.manual_measurements(object_id, aggregate_id)
        ]
    }


def manual_measurement(
    database: AuditDatabase, object_id: str, aggregate_id: str, measurement_id: int
) -> dict[str, Any]:
    row = database.manual_measurement(measurement_id)
    if row is None or row["plant_code"] != object_id or row["aggregate_code"] != aggregate_id:
        raise KeyError(f"ручной замер {measurement_id} не найден")
    return row


def manual_measurement_view(row: dict[str, Any]) -> dict[str, Any]:
    return _measurement_item(row)
