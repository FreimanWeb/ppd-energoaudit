"""CLI слоя данных: python -m ppd_audit.ingest [plant_id]

Читает телеметрию объекта, сохраняет нормализованные ряды и отчёт качества,
печатает краткую сводку.
"""

from __future__ import annotations

import sys

from ..quality.report import build_quality_report, save_quality_report
from .pipeline import ingest_plant, save_dataset


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    plant_id = argv[0] if argv else "dns7s"

    print(f"[ingest] объект: {plant_id}")
    ds = ingest_plant(plant_id)
    out = save_dataset(ds)
    print(f"[ingest] нормализованные ряды → {out}")

    rep = build_quality_report(ds)
    path = save_quality_report(rep)
    print(f"[quality] отчёт качества → {path}\n")

    _print_summary(rep)
    return 0


def _print_summary(rep: dict) -> None:
    print("=== Сводка качества данных ===")
    print("Ряды:")
    for name, q in rep["series"].items():
        if q.get("n", 0) == 0:
            print(f"  {name:14s}: нет данных")
        else:
            print(f"  {name:14s}: n={q['n']:>6}  нулей={q['zero_fraction']:.0%}  "
                  f"медиана={q['value_median']}  период {q['period'][0][:10]}…{q['period'][1][:10]}")
    print("Журналы (наработка):")
    for agg, j in rep["journals"].items():
        print(f"  {agg}: события {j['events_raw']}→{j['events_dedup']} (дублей {j.get('duplicates_removed',0)}), "
              f"наработка {j['runtime_hours']} ч, пусков {j['starts']}")
    if "transfer_gaps" in rep:
        g = rep["transfer_gaps"]
        print(f"Перекачка: {g['n']} сут, пропусков дат {g['missing_dates']} ({g.get('missing_fraction',0):.1%})")
    e = rep["balances"]["energy"]
    print(f"Энергобаланс: доли по агрегатам {e['shares']}")
    sf = rep["balances"]["sec_fact"]
    if "sec_fact_by_transfer" in sf:
        print(f"УРЭ факт (по перекачке): {sf['sec_fact_by_transfer']} кВт·ч/м³  "
              f"(по УУЖ: {sf.get('sec_fact_by_uuj','—')})")
    v = rep["balances"]["volume"]
    if "residual_pct_median" in v:
        print(f"Объёмный баланс УУЖ↔перекачка: медианная невязка {v['residual_pct_median']}%")
    if rep["flags"]:
        print("Флаги:")
        for fl in rep["flags"]:
            print(f"  ⚠ {fl}")


if __name__ == "__main__":
    raise SystemExit(main())
