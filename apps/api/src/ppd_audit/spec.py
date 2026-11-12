"""Универсальное нормализованное описание объекта ППД (источник-независимое).

Иерархия:  ObjectSpec → AggregateSpec → {PumpSpec, MotorSpec, TransmissionSpec,
RegimeMeasurement, ReferenceOutputs}

Ядро формул (7)-(47) работает с этими структурами и не знает о формате исходников.
Спец собирается из структурированных паспортов, телеметрии или ручного ввода.
"""

from __future__ import annotations

import math
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator


class WaterType(StrEnum):
    fresh = "пресная"
    aggressive = "агрессивная"
    formation = "пластовая"


class PumpKind(StrEnum):
    centrifugal = "центробежный"  # ЦНС и т.п. — полная диагностика кривых (28)-(42)
    positive_displacement = "объёмный"  # поршневой/плунжерный — без кривых Q-H


class Branch(StrEnum):
    kns = "кнс"  # высоконапорная закачка (p_БГ есть), декомпозиция (31)-(36)
    transfer = "перекачка"  # перекачка нефти/эмульсии, декомпозиция (37)-(42)


# Ключевые слова в названии насоса → объёмный (плунжерный/поршневой) тип.
_POSITIVE_DISPLACEMENT_HINTS = ("нпж", "ст-а", "син", "плунж", "поршн", "тнг", "пт ", "нп ")


def infer_pump_kind(model: str, n_rpm: float | None = None) -> PumpKind:
    """Эвристика типа насоса по названию/оборотам (ЦНС=центробежный, НПЖ/СИН=объёмный)."""
    m = (model or "").lower().replace("ё", "е")
    if any(h in m for h in _POSITIVE_DISPLACEMENT_HINTS):
        return PumpKind.positive_displacement
    if n_rpm is not None and n_rpm < 800:  # плунжерные тихоходны (~300 об/мин)
        return PumpKind.positive_displacement
    return PumpKind.centrifugal


# Серии синхронных двигателей (влияет на α в (26): синхронный → α=2).
_SYNCHRONOUS_MOTOR_HINTS = ("стд", "сдн", "сд-", "вдс", "сднз")


def infer_motor_synchronous(model: str) -> bool:
    """Эвристика синхронности ЭД по серии (СТД/СДН… — синхронные; АИ/ВАО/5АИ — асинхронные)."""
    m = (model or "").lower().replace("ё", "е").replace(" ", "")
    return any(h in m for h in _SYNCHRONOUS_MOTOR_HINTS)


class PumpCurveSource(BaseModel):
    """Происхождение кривой; проверка применимости не следует из наличия точек."""

    kind: Literal["manufacturer", "engineering", "experimental", "unverified"] = "unverified"
    reference: str = ""
    model: str | None = Field(None, description="Явная привязка к модели; подтверждается отдельно")
    speed_rpm: float | None = Field(None, gt=0, allow_inf_nan=False)
    frequency_hz: float | None = Field(None, gt=0, allow_inf_nan=False)
    verified: bool = False
    note: str = ""

    @model_validator(mode="after")
    def require_verified_binding(self) -> PumpCurveSource:
        if self.verified and (
            self.kind == "unverified"
            or not self.reference.strip()
            or not self.model
            or self.speed_rpm is None
        ):
            raise ValueError("Подтверждённая кривая требует источника, модели и частоты вращения")
        return self


class PumpSpec(BaseModel):
    model: str = ""
    kind: PumpKind = PumpKind.centrifugal
    q_nom: float | None = Field(None, description="ном. подача Q_ном, м³/ч")
    h_nom: float | None = Field(None, description="ном. напор H_ном, м")
    eta_nom: float | None = Field(None, description="ном. КПД насоса, о.е.")
    power_nom: float | None = Field(None, description="потребляемая мощность, кВт")
    n_rpm: float | None = Field(None, description="частота вращения, об/мин")
    curve_qh: list[list[float]] = Field(default_factory=list)
    curve_qeta: list[list[float]] = Field(default_factory=list)
    curve_source: PumpCurveSource | None = None

    @field_validator("curve_qh", "curve_qeta")
    @classmethod
    def validate_curve_points(
        cls, points: list[list[float]], info: ValidationInfo
    ) -> list[list[float]]:
        seen = set()
        for point in points:
            if len(point) != 2 or not all(math.isfinite(value) for value in point):
                raise ValueError("Точка характеристики должна содержать два конечных числа")
            q, value = point
            if q < 0 or q in seen or value < 0:
                raise ValueError("Подача неотрицательна и уникальна; ордината неотрицательна")
            if info.field_name == "curve_qeta" and value > 1:
                raise ValueError("КПД характеристики задаётся долей от 0 до 1, не процентами")
            seen.add(q)
        return points


