"""CLI расчётного ядра: python -m ppd_audit.core [plant_id] [aggregate]

Печатает воспроизведение энергоаудита агрегата рядом с эталоном из паспорта.
"""

from __future__ import annotations

import sys

from ..config import load_plant
from .audit import run_pump_audit


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    plant_id = argv[0] if argv else "dns7s"
    agg = argv[1] if len(argv) > 1 else None

    plant = load_plant(plant_id)
    exp = (plant.reference_regime or {}).get("expected", {})
    r = run_pump_audit(plant_id, agg)
    g = r.regime

    def line(label, val, ref, unit="", fmt="{:.4f}"):
        ref_s = fmt.format(ref) if isinstance(ref, (int, float)) else "—"
        print(f"  {label:24s} {fmt.format(val):>12s} {unit:<10s} эталон {ref_s}")

    print(f"=== {plant.meta['name']} · агрегат {r.aggregate_id} · ветка «{r.branch}» ===")
    line("H_ф (8), м", g.h_fact, exp.get("h_fact"), fmt="{:.2f}")
    line("P_гидр (11), кВт", g.p_hydraulic, exp.get("p_hydraulic"), fmt="{:.3f}")
    line("P_эл, кВт", g.p_electric, exp.get("p_electric"), fmt="{:.2f}")
    line("η_НА факт (13)", g.eta_unit, exp.get("eta_fact"))
    line("η_ном (14)", g.eta_nom, exp.get("eta_nom"))
    line("K_з (24)", r.load_factor, exp.get("load_factor"))
    line("η_эд.р (25-26)", r.eta_motor_real, exp.get("eta_motor_calc"))
    line("η_нас (27)", r.eta_pump, exp.get("eta_pump"))
    line("УРЭ_ф (16), кВт·ч/м³", r.sec_fact, exp.get("sec_fact"))
    line("УРЭ_р (17), кВт·ч/м³", r.sec_calc, exp.get("sec_calc"))
    d = r.decomposition
    print(f"  {'ΔW_НА = ΔP_КПД·T_год':24s} {r.dw_efficiency:>12.1f} {'кВт·ч/год':<10s} "
          f"эталон {exp.get('dw_efficiency','—')}")
    if hasattr(d, "balance_ok"):
        print(f"  Баланс мощностей (43): невязка {d.balance_residual:.2e} кВт, сходится: {d.balance_ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
