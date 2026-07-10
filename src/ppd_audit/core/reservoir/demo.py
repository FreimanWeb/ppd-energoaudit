"""Демо-заглушка отклика пласта: равномерная связность (нет данных о геологии)."""

from __future__ import annotations

from .base import ReservoirInput, ReservoirResult


class DemoReservoir:
    """Заглушка: равномерная связность 1/N_инж, эффективная закачка = средняя."""
    name = "demo"

    def fit(self, data: ReservoirInput) -> ReservoirResult:
        n = len(data.injectors) or 1
        conn = {prod: {inj: round(1.0 / n, 4) for inj in data.injectors}
                for prod in data.producers}
        eff = {inj: (sum(s) / len(s) if s else 0.0)
               for inj, s in data.injection.items()}
        return ReservoirResult(connectivity=conn, effective_injection=eff,
                               model=self.name, estimate=True,
                               note="равномерная связность — оценка без геологии/CRM")
