"""Универсальное нормализованное описание объекта ППД (источник-независимое).

Иерархия:  ObjectSpec → AggregateSpec → {PumpSpec, MotorSpec, RegimeMeasurement, ReferenceOutputs}

Ядро формул (7)-(47) работает с этими структурами и не знает о формате исходников.
Спец собирается из любого источника: yaml-паспорт объекта, парсер «… расчет.xlsx»
или ручной ввод (см. spec_io.py).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class WaterType(str, Enum):
    fresh = "пресная"
    aggressive = "агрессивная"
    formation = "пластовая"


class PumpKind(str, Enum):
    centrifugal = "центробежный"          # ЦНС и т.п. — полная диагностика кривых (28)-(42)
    positive_displacement = "объёмный"    # поршневой/плунжерный — без кривых Q-H


class Branch(str, Enum):
    kns = "кнс"                # высоконапорная закачка (p_БГ есть), декомпозиция (31)-(36)
    transfer = "перекачка"     # перекачка нефти/эмульсии, декомпозиция (37)-(42)


# Ключевые слова в названии насоса → объёмный (плунжерный/поршневой) тип.
_POSITIVE_DISPLACEMENT_HINTS = ("нпж", "ст-а", "син", "плунж", "поршн", "тнг", "пт ", "нп ")


def infer_pump_kind(model: str, n_rpm: Optional[float] = None) -> PumpKind:
    """Эвристика типа насоса по названию/оборотам (ЦНС=центробежный, НПЖ/СИН=объёмный)."""
    m = (model or "").lower().replace("ё", "е")
    if any(h in m for h in _POSITIVE_DISPLACEMENT_HINTS):
        return PumpKind.positive_displacement
    if n_rpm is not None and n_rpm < 800:   # плунжерные тихоходны (~300 об/мин)
        return PumpKind.positive_displacement
    return PumpKind.centrifugal


# Серии синхронных двигателей (влияет на α в (26): синхронный → α=2).
_SYNCHRONOUS_MOTOR_HINTS = ("стд", "сдн", "сд-", "вдс", "сднз")


def infer_motor_synchronous(model: str) -> bool:
    """Эвристика синхронности ЭД по серии (СТД/СДН… — синхронные; АИ/ВАО/5АИ — асинхронные)."""
    m = (model or "").lower().replace("ё", "е").replace(" ", "")
    return any(h in m for h in _SYNCHRONOUS_MOTOR_HINTS)


class PumpSpec(BaseModel):
    model: str = ""
    kind: PumpKind = PumpKind.centrifugal
    q_nom: Optional[float] = Field(None, description="ном. подача Q_ном, м³/ч")
    h_nom: Optional[float] = Field(None, description="ном. напор H_ном, м")
    eta_nom: Optional[float] = Field(None, description="ном. КПД насоса, о.е.")
    power_nom: Optional[float] = Field(None, description="потребляемая мощность, кВт")
    n_rpm: Optional[float] = Field(None, description="частота вращения, об/мин")
    curve_qh: list[list[float]] = Field(default_factory=list)
    curve_qeta: list[list[float]] = Field(default_factory=list)


class MotorSpec(BaseModel):
    model: str = ""
    synchronous: bool = False
    p_nom: Optional[float] = Field(None, description="ном. мощность на валу, кВт")
    eta_nom: Optional[float] = Field(None, description="ном. КПД ЭД, о.е.")
    cos_phi: Optional[float] = None
    voltage_kv: Optional[float] = None
    i_nom: Optional[float] = None
    n_rpm: Optional[float] = None

    @property
    def alpha(self) -> float:
        """Коэф. α для (26): до 2 у синхронных, ~1 у асинхронных."""
        return 2.0 if self.synchronous else 1.0


class RegimeMeasurement(BaseModel):
    """Измеренный режим (Таблица 8.2.1 Методики)."""
    rho: float = Field(..., description="плотность ρ, кг/м³")
    p_in: float = Field(..., description="давление приём p_вх, МПа")
    p_out: float = Field(..., description="давление выкид p_вых, МПа")
    q_day: Optional[float] = Field(None, description="суточная перекачка Q_сут, м³/сут")
    t: Optional[float] = Field(None, description="время работы за сутки T, ч")
    w: Optional[float] = Field(None, description="суточный расход ЭЭ W, кВт·ч/сут")
    q_fact: Optional[float] = Field(None, description="фактич. подача Q, м³/ч (= Q_сут/T)")
    p_electric: Optional[float] = Field(None, description="активная мощность P_эл, кВт")
    nu: Optional[float] = Field(None, description="вязкость ν, сСт")
    p_bg: Optional[float] = Field(None, description="давление на БГ p_БГ, МПа (КНС)")
    t_year: Optional[float] = Field(None, description="годовая наработка T_год, ч")

    def flow(self) -> float:
        """Подача Q, м³/ч: измеренная или Q_сут/T (формула 7)."""
        if self.q_fact is not None:
            return self.q_fact
        if self.q_day is not None and self.t:
            return self.q_day / self.t
        raise ValueError("нет данных для подачи Q (нужны q_fact или q_day+t)")


class ReferenceOutputs(BaseModel):
    """Эталонные результаты из «… расчет.xlsx»/отчёта — для сверки."""
    h_fact: Optional[float] = None        # напор фактический, м
    h_due: Optional[float] = None         # напор должный, м
    eta_fact: Optional[float] = None      # КПД НА факт, о.е.
    eta_nom: Optional[float] = None       # КПД НА номинальный, о.е.
    sec_fact: Optional[float] = None      # УРЭ факт, кВт·ч/м³
    sec_calc: Optional[float] = None      # УРЭ расчётный, кВт·ч/м³
    load_factor: Optional[float] = None   # K_з
    p_hydraulic: Optional[float] = None   # Р_гидр, кВт
    p_electric: Optional[float] = None    # Р_эл, кВт
    dw_efficiency: Optional[float] = None  # ΔW_кпд, кВт·ч/год
    dw_throttle: Optional[float] = None   # ΔW_дрос, кВт·ч/год
    t_year: Optional[float] = None        # T_год, ч


class AggregateSpec(BaseModel):
    id: str
    role: str = "работа"                  # работа | резерв
    pump: PumpSpec = Field(default_factory=PumpSpec)
    motor: MotorSpec = Field(default_factory=MotorSpec)
    transmission_eff: float = 1.0
    vfd: bool = False
    eta_pump_due: Optional[float] = None   # должный КПД насоса при рабочей подаче (с кривой Q-η)
    h_pump_due: Optional[float] = None     # должный напор при рабочей подаче, м (с кривой Q-H)
    regime: Optional[RegimeMeasurement] = None
    reference: Optional[ReferenceOutputs] = None

    def nominal_efficiency(self, eta_vfd: float = 0.97) -> Optional[float]:
        """η_ном = η_ЭД.ном · η_нас.ном · η_тр · [η_пч] (14)/(15)."""
        if self.pump.eta_nom is None or self.motor.eta_nom is None:
            return None
        eta = self.motor.eta_nom * self.pump.eta_nom * self.transmission_eff
        if self.vfd:
            eta *= eta_vfd
        return eta


class ObjectSpec(BaseModel):
    id: str
    name: str
    water_type: WaterType = WaterType.fresh
    branch: Branch = Branch.kns
    source: str = ""                      # откуда собран спец (файл/ручной ввод)
    aggregates: list[AggregateSpec] = Field(default_factory=list)

    def aggregate(self, agg_id: str) -> AggregateSpec:
        for a in self.aggregates:
            if a.id == agg_id:
                return a
        raise KeyError(f"Агрегат {agg_id!r} не найден в объекте {self.id}")

    def working_aggregates(self) -> list[AggregateSpec]:
        return [a for a in self.aggregates if a.regime is not None]
