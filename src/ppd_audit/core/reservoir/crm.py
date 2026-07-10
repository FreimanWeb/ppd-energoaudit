"""CRM-реализация отклика пласта (упрощённая, регрессионная).

Для каждой добывающей скважины оценивается матрица связностей λ_ij методом
наименьших квадратов: q_prod_j(t) ≈ Σ_i λ_ij · q_inj_i(t), с неотрицательностью
и нормировкой Σ_i λ_ij ≤ 1. Это статический аналог CRM (без динамики τ); полноценная
CRMP/CRMT подключается через тот же интерфейс ReservoirModel.
"""

from __future__ import annotations

import numpy as np

from .base import ReservoirInput, ReservoirResult


class CRMLite:
    """Регрессионная оценка связностей закачка→добыча (CRM-lite)."""
    name = "crm-lite"

    def fit(self, data: ReservoirInput) -> ReservoirResult:
        injs = data.injectors
        X = np.array([data.injection[i] for i in injs], dtype=float).T  # (T, Ninj)
        conn: dict[str, dict[str, float]] = {}
        for prod in data.producers:
            y = np.asarray(data.production.get(prod, []), dtype=float)
            if y.size != X.shape[0] or X.shape[0] < len(injs):
                conn[prod] = {i: round(1.0 / len(injs), 4) for i in injs}
                continue
            lam, *_ = np.linalg.lstsq(X, y, rcond=None)
            lam = np.clip(lam, 0.0, None)
            s = lam.sum()
            if s > 1.0:                     # нормировка Σλ ≤ 1 (физичность)
                lam = lam / s
            conn[prod] = {i: round(float(v), 4) for i, v in zip(injs, lam)}

        # эффективная закачка = средняя закачка, взвешенная суммарной связностью
        eff = {}
        for inj in injs:
            total_lambda = sum(conn[p].get(inj, 0.0) for p in data.producers)
            mean_inj = float(np.mean(data.injection[inj])) if data.injection[inj] else 0.0
            eff[inj] = round(mean_inj * min(total_lambda, 1.0), 2)

        return ReservoirResult(connectivity=conn, effective_injection=eff,
                               model=self.name, estimate=True,
                               note="CRM-lite: связности по МНК (статический режим)")
