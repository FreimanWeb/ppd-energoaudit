"""Статус применимости суточных и годовых результатов."""

from __future__ import annotations

from dataclasses import dataclass

from ..spec import RegimeMeasurement


@dataclass(frozen=True)
class ResultScope:
    daily_kpi_is_fact: bool
    daily_pressure_coverage_is_complete: bool
    annual_runtime_hours: float
    annual_runtime_is_assumed: bool


def result_scope(
    regime: RegimeMeasurement,
    annual_runtime: float | None,
    *,
    daily_pressure_coverage_is_complete: bool = True,
) -> ResultScope:
    """Отделить измеренный суточный KPI от сценарной годовой оценки."""
    return ResultScope(
        daily_kpi_is_fact=regime.w is not None and regime.q_day not in (None, 0),
        daily_pressure_coverage_is_complete=daily_pressure_coverage_is_complete,
        annual_runtime_hours=annual_runtime if annual_runtime is not None else 8760.0,
        annual_runtime_is_assumed=annual_runtime is None,
    )