class MotorSpec(BaseModel):
    model: str = ""
    synchronous: bool = False
    p_nom: float | None = Field(None, description="ном. мощность на валу, кВт")
    eta_nom: float | None = Field(None, description="ном. КПД ЭД, о.е.")
    cos_phi: float | None = None
    voltage_kv: float | None = None
    i_nom: float | None = None
    n_rpm: float | None = None

    @property
    def alpha(self) -> float:
        """Коэф. α для (26): до 2 у синхронных, ~1 у асинхронных."""
        return 2.0 if self.synchronous else 1.0


class RegimeMeasurement(BaseModel):
    """Измеренный режим (Таблица 8.2.1 Методики)."""

    measured_at: date | None = Field(None, description="дата измерения режима")
    rho: float = Field(..., description="плотность ρ, кг/м³")
    p_in: float = Field(..., description="давление приём p_вх, МПа")
    p_out: float = Field(..., description="давление выкид p_вых, МПа")
    q_day: float | None = Field(None, description="суточная перекачка Q_сут, м³/сут")
    t: float | None = Field(None, description="время работы за сутки T, ч")
    w: float | None = Field(None, description="суточный расход ЭЭ W, кВт·ч/сут")
    q_fact: float | None = Field(None, description="фактич. подача Q, м³/ч (= Q_сут/T)")
    p_electric: float | None = Field(None, description="активная мощность P_эл, кВт")
    power_daily_reported: float | None = Field(
        None, description="мощность из суточного отчёта, база усреднения не подтверждена, кВт"
    )
    nu: float | None = Field(None, description="вязкость ν, сСт")
    p_bg: float | None = Field(None, description="давление на БГ p_БГ, МПа (КНС)")
    t_year: float | None = Field(None, description="годовая наработка T_год, ч")

    def flow(self) -> float:
        """Подача Q, м³/ч: измеренная или Q_сут/T (формула 7)."""
        if self.q_fact is not None:
            return self.q_fact
        if self.q_day is not None and self.t:
            return self.q_day / self.t
        raise ValueError("нет данных для подачи Q (нужны q_fact или q_day+t)")


class ReferenceOutputs(BaseModel):
    """Эталонные результаты из «… расчет.xlsx»/отчёта — для сверки."""

    h_fact: float | None = None  # напор фактический, м
    h_due: float | None = None  # напор должный, м
    eta_fact: float | None = None  # КПД НА факт, о.е.
    eta_nom: float | None = None  # КПД НА номинальный, о.е.
    sec_fact: float | None = None  # УРЭ факт, кВт·ч/м³
    sec_calc: float | None = None  # УРЭ расчётный, кВт·ч/м³
    load_factor: float | None = None  # K_з
    p_hydraulic: float | None = None  # Р_гидр, кВт
    p_electric: float | None = None  # Р_эл, кВт
    eta_motor_real: float | None = None  # η_ЭД расчётный, о.е.
    eta_pump: float | None = None  # η_насоса расчётный, о.е.
    dw_efficiency: float | None = None  # ΔW_кпд, кВт·ч/год
    dw_throttle: float | None = None  # ΔW_дрос, кВт·ч/год
    dw_hydraulic: float | None = None  # гидравлические потери, кВт·ч/год
    t_year: float | None = None  # T_год, ч


class TransmissionSpec(BaseModel):
    """Механическая передача между двигателем и насосом."""

    model: str | None = None
    ratio: float | None = None
    efficiency: float | None = 1.0


