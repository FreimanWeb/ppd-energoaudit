"""🔬 Модель vs Отчёт — трёхсторонняя сверка модель ↔ расчет.xlsx ↔ отчёт .doc."""

from __future__ import annotations

import lib
import pandas as pd
import streamlit as st
import ui

from tabs.common import STATUS_BG, Ctx, fmt


def _fmt_report(r) -> str:
    """Значение отчёта: одиночное или диапазон (для многодатовых отчётов 2026)."""
    if r["report"] is None and r["report_lo"] is None:
        return "—"
    if (
        r["report_lo"] is not None
        and r["report_hi"] is not None
        and r["report_lo"] != r["report_hi"]
    ):
        return f"{fmt(r['report_lo'], 3)}…{fmt(r['report_hi'], 3)}"
    return fmt(r["report"], 3)


def render(ctx: Ctx) -> None:
    st.subheader("Трёхсторонняя сверка: модель ↔ расчет.xlsx ↔ отчёт")
    ui.provenance(("Сверка источников", "ok"))
    st.caption(
        "Третий источник — текстовый отчёт энергоаудита (.doc/.docx): независимый "
        "«человеческий» эталон. Колонки статусов: М↔xlsx · М↔отчёт · источники (xlsx↔отчёт)."
    )
    rec = lib.get_reconciliation()
    rows = [
        r
        for r in rec["rows"]
        if r["object_id"] == ctx.object_id and r["aggregate_id"] == ctx.agg_id
    ]
    if not rows:
        st.info(
            "Для этого объекта нет текстового отчёта: у ДНС-7с эталон — телеметрия и "
            "аудит №31, у КНС-129/138/175 в материалах НТУ есть только «… расчет.xlsx». "
            "Сверка модель↔xlsx для них выполняется в тестах (`python -m ppd_audit.verify`)."
        )
    else:
        abs_rows = [r for r in rows if r["kind"] == "абс"]
        rel_rows = [r for r in rows if r["kind"] == "отн"]

        def build_df(rs):
            return pd.DataFrame([
                {
                    "Показатель": r["metric"],
                    "Модель": fmt(r["model"], 3),
                    "расчет.xlsx": fmt(r["xlsx"], 3),
                    "Отчёт .doc": _fmt_report(r),
                    "М↔xlsx": r["st_model_xlsx"],
                    "М↔отч": r["st_model_report"],
                    "Ист.": r["st_sources"],
                    "Примечание": r["note"],
                }
                for r in rs
            ])

        def style(df):
            return df.style.map(
                lambda v: f"background-color:{STATUS_BG.get(v, '')}",
                subset=["М↔xlsx", "М↔отч", "Ист."],
            )

        st.markdown("**Абсолютные показатели**")
        st.dataframe(style(build_df(abs_rows)), width="stretch", hide_index=True)
        if rel_rows:
            st.markdown(
                "**Относительные утверждения отчёта** (модель воспроизводит из своих величин)"
            )
            st.dataframe(style(build_df(rel_rows)), width="stretch", hide_index=True)

        src_bad = [r for r in rows if r["st_sources"] == "✗"]
        mr_bad = [r for r in rows if r["st_model_report"] == "✗"]
        if src_bad:
            st.warning(
                "⚠ Источники расходятся (xlsx ≠ отчёт) — разные итерации/замеры/привязка "
                "агрегатов. Причина в колонке «Примечание»; разбор — docs/verification.md."
            )
        elif mr_bad:
            st.warning(
                "Есть ✗ модель↔отчёт — см. «Примечание» (как правило, рассогласование "
                "источников, а не ошибка модели)."
            )
        else:
            st.success("Модель согласуется и с инженерным расчётом, и с текстовым отчётом.")

        # Цитаты из отчёта по этому агрегату
        facts = lib.get_report_facts(ctx.object_id)
        ra = facts.get("aggregates", {}).get(ctx.agg_id, {})
        if ra.get("claims"):
            st.markdown("**Выдержки из отчёта (проза):**")
            for txt in dict.fromkeys(c["text"] for c in ra["claims"] if c["text"]):
                st.markdown(f"> {txt}")

    st.markdown("---")
    s = rec["summary"]
    cc = st.columns(4)
    cc[0].metric("Строк сверки (все объекты)", s["total_rows"])
    cc[1].metric("Модель↔отчёт ✓", s["model_report"].get("✓", 0))
    cc[2].metric("Расхождения источников", s["sources"].get("⚠", 0) + s["sources"].get("✗", 0))
    if s.get("source_agreement_rate") is not None:
        cc[3].metric("Согласованность источников", f"{s['source_agreement_rate'] * 100:.0f}%")
