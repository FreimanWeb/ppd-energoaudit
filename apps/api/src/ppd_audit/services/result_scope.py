"""Статус применимости суточных и годовых результатов."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.audit import AuditResult


@dataclass(frozen=True)
class ResultScope:
    daily_kpi_is_fact: bool
    daily_pressure_coverage_is_complete: bool
    annual_runtime_hours: float
    annual_runtime_is_assumed: bool


def result_scope(
    audit: AuditResult,
    *,
    daily_pressure_coverage_is_complete: bool = True,
) -> ResultScope:
    """Отделить измеренный суточный KPI от сценарной годовой оценки."""
    if audit.spec is None or audit.spec.regime is None:
        raise ValueError("Для определения базы нужен исходный режим агрегата")
    regime = audit.spec.regime
    return ResultScope(
        daily_kpi_is_fact=regime.w is not None and regime.q_day not in (None, 0),
        daily_pressure_coverage_is_complete=daily_pressure_coverage_is_complete,
        annual_runtime_hours=audit.annual_runtime_hours,
        annual_runtime_is_assumed=audit.annual_runtime_is_assumed,
    )
