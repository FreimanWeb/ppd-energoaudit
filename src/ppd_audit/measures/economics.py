"""Экономика мероприятий на горизонте с учётом прогнозного профиля закачки.

ЧТО ЭТО: надстройка над ``registry.evaluate``, которая превращает «плоскую»
годовую оценку (эффект текущего режима × T_год, один и тот же каждый год) в
денежный поток по годам горизонта. Годовой энергоэффект каждого года
масштабируется отношением прогнозного объёма закачки этого года к объёму
базового года::

    ΔW(k) = ΔW_база · (Q_год(k) / Q_год.база) ** n

где ``n`` — ``Measure.volume_exponent``. По умолчанию n = 1: и дросселирование
(45), и потери КПД (44), и составляющие мощностной декомпозиции (39)-(42) дают
экономию, пропорциональную перекачанному объёму — потерянная мощность ΔP ∝ Q,
а годовая энергия = ΔP · T_год, то есть ∝ Q · T_год = Q_год. Если у конкретного
мероприятия зависимость иная (например, потери холостого хода ЭД слабо зависят
от подачи, а трение в трубопроводе — как Q³), это задаётся ``volume_exponent``
у самого мероприятия, а не правкой этого модуля.

Дальше по годовому потоку считаются: NPV при заданной ставке дисконтирования,
IRR (бисекция), простая и дисконтированная окупаемость — обе с линейной
интерполяцией внутри года, чтобы не округлять всё до целых лет.

ЧЕМ ЭТО НЕ ЯВЛЯЕТСЯ: источник профиля закачки — статистическая экстраполяция
тренда из ``core/reservoir/forecast.py``, а НЕ гидродинамическая модель пласта
и не план ГТМ. Поэтому все результаты помечены ``estimate=True``: это
индикативная оценка для ранжирования мероприятий, а не проектное ТЭО. Когда в
проекте появится план закачки или нормальная модель пласта — подставлять его
годовые объёмы в ``InjectionProfile.annual_m3``, интерфейс не меняется.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..core.audit import AuditResult
from .registry import CATALOG, Measure, evaluate


DAYS_PER_YEAR = 365.0
DEFAULT_DISCOUNT_RATE = 0.15  # ставка дисконтирования по умолчанию, доля/год
DEFAULT_HORIZON_YEARS = 3  # совпадает с дефолтом вкладки прогноза (36 месяцев)
DEFAULT_TARIFF = 4.68  # тыс. руб/МВт·ч → руб/кВт·ч, как в registry.evaluate


# ────────────────────────── профиль закачки ──────────────────────────


@dataclass(frozen=True)
class InjectionProfile:
    """Годовые объёмы закачки на горизонте + объём базового года.

    ``base_annual_m3`` — Q_год того режима, по которому посчитан аудит
    (Q · T_год). Именно к нему нормируются прогнозные годы, поэтому профиль
    всегда согласован с базовой оценкой эффекта из ``registry``.
    """

    base_annual_m3: float
    annual_m3: list[float]
    lower_annual_m3: list[float] | None = None
    upper_annual_m3: list[float] | None = None
    method: str = "linear-trend"
    estimate: bool = True
    extrapolated_tail: bool = False  # горизонт длиннее прогноза, хвост продлён
    note: str = ""

    @property
    def horizon_years(self) -> int:
        return len(self.annual_m3)

    @property
    def total_m3(self) -> float:
        return round(sum(self.annual_m3), 2)

    def ratio(self, year_index: int) -> float:
        """Q_год(k) / Q_год.база; 1.0, если база неизвестна или нулевая."""
        if self.base_annual_m3 <= 0:
            return 1.0
        return self.annual_m3[year_index] / self.base_annual_m3

    def ratios(self) -> list[float]:
        return [self.ratio(i) for i in range(self.horizon_years)]

    @classmethod
    def flat(cls, base_annual_m3: float, horizon_years: int) -> InjectionProfile:
        """Профиль «как сейчас»: объём закачки постоянен весь горизонт.

        Нужен, когда телеметрии не хватает на прогноз, но экономику на
        горизонте показать всё равно надо — тогда NPV считается честно, а
        роста/спада закачки просто нет.
        """
        if horizon_years < 1:
            raise ValueError("horizon_years должен быть ≥1")
        return cls(
            base_annual_m3=base_annual_m3,
            annual_m3=[round(base_annual_m3, 2)] * horizon_years,
            method="flat",
            note="Прогноз не строился: объём закачки принят постоянным на весь горизонт.",
        )


def build_annual_profile(
    period_values: list[float],
    *,
    period_days: int,
    horizon_years: int,
    base_annual_m3: float,
    lower_values: list[float] | None = None,
    upper_values: list[float] | None = None,
    method: str = "linear-trend",
    note: str = "",
) -> InjectionProfile:
    """Свернуть прогноз по периодам (м³/период) в годовые объёмы (м³/год).

    Прогноз считается кусочно-постоянным по суточному расходу внутри периода,
    поэтому периоды любой длины (сутки/неделя/месяц) корректно ложатся на
    календарные годы по 365 суток. Если горизонт длиннее прогноза, хвост
    продлевается последним прогнозным периодом, и это помечается
    ``extrapolated_tail=True`` — молча экстраполировать нельзя.
    """
    if period_days < 1:
        raise ValueError("period_days должен быть ≥1")
    if horizon_years < 1:
        raise ValueError("horizon_years должен быть ≥1")
    if not period_values:
        raise ValueError("пустой прогнозный ряд")

    def roll(values: list[float]) -> list[float]:
        out: list[float] = []
        last = len(values) - 1
        for year in range(horizon_years):
            total = 0.0
            for day in range(int(year * DAYS_PER_YEAR), int((year + 1) * DAYS_PER_YEAR)):
                total += values[min(day // period_days, last)] / period_days
            out.append(round(total, 2))
        return out

    needed_periods = math.ceil(horizon_years * DAYS_PER_YEAR / period_days)
    return InjectionProfile(
        base_annual_m3=base_annual_m3,
        annual_m3=roll(period_values),
        lower_annual_m3=roll(lower_values) if lower_values else None,
        upper_annual_m3=roll(upper_values) if upper_values else None,
        method=method,
        extrapolated_tail=needed_periods > len(period_values),
        note=note,
    )


# ────────────────────────── денежный поток ──────────────────────────


@dataclass(frozen=True)
class CashflowYear:
    year: int  # 1..horizon
    injection_m3: float  # прогнозный объём закачки за этот год
    volume_ratio: float  # Q_год(k)/Q_год.база
    energy_saving_kwh: float
    money_saving_krub: float
    discount_factor: float
    discounted_krub: float
    cumulative_krub: float  # накопленная экономия без дисконта
    cumulative_discounted_krub: float


@dataclass(frozen=True)
class HorizonEvaluation:
    """ТЭО мероприятия на горизонте: поток по годам + NPV/IRR/окупаемость."""

    measure_id: str
    name: str
    cls: str
    capex_krub: float
    base_energy_saving_kwh: float  # эффект базового года (как в registry)
    base_money_saving_krub: float
    volume_exponent: float
    discount_rate: float
    years: list[CashflowYear]
    total_energy_kwh: float
    total_money_krub: float
    total_discounted_krub: float
    npv_krub: float | None
    irr: float | None  # доля/год, напр. 0.42 = 42 %
    payback_years: float | None  # простая, по накопленному потоку
    discounted_payback_years: float | None
    estimate: bool = True
    note: str = ""

    @property
    def horizon_years(self) -> int:
        return len(self.years)


def net_present_value(capex_krub: float, flows_krub: list[float], rate: float) -> float:
    """NPV = Σ CF_k/(1+r)^k − CAPEX. CAPEX относится к году 0, потоки — к 1..N."""
    if rate <= -1.0:
        raise ValueError("ставка дисконтирования должна быть > −100 %")
    discounted = sum(cf / (1.0 + rate) ** (k + 1) for k, cf in enumerate(flows_krub))
    return round(discounted - capex_krub, 2)


def internal_rate_of_return(
    capex_krub: float,
    flows_krub: list[float],
    *,
    lo: float = -0.9,
    hi: float = 10.0,
    tol: float = 1e-7,
    max_iter: int = 200,
) -> float | None:
    """IRR методом бисекции.

    ``None``, если IRR не определена: нет CAPEX (мероприятие без вложений —
    окупается мгновенно), нет положительных потоков, или на отрезке
    [lo, hi] знак NPV не меняется (проект не выходит в ноль даже при −90 %,
    либо выходит при ставке выше 1000 % — в обоих случаях число бессмысленно).
    """
    if capex_krub <= 0 or not flows_krub or all(cf <= 0 for cf in flows_krub):
        return None

    def npv_at(rate: float) -> float:
        return sum(cf / (1.0 + rate) ** (k + 1) for k, cf in enumerate(flows_krub)) - capex_krub

    f_lo, f_hi = npv_at(lo), npv_at(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        f_mid = npv_at(mid)
        if abs(f_mid) < tol:
            return round(mid, 4)
        if f_lo * f_mid <= 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return round((lo + hi) / 2.0, 4)


def payback_from_cumulative(cumulative_krub: list[float], capex_krub: float) -> float | None:
    """Год, в котором накопленный поток перекрыл CAPEX (с долей внутри года).

    ``0.0`` — мероприятие без CAPEX (окупается сразу), ``None`` — за горизонт
    так и не окупилось.
    """
    if capex_krub <= 0:
        return 0.0
    previous = 0.0
    for index, cumulative in enumerate(cumulative_krub):
        if cumulative >= capex_krub:
            gain = cumulative - previous
            fraction = (capex_krub - previous) / gain if gain > 0 else 0.0
            return round(index + fraction, 2)
        previous = cumulative
    return None


def evaluate_horizon(
    measure: Measure,
    audit: AuditResult,
    profile: InjectionProfile,
    *,
    tariff: float = DEFAULT_TARIFF,
    discount_rate: float = DEFAULT_DISCOUNT_RATE,
) -> HorizonEvaluation:
    """ТЭО одного мероприятия на горизонте профиля закачки."""
    base = evaluate(measure, audit, tariff)
    exponent = getattr(measure, "volume_exponent", 1.0)

    years: list[CashflowYear] = []
    cumulative = 0.0
    cumulative_discounted = 0.0
    for index in range(profile.horizon_years):
        ratio = profile.ratio(index)
        scale = ratio**exponent if ratio > 0 else 0.0
        energy = base.energy_saving_kwh * scale
        money = energy * tariff / 1000.0
        factor = 1.0 / (1.0 + discount_rate) ** (index + 1)
        discounted = money * factor
        cumulative += money
        cumulative_discounted += discounted
        years.append(
            CashflowYear(
                year=index + 1,
                injection_m3=round(profile.annual_m3[index], 2),
                volume_ratio=round(ratio, 4),
                energy_saving_kwh=round(energy, 1),
                money_saving_krub=round(money, 1),
                discount_factor=round(factor, 4),
                discounted_krub=round(discounted, 1),
                cumulative_krub=round(cumulative, 1),
                cumulative_discounted_krub=round(cumulative_discounted, 1),
            )
        )

    flows = [y.money_saving_krub for y in years]
    capex = base.capex_krub
    return HorizonEvaluation(
        measure_id=base.measure_id,
        name=base.name,
        cls=base.cls,
        capex_krub=capex,
        base_energy_saving_kwh=base.energy_saving_kwh,
        base_money_saving_krub=base.money_saving_krub,
        volume_exponent=exponent,
        discount_rate=discount_rate,
        years=years,
        total_energy_kwh=round(sum(y.energy_saving_kwh for y in years), 1),
        total_money_krub=round(sum(flows), 1),
        total_discounted_krub=round(sum(y.discounted_krub for y in years), 1),
        npv_krub=net_present_value(capex, flows, discount_rate),
        irr=internal_rate_of_return(capex, flows),
        payback_years=payback_from_cumulative([y.cumulative_krub for y in years], capex),
        discounted_payback_years=payback_from_cumulative(
            [y.cumulative_discounted_krub for y in years], capex
        ),
        note=(
            "Годовой эффект масштабирован прогнозным объёмом закачки "
            f"(показатель {exponent:g}); профиль — {profile.method}, "
            "статистическая экстраполяция, не гидродинамическая модель пласта."
        ),
    )


def suggest_measures_over_horizon(
    audit: AuditResult,
    profile: InjectionProfile,
    *,
    tariff: float = DEFAULT_TARIFF,
    discount_rate: float = DEFAULT_DISCOUNT_RATE,
    catalog: list[Measure] | None = None,
) -> list[HorizonEvaluation]:
    """Применимые мероприятия с ТЭО на горизонте, по убыванию суммарного эффекта.

    Отбор применимости и порог «эффект > 0» — те же, что в
    ``registry.suggest_measures``, чтобы список мероприятий не расходился
    между режимами «текущий режим» и «прогноз».
    """
    out: list[HorizonEvaluation] = []
    for measure in catalog if catalog is not None else CATALOG:
        if measure.applicable_fn and not measure.applicable_fn(audit):
            continue
        ev = evaluate_horizon(
            measure, audit, profile, tariff=tariff, discount_rate=discount_rate
        )
        if ev.base_energy_saving_kwh > 0:
            out.append(ev)
    return sorted(out, key=lambda e: e.total_energy_kwh, reverse=True)
