"""Схемы данных (pydantic v2) — паспорта, режимы, конфиги.

Схемы — единый контракт между слоями: ingest/quality наполняют ряды, ядро читает
паспорта и режимы. Каждое поле имеет единицу измерения в комментарии.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


# --- Справочники / паспорта ----------------------------------------------

class FluidProps(BaseModel):
    """Свойства жидкости (config/fluids.yaml или паспорт объекта)."""
    rho: float = Field(..., description="плотность, кг/м³")
    nu: float = Field(..., description="кинематическая вязкость, сСт")
    estimate: bool = False
    note: str = ""


class PumpPassport(BaseModel):
    """Паспорт насоса."""
    model: str
    q_nom: float = Field(..., description="номинальная подача, м³/ч")
    h_nom: float = Field(..., description="номинальный напор, м")
    eta_nom: float = Field(..., description="номинальный КПД насоса, о.е.")
    power_consumed_nom: Optional[float] = Field(None, description="потребляемая мощность, кВт")
    overhaul: Optional[str] = None
    curve_qh: list[list[float]] = Field(default_factory=list, description="[[Q, H], ...]")
    curve_qeta: list[list[float]] = Field(default_factory=list, description="[[Q, η], ...]")


class MotorPassport(BaseModel):
    """Паспорт электродвигателя."""
    model: str
    kind: Literal["асинхронный", "синхронный"] = "асинхронный"
    p_nom: float = Field(..., description="номинальная мощность на валу, кВт")
    eta_nom: float = Field(..., description="номинальный КПД ЭД, о.е.")
    voltage_kv: Optional[float] = None
    cos_phi: Optional[float] = None
    alpha: float = Field(1.0, description="коэф. α для формулы (26): асинхр. 0,5..1, синхр. до 2")


class Aggregate(BaseModel):
    """Насосный агрегат: насос + ЭД + трансмиссия + ПЧ."""
    id: str
    role: Literal["работа", "резерв"] = "работа"
    pump: Optional[PumpPassport] = None
    motor: Optional[MotorPassport] = None
    transmission_eff: float = Field(1.0, description="η_тр")
    vfd: bool = False


# --- Режим (вход расчётного ядра) ----------------------------------------

class RegimeInputs(BaseModel):
    """Параметры режима работы агрегата — вход формул (7)-(18).

    Минимально необходимый набор по Таблице 8.2.1 Методики.
    """
    q: float = Field(..., description="подача мгновенная Q, м³/ч")
    rho: float = Field(..., description="плотность ρ, кг/м³")
    p_in: float = Field(..., description="давление на приёме p_вх, МПа")
    p_out: float = Field(..., description="давление на выкиде p_вых, МПа")

    # Энергия/наработка — для УРЭ факт и годовых потерь
    w: Optional[float] = Field(None, description="расход ЭЭ за период W, кВт·ч")
    t: Optional[float] = Field(None, description="время работы T за период, ч")
    p_electric: Optional[float] = Field(None, description="активная мощность P_эл, кВт")

    q_day: Optional[float] = Field(None, description="суточный объём Q_сут, м³")
    q_year: Optional[float] = Field(None, description="годовой объём Q_год, м³")
    t_year: Optional[float] = Field(None, description="годовая наработка T_год, ч")

    # Доп. для КНС / перекачки
    p_bg: Optional[float] = Field(None, description="давление на БГ p_БГ, МПа (КНС)")
    p_opt: Optional[float] = Field(None, description="оптимальное давление p_опт, МПа")


# --- Конфиги -------------------------------------------------------------

class Plant(BaseModel):
    """Паспорт объекта (config/plants/<id>.yaml)."""
    meta: dict
    fluid: dict
    aggregates: list[dict]
    reference_regime: Optional[dict] = None
    telemetry: Optional[dict] = None

    def aggregate(self, agg_id: str) -> Aggregate:
        """Вернуть типизированный агрегат по id."""
        for a in self.aggregates:
            if a.get("id") == agg_id:
                return Aggregate(**a)
        raise KeyError(f"Агрегат {agg_id!r} не найден в объекте {self.meta.get('id')}")


class Constraints(BaseModel):
    """Технологические ограничения (config/constraints.yaml)."""
    pressure_limits: dict = Field(default_factory=dict)
    vfd: dict = Field(default_factory=dict)
    operation: dict = Field(default_factory=dict)
    wells: dict = Field(default_factory=dict)
    kpi: dict = Field(default_factory=dict)
    economics: dict = Field(default_factory=dict)
