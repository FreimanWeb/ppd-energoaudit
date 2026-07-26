"""CLI верификации: python -m ppd_audit.verify

Парсит эталоны (xlsx + текстовые отчёты), прогоняет ядро, печатает таблицы сверки
(двустороннюю модель↔xlsx и трёхстороннюю модель↔xlsx↔отчёт) и сохраняет отчёты.
"""

from __future__ import annotations

from .compare import FAIL, NA, OK, WARN
from .reconcile import run_reconciliation, save_reconciliation
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
    print(
        f"Строк сверки: {s['total_rows']} | {OK} {s['by_status'][OK]} · "
        f"{WARN} {s['by_status'][WARN]} · {FAIL} {s['by_status'][FAIL]} · {NA} {s['by_status'][NA]}"
    )
    print(
        f"Измеряемые KPI (УРЭф/КПДф) в допуске: {s['measured_ok']}/{s['measured_metrics']} "
        f"({s['measured_pass_rate'] * 100:.0f}%)"
    )
    for e in res["errors"]:
        print(f"  ⚠ {e}")

    paths = save_report(res)
    print(f"\nОтчёт: {paths['csv']}")
    print(f"       {paths['json']}")

    # ── Трёхсторонняя сверка с текстовыми отчётами (.doc/.docx) ──
    print("\n" + "═" * 64)
    print("ТРЁХСТОРОННЯЯ СВЕРКА: модель ↔ расчет.xlsx ↔ отчёт (.doc/.docx)")
    rec = run_reconciliation()
    cur = None
    for r in rec["rows"]:
        if r.st_model_xlsx == OK and r.st_model_report in (OK, NA) and r.st_sources in (OK, NA):
            continue  # печатаем только расхождения
        head = (r.object_id, r.aggregate_id)
        if head != cur:
            cur = head
            print(f"\n— {r.object_name} · {r.aggregate_id} · {r.pump_kind} —")
        rep = (
            "—"
            if r.report is None
            else (
                f"{r.report:.3f}"
                if r.report_lo == r.report_hi
                else f"{r.report_lo:.3f}…{r.report_hi:.3f}"
            )
        )
        print(
            f"   М↔xlsx {r.st_model_xlsx} М↔отч {r.st_model_report} ист.{r.st_sources}  "
            f"{r.metric:26s} модель {('—' if r.model is None else f'{r.model:.3f}'):>10}  "
            f"xlsx {('—' if r.xlsx is None else f'{r.xlsx:.3f}'):>10}  отчёт {rep:>14}  {r.note}"
        )

    rs = rec["summary"]
    print("\n=== Итог трёхсторонней сверки ===")
    print(
        f"Строк: {rs['total_rows']} | модель↔отчёт: {OK} {rs['model_report'][OK]} · "
        f"{WARN} {rs['model_report'][WARN]} · {FAIL} {rs['model_report'][FAIL]}"
    )
    if rs["source_agreement_rate"] is not None:
        print(
            f"Согласованность источников (xlsx↔отчёт): {rs['source_agreement_rate'] * 100:.0f}% "
            f"из {rs['source_pairs']} пар"
        )
    for e in rec["errors"]:
        print(f"  ⚠ {e}")
    rpaths = save_reconciliation(rec)
    print(f"\nСверка: {rpaths['csv']}")
    print(f"        {rpaths['md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
