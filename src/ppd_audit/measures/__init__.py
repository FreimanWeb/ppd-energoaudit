"""Реестр мероприятий и ТЭО."""

from .economics import (
    DEFAULT_DISCOUNT_RATE,
    DEFAULT_HORIZON_YEARS,
    CashflowYear,
    HorizonEvaluation,
    InjectionProfile,
    build_annual_profile,
    evaluate_horizon,
    internal_rate_of_return,
    net_present_value,
    payback_from_cumulative,
    suggest_measures_over_horizon,
)
from .registry import CATALOG, Measure, MeasureClass, MeasureEvaluation, evaluate, suggest_measures


__all__ = [
    "CATALOG",
    "Measure",
    "MeasureClass",
    "MeasureEvaluation",
    "evaluate",
    "suggest_measures",
    # экономика на горизонте с учётом прогнозного профиля закачки
    "CashflowYear",
    "HorizonEvaluation",
    "InjectionProfile",
    "DEFAULT_DISCOUNT_RATE",
    "DEFAULT_HORIZON_YEARS",
    "build_annual_profile",
    "evaluate_horizon",
    "internal_rate_of_return",
    "net_present_value",
    "payback_from_cumulative",
    "suggest_measures_over_horizon",
]
