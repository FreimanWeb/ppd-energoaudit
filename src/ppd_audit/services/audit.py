"""Energy audit application service."""

from __future__ import annotations

from ..core.audit import AuditResult, audit_aggregate
from ..spec import ObjectSpec


def run_energy_audit(spec: ObjectSpec, aggregate_id: str | None = None) -> AuditResult:
    """Запустить аудит выбранного агрегата без привязки к transport contract."""
    aggregates = spec.working_aggregates()
    if not aggregates:
        raise ValueError(f"у объекта {spec.id} нет агрегатов с измеренным режимом")
    aggregate = spec.aggregate(aggregate_id) if aggregate_id else aggregates[0]
    return audit_aggregate(aggregate, spec.branch)