class EquipmentData(BaseModel):
    """Полные паспортные данные агрегата (насос, ЭД, передача, ПЧ).

    Один и тот же контракт описывает паспорт из БД, ручной ввод оператора и
    временный сценарий: значения хранятся как есть, без подстановки «типовых».
    """

    pump: PumpSpec = Field(default_factory=PumpSpec)
    motor: MotorSpec = Field(default_factory=MotorSpec)
    transmission: TransmissionSpec = Field(
        default_factory=lambda: TransmissionSpec(efficiency=None)
    )
    vfd: bool = False

    @model_validator(mode="after")
    def validate_input_ranges(self) -> EquipmentData:
        """Правила ВВОДА ручных данных; чтение из БД идёт через model_construct."""
        positive = {
            "подача Q_ном": self.pump.q_nom,
            "напор H_ном": self.pump.h_nom,
            "мощность насоса P_ном": self.pump.power_nom,
            "обороты насоса": self.pump.n_rpm,
            "мощность ЭД P_ном": self.motor.p_nom,
            "напряжение ЭД": self.motor.voltage_kv,
            "ток ЭД": self.motor.i_nom,
            "обороты ЭД": self.motor.n_rpm,
            "передаточное число передачи": self.transmission.ratio,
        }
        for label, value in positive.items():
            if value is not None and (not math.isfinite(value) or value <= 0):
                raise ValueError(f"{label} задаётся положительным конечным числом")
        for label, value in (
            ("КПД насоса", self.pump.eta_nom),
            ("КПД ЭД", self.motor.eta_nom),
            ("КПД передачи", self.transmission.efficiency),
        ):
            if value is not None and (not math.isfinite(value) or not 0 < value <= 1):
                raise ValueError(f"{label} задаётся долей в интервале (0, 1]")
        cos_phi = self.motor.cos_phi
        if cos_phi is not None and (not math.isfinite(cos_phi) or abs(cos_phi) > 1):
            raise ValueError("cos φ должен быть конечным числом от −1 до 1")
        return self


class AggregateSpec(BaseModel):
    id: str
    technical_place_code: str = "main"
    role: str = "работа"  # работа | резерв
    pump: PumpSpec = Field(default_factory=lambda: PumpSpec())
    motor: MotorSpec = Field(default_factory=lambda: MotorSpec())
    transmission: TransmissionSpec = Field(default_factory=TransmissionSpec)
    vfd: bool = False
    eta_pump_due: float | None = None  # должный КПД насоса при рабочей подаче (с кривой Q-η)
    h_pump_due: float | None = None  # должный напор при рабочей подаче, м (с кривой Q-H)
    runtime_total_h: float | None = None  # наработка с начала эксплуатации, ч
    regime: RegimeMeasurement | None = None
    reference: ReferenceOutputs | None = None

    def nominal_efficiency(self, eta_vfd: float = 0.97) -> float | None:
        """η_ном = η_ЭД.ном · η_нас.ном · η_тр · [η_пч] (14)/(15)."""
        if (
            self.pump.eta_nom is None
            or self.motor.eta_nom is None
            or self.transmission.efficiency is None
        ):
            return None
        eta = self.motor.eta_nom * self.pump.eta_nom * self.transmission.efficiency
        if self.vfd:
            eta *= eta_vfd
        return eta


class ObjectSpec(BaseModel):
    id: str
    name: str
    ngdu: str | None = None  # НГДУ: без подтверждённого НГДУ объект в БД не переносится
    is_example: bool = False  # Пример для верификации, не показывать как рабочий объект.
    operator_visible: bool = True  # Показывать оператору; исторические справочные — false.
    water_type: WaterType = WaterType.fresh
    branch: Branch = Branch.kns
    density: float | None = None  # плотность закачиваемого агента объекта, кг/м³
    source: str = ""  # откуда собран спец (файл/ручной ввод)
    telemetry: dict[str, Any] = Field(default_factory=dict)
    technical_places: dict[str, str] = Field(default_factory=dict)
    aggregates: list[AggregateSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_group_bindings(self) -> "ObjectSpec":
        known = {"main", *self.technical_places}
        missing = {aggregate.technical_place_code for aggregate in self.aggregates} - known
        if missing:
            raise ValueError(f"Не описаны гидравлические группы: {', '.join(sorted(missing))}")
        ids = [aggregate.id for aggregate in self.aggregates]
        if len(ids) != len(set(ids)):
            raise ValueError("ID агрегатов должны быть уникальны внутри объекта")
        return self

    def aggregate(self, agg_id: str) -> AggregateSpec:
        for a in self.aggregates:
            if a.id == agg_id:
                return a
        raise KeyError(f"Агрегат {agg_id!r} не найден в объекте {self.id}")

    def working_aggregates(self) -> list[AggregateSpec]:
        return [a for a in self.aggregates if a.regime is not None]


def _plants_dir() -> Path:
    from .config import project_root

    return project_root() / "config" / "plants"


def save_object_spec(spec: ObjectSpec, path: Path | None = None) -> Path:
    """Сохранить спец в нативный YAML-формат."""
    path = path or (_plants_dir() / f"{spec.id}.yaml")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(
            spec.model_dump(mode="json", exclude_none=True), f, allow_unicode=True, sort_keys=False
        )
    return path


def load_object_spec(plant_id: str) -> ObjectSpec:
    """Загрузить нативный YAML-паспорт объекта."""
    path = _plants_dir() / f"{plant_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Паспорт объекта не найден: {path}")
    with path.open(encoding="utf-8") as f:
        return ObjectSpec(**yaml.safe_load(f))
