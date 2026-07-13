"""Правила диагностики для разных принципов действия насосов."""

from __future__ import annotations

from dataclasses import dataclass

from ..spec import PumpKind


@dataclass(frozen=True)
class PumpAuditProfile:
    name: str
    uses_qh_curve: bool
    uses_qeta_curve: bool
    curve_diagnostics_reason: str


CENTRIFUGAL = PumpAuditProfile(
    name="centrifugal",
    uses_qh_curve=True,
    uses_qeta_curve=True,
    curve_diagnostics_reason="",
)

POSITIVE_DISPLACEMENT = PumpAuditProfile(
    name="positive_displacement",
    uses_qh_curve=False,
    uses_qeta_curve=False,
    curve_diagnostics_reason="объёмный насос: диагностика по кривым Q-H и Q-η неприменима",
)


def profile_for(kind: PumpKind) -> PumpAuditProfile:
    if kind == PumpKind.positive_displacement:
        return POSITIVE_DISPLACEMENT
    return CENTRIFUGAL
