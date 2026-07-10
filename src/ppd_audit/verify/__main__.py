"""CLI верификации: python -m ppd_audit.verify

Парсит эталоны («… расчет.xlsx»), прогоняет ядро, печатает таблицу сверки
модель↔xlsx и сохраняет отчёт (verification_report.csv/.json).
"""

from __future__ import annotations

from .compare import FAIL, NA, OK, WARN
from .runner import run_verification, save_report


def main() -> int:
    res = run_verification()
    rows = res["rows"]

    cur = None
    for r in rows:
        head = (r.object_id, r.aggregate_id)
        if head != cur:
            cur = head
            print(f"\n— {r.object_name} · {r.aggregate_id} · {r.water_type} · {r.pump_kind} —")
        model = "—" if r.model is None else f"{r.model:>12.3f}"
        refer = "—" if r.reference is None else f"{r.reference:>12.3f}"
        dev = "" if r.rel_dev is None else f"{r.rel_dev * 100:+6.1f}%"
        print(f"   {r.status} {r.metric:26s} модель {model}  эталон {refer}  {dev}")

    s = res["summary"]
    print("\n=== Итог ===")
    print(f"Строк сверки: {s['total_rows']} | {OK} {s['by_status'][OK]} · "
          f"{WARN} {s['by_status'][WARN]} · {FAIL} {s['by_status'][FAIL]} · {NA} {s['by_status'][NA]}")
    print(f"Измеряемые KPI (УРЭф/КПДф) в допуске: {s['measured_ok']}/{s['measured_metrics']} "
          f"({s['measured_pass_rate'] * 100:.0f}%)")
    for e in res["errors"]:
        print(f"  ⚠ {e}")

    paths = save_report(res)
    print(f"\nОтчёт: {paths['csv']}")
    print(f"       {paths['json']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
