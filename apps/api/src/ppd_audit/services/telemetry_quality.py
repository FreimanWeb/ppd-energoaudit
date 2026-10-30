"""Оценка пригодности телеметрийного режима для инженерных и экономических выводов."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


_RECONCILIATION_TOLERANCE = 0.05


@dataclass(frozen=True)
class QualityIssue:
    code: str
    message: str
    severity: Literal["warning", "error"]


@dataclass(frozen=True)
class TelemetryQuality:
    status: Literal["ready", "assumptions", "unfit"]
    issues: tuple[QualityIssue, ...]
    basis: dict[str, str]

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues)

    @property
    def allows_economic_conclusions(self) -> bool:
        return self.status != "unfit"


def assess_telemetry_quality(
    *,
    eta_unit: float,
    uses_daily_flow: bool,
    uses_daily_power: bool,
    energy_kwh: float | None = None,
    integrated_energy_kwh: float | None = None,
    runtime_hours: float | None = None,
    powered_hours: float | None = None,
    q_day_m3: float | None = None,
    integrated_flow_m3: float | None = None,
) -> TelemetryQuality:
    """Оценить физическую допустимость и basis показателей выбранного снимка."""
    basis = {
        "pressure": "p_вх/p_вых в момент снимка",
        "flow": "Q_сут / T_сут" if uses_daily_flow else "Q в момент снимка",
        "power": "W_сут / T_сут" if uses_daily_power else "P_эл в момент снимка",
    }
    issues: list[QualityIssue] = []
    if uses_daily_flow:
        issues.append(
            QualityIssue(
                "daily_flow_basis",
                "Подача принята как Q_сут / T_сут: мгновенный Q отсутствует.",
                "warning",
            )
        )
    if uses_daily_power:
        issues.append(
            QualityIssue(
                "daily_power_basis",
                "Мощность принята как W_сут / T_сут, а не как значение выбранного снимка.",
                "warning",
            )
        )
    if eta_unit > 1.0:
        issues.append(
            QualityIssue(
                "efficiency_above_one",
                "КПД выше 1: гидравлическая мощность больше электрической.",
                "error",
            )
        )
    _append_mismatch(
        issues,
        "energy_mismatch",
        "W_сут не совпадает с интегралом 30-минутной мощности.",
        energy_kwh,
        integrated_energy_kwh,
    )
    _append_mismatch(
        issues,
        "runtime_mismatch",
        "Моточасы не совпадают с длительностью положительной мощности.",
        runtime_hours,
        powered_hours,
    )
    _append_mismatch(
        issues,
        "daily_flow_mismatch",
        "Q_сут не совпадает с интегралом мгновенного расхода.",
        q_day_m3,
        integrated_flow_m3,
    )
    if any(issue.severity == "error" for issue in issues):
        status: Literal["ready", "assumptions", "unfit"] = "unfit"
    elif issues:
        status = "assumptions"
    else:
        status = "ready"
    return TelemetryQuality(status=status, issues=tuple(issues), basis=basis)


def _append_mismatch(
    issues: list[QualityIssue],
    code: str,
    message: str,
    expected: float | None,
    observed: float | None,
) -> None:
    if expected is None or observed is None or expected == 0:
        return
    if abs(expected - observed) / abs(expected) > _RECONCILIATION_TOLERANCE:
        issues.append(QualityIssue(code, message, "error"))
