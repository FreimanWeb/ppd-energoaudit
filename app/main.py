"""Цифровой энергоаудит ППД — дашборд (Streamlit).

Запуск:  streamlit run app/main.py
Экраны: Обзор · Схема ППД · Карта потерь · Рабочая точка · Модель vs Отчёт ·
        Мероприятия · Новый объект · Формулы · Качество.
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # каталог app/ для `import lib`

import lib  # noqa: E402  data-слой (настраивает путь к src/)
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
import ui  # noqa: E402  дизайн-система (CSS + компоненты)

st.set_page_config(page_title="Энергоаудит ППД", page_icon="⚡", layout="wide")
ui.inject_css()

WATER_EMOJI = {"пресная": "💧", "агрессивная": "🧪", "пластовая": "🛢️"}
STATUS_BG = {"✓": "#d7f5dd", "⚠": "#fff3cd", "✗": "#f8d7da", "—": "#eeeeee"}


# ── Справочные данные для вкладки «Новый объект» ──
# Требуемая телеметрия (Методика энергоаудита, Таблица 8.2.1).
TELEMETRY_REQUIREMENTS = [
    ("Годовой объём перекачки", "Q_год", "м³", "обязательно", "УУЖ / расчёт"),
    ("Годовая наработка", "T_год", "ч", "обязательно", "журнал состояний"),
    ("Суточный расход жидкости", "Q_сут", "м³", "обязательно", "телеметрия (УУЖ)"),
    ("Время работы за сутки", "T", "ч", "обязательно", "журнал / телеметрия"),
    ("Подача мгновенная", "Q", "м³/ч", "желательно", "телеметрия"),
    ("Давление на приёме", "p_вх", "МПа", "обязательно", "датчик давления"),
    ("Давление на выкиде", "p_вых", "МПа", "обязательно", "датчик давления"),
    ("Плотность жидкости", "ρ", "кг/м³", "обязательно", "замер / тип воды"),
    ("Расход ЭЭ за сутки", "W", "кВт·ч", "обязательно", "счётчик ЭЭ"),
    ("Активная мощность", "P_эл", "кВт", "желательно", "счётчик ЭЭ"),
    ("Давление на БГ (для КНС)", "p_БГ", "МПа", "для КНС", "телеметрия гребёнки"),
    ("Вязкость (перекачка нефти)", "ν", "сСт", "для нефти", "лаборатория"),
    ("Диаметр выкидной трубы", "D", "мм", "для нефти/вязкости", "паспорт трубы"),
    ("Толщина стенки трубы", "d", "мм", "для нефти/вязкости", "паспорт трубы"),
]

NEW_OBJECT_YAML_TEMPLATE = """\
# config/plants/<id>.yaml — паспорт + режим объекта.
# Обычно создаётся автоматически из «… расчет.xlsx», но можно завести вручную.
id: kns_new
name: КНС-XXX
water_type: пресная        # пресная | агрессивная | пластовая
branch: кнс                # кнс | перекачка
source: data/raw/ntu/<вид воды>/<папка>/<...> расчет.xlsx
aggregates:
  - id: НА-1
    role: работа           # работа | резерв
    pump:
      model: ЦНС-180-1422
      kind: центробежный    # центробежный | объёмный
      q_nom: 180.0
      h_nom: 1422.0
      eta_nom: 0.72
      power_nom: 1250.0
      n_rpm: 3000.0
      curve_qh: []          # [[Q,H], ...] из паспорта (опц.)
      curve_qeta: []        # [[Q,eta], ...] (опц.)
    motor:
      model: СТД-1250
      p_nom: 1250.0
      eta_nom: 0.95
      cos_phi: 0.9
      voltage_kv: 6.0
    transmission_eff: 1.0
    vfd: false
    regime:                 # из телеметрии / замера
      rho: 1130.0
      p_in: 0.8
      p_out: 14.0
      p_bg: 13.5
      q_day: 4000.0
      t: 24.0
      w: 60000.0
      t_year: 8000.0
"""

NEW_OBJECT_VERIFICATION_TEMPLATE = """\
# config/verification.yaml -> секция objects: (пути относительно data/raw/ntu)
objects:
  - id: kns_new
    name: "КНС-XXX"
    file: "<вид воды>/<папка объекта>/<...> расчет.xlsx"
    report: "<вид воды>/<папка объекта>/<самый поздний> отчёт.doc"   # опционально
"""


# ── Формулы методики в LaTeX (для вкладки «Формулы»; KaTeX, кириллица в \text{}) ──
_FORMULA_LATEX = {
    "8":  r"H_{\text{ф}}=\dfrac{(p_{\text{вых}}-p_{\text{вх}})\cdot 10^{6}}{\rho\,g}",
    "11": r"P_{\text{гидр}}=\dfrac{(p_{\text{вых}}-p_{\text{вх}})\cdot Q}{3{,}6}",
    "13": r"\eta_{\text{НА}}=\dfrac{P_{\text{гидр}}}{P_{\text{эл}}}",
    "14": r"\eta_{\text{ном}}=\eta_{\text{ЭД.ном}}\cdot\eta_{\text{нас.ном}}\cdot\eta_{\text{тр}}",
    "16": r"\text{УРЭ}_{\text{ф}}=\dfrac{W}{Q_{\text{сут}}}",
    "17": r"\text{УРЭ}_{\text{р}}=\dfrac{p_{\text{вых}}-p_{\text{вх}}}{3{,}6\,\eta_{\text{ном}}}",
    "24": r"K_{\text{з}}=\dfrac{P_{\text{эл}}}{P_{\text{ном}}/\eta_{\text{ЭД.ном}}}",
    "25-26": r"\eta_{\text{эд.р}}=\dfrac{1}{1+\left(\tfrac{1}{\eta_{\text{ЭД.ном}}}-1\right)\beta}",
    "27": r"\eta_{\text{нас}}=\dfrac{\eta_{\text{НА}}}{\eta_{\text{эд.р}}}",
    "44": r"\Delta W_{\text{кпд}}=Q_{\text{год}}\,(\text{УРЭ}_{\text{ф}}-\text{УРЭ}_{\text{р}})",
}
_FORMULA_NAME = {
    "8": "Фактический напор, м", "11": "Гидравлическая мощность, кВт",
    "13": "КПД насосной установки (факт)", "14": "Номинальный КПД",
    "16": "УРЭ фактический, кВт·ч/м³", "17": "УРЭ расчётный, кВт·ч/м³",
    "24": "Коэффициент загрузки ЭД", "25-26": "КПД ЭД при недогрузке",
    "27": "КПД насоса", "44": "Годовые потери по КПД, кВт·ч/год",
}


def _clean_nums(s: str) -> str:
    """Округлить длинные десятичные хвосты в строке (0.8335950000001 → 0.8336)."""
    return re.sub(r"-?\d+\.\d+", lambda m: f"{float(m.group()):.4g}", str(s))


def _subst_to_latex(s: str) -> str:
    """Числовая подстановка → LaTeX-выражение."""
    return (_clean_nums(s).replace("1e6", r"\cdot 10^{6}")
            .replace("·", r"\cdot ").replace("−", "-"))


def fmt(x, nd: int = 2) -> str:
    """Формат числа ru-RU: 53 242,90."""
    if x is None or isinstance(x, str):
        return x if isinstance(x, str) else "—"
    s = f"{x:,.{nd}f}".replace(",", " ").replace(".", ",")
    return s


# ───────────────────────── Sidebar: выбор объекта ─────────────────────────

st.sidebar.title("⚡ Энергоаудит ППД")
index = lib.object_index()
waters = sorted({o["water"] for o in index}, key=lambda w: lib.WATER_ORDER.index(w)
                if w in lib.WATER_ORDER else 9)
sel_waters = st.sidebar.multiselect("Тип воды", waters, default=waters)
flt = [o for o in index if o["water"] in sel_waters] or index

obj_labels = {f"{o['name']}  ·  {WATER_EMOJI.get(o['water'],'')} {o['water']}": o["id"] for o in flt}
obj_choice = st.sidebar.selectbox("Объект", list(obj_labels))
object_id = obj_labels[obj_choice]
obj = lib.get_object(object_id)

agg_ids = [a.id for a in obj.working_aggregates()]
agg_id = st.sidebar.selectbox("Агрегат", agg_ids)
agg = obj.aggregate(agg_id)
audit = lib.get_audit(object_id, agg_id)
tariff = lib.tariff()

st.sidebar.markdown("---")
st.sidebar.caption(f"Ветка расчёта: **{obj.branch.value}**")
st.sidebar.caption(f"Тип насоса: **{audit.pump_kind}**")
st.sidebar.caption(f"Источник: {obj.source.split('/')[-1]}")

_eta_ratio = (audit.regime.eta_unit / audit.regime.eta_nom) if audit.regime.eta_nom else 1.0
_eta_tone = "ok" if _eta_ratio >= 0.9 else ("warn" if _eta_ratio >= 0.78 else "bad")
ui.hero(
    f"{obj.name} · {agg_id}",
    f"Цифровой энергоаудит ППД · источник: {obj.source.split('/')[-1]}",
    [(f"{WATER_EMOJI.get(obj.water_type.value, '')} {obj.water_type.value} вода", ""),
     (f"ветка: {obj.branch.value}", ""),
     (f"насос: {audit.pump_kind}", ""),
     (f"КПД {fmt(audit.regime.eta_unit, 3)} / ном {fmt(audit.regime.eta_nom, 3)}", _eta_tone),
     (f"УРЭ {fmt(audit.sec_fact, 2)} кВт·ч/м³", "")])

(tab_overview, tab_scheme, tab_losses, tab_point, tab_recon,
 tab_measures, tab_newobj, tab_formulas, tab_quality) = st.tabs([
    "📋 Обзор", "🗺️ Схема ППД", "📉 Карта потерь", "📈 Рабочая точка",
    "🔬 Модель vs Отчёт", "💡 Мероприятия", "🧩 Новый объект",
    "🧮 Формулы", "✅ Качество данных"])


# ───────────────────────────── Обзор ─────────────────────────────
with tab_overview:
    reg = audit.regime
    rm = agg.regime
    p, m = agg.pump, agg.motor

    st.subheader("Ключевые показатели (KPI)")
    c = st.columns(4)
    sec_dev = (audit.sec_fact - audit.sec_calc) / audit.sec_calc * 100 if audit.sec_calc else None
    c[0].metric("УРЭ факт, кВт·ч/м³", fmt(audit.sec_fact, 3),
                f"{fmt(sec_dev,1)} % к расчётному" if sec_dev is not None else None,
                delta_color="inverse",
                help="Фактический удельный расход ЭЭ = W / Q_сут (формула 16).")
    c[1].metric("УРЭ расчётный, кВт·ч/м³", fmt(audit.sec_calc, 3),
                help="По напору и номинальному КПД (формула 17). Разница с фактом = потери КПД.")
    c[2].metric("УРЭ оптимальный, кВт·ч/м³", fmt(audit.sec_optimal, 3),
                help="По НДТ / оптимальному режиму (формула 18).")
    c[3].metric("Цель ППД-2035", fmt(lib.constraints().kpi.get("target_sec_2035"), 2),
                help="Целевой УРЭ системы ППД к 2035 г. (ТЗ).")

    c = st.columns(4)
    c[0].metric("КПД факт", fmt(reg.eta_unit, 3),
                help="Фактический КПД насосной установки = P_гидр / P_эл (формула 13).")
    c[1].metric("КПД номинальный", fmt(reg.eta_nom, 3),
                help="Паспортный КПД (η_ЭД·η_нас·η_тр, формула 14).")
    c[2].metric("ΔW по КПД, кВт·ч/год", fmt(audit.dw_efficiency, 0),
                help="Годовые потери из-за снижения КПД (формула 44).")
    c[3].metric("ΔW по КПД, тыс. ₽/год", fmt(audit.dw_efficiency * tariff / 1000, 1),
                help="Те же потери в деньгах по тарифу.")

    st.divider()
    gc = st.columns([1, 1.4])
    with gc[0]:
        en = reg.eta_nom or 0.7
        gfig = go.Figure(go.Indicator(
            mode="gauge+number", value=reg.eta_unit, number={"valueformat": ".3f"},
            title={"text": "КПД установки (факт)", "font": {"size": 14}},
            gauge={"axis": {"range": [0, max(en, reg.eta_unit) * 1.15]},
                   "bar": {"color": "#2f80ed"},
                   "steps": [{"range": [0, en * 0.78], "color": "#f6d6d2"},
                             {"range": [en * 0.78, en * 0.9], "color": "#fdeecb"},
                             {"range": [en * 0.9, max(en, reg.eta_unit) * 1.15], "color": "#cdeedd"}],
                   "threshold": {"line": {"color": "#1f4e79", "width": 4}, "value": en}}))
        gfig.update_layout(height=250, margin=dict(t=40, b=10, l=24, r=24))
        st.plotly_chart(gfig, width="stretch")
        st.caption("Порог (синяя черта) — номинальный КПД. Зоны: 🔴 <0,78·ном · 🟡 <0,9·ном · 🟢 норма.")
    with gc[1]:
        labels = ["факт", "расчётный", "оптимальный", "цель-2035"]
        vals = [audit.sec_fact, audit.sec_calc, audit.sec_optimal,
                lib.constraints().kpi.get("target_sec_2035")]
        bfig = go.Figure(go.Bar(x=labels, y=vals, marker_color=["#d9534f", "#2f80ed", "#2e9e6b", "#1f4e79"],
                                text=[fmt(v, 2) for v in vals], textposition="outside",
                                textfont=dict(size=13)))
        bfig.update_layout(height=250, margin=dict(t=40, b=10), yaxis_title="кВт·ч/м³",
                           title={"text": "УРЭ: факт → расчёт → оптимум → цель", "font": {"size": 14}},
                           plot_bgcolor="#f7fafd")
        st.plotly_chart(bfig, width="stretch")

    st.divider()
    st.subheader("Паспорт и режим")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("**Насос**")
        st.write({"Модель": p.model, "Тип": p.kind.value, "Q_ном, м³/ч": p.q_nom,
                  "H_ном, м": p.h_nom, "η_нас.ном": p.eta_nom, "n, об/мин": p.n_rpm})
    with col2:
        st.markdown("**Электродвигатель**")
        st.write({"Модель": m.model, "P_ном, кВт": m.p_nom, "η_ЭД.ном": m.eta_nom,
                  "cos φ": m.cos_phi, "U, кВ": m.voltage_kv})
    with col3:
        st.markdown("**Режим**")
        st.write({"ρ, кг/м³": rm.rho, "p_вх, МПа": round(rm.p_in, 3),
                  "p_вых, МПа": round(rm.p_out, 3),
                  "p_БГ, МПа": round(rm.p_bg, 3) if rm.p_bg else None,
                  "Q_сут, м³": rm.q_day, "T, ч": rm.t, "T_год, ч": rm.t_year})

    # Выдержка из текстового отчёта энергоаудита (для визуальной сверки прозы с числами)
    facts = lib.get_report_facts(object_id)
    if facts:
        src = facts["source"].split("/")[-1]
        with st.expander(f"📄 Текстовый отчёт энергоаудита — выводы (источник: {src})"):
            ra = facts.get("aggregates", {}).get(agg_id, {})
            for c in ra.get("claims", []):
                st.markdown(f"> {c['text']}")
            teo = facts.get("teo", {})
            if teo.get("headline"):
                st.info("ТЭО: " + teo["headline"])
            elif teo.get("total_loss_kwh"):
                st.caption(f"Годовые потери по отчёту: {fmt(teo['total_loss_kwh'], 0)} кВт·ч"
                           + (f" · {fmt(teo.get('total_loss_krub'), 1)} тыс. ₽" if teo.get('total_loss_krub') else ""))
            if facts.get("recommendations"):
                st.markdown("**Рекомендации отчёта:**")
                for rrec in facts["recommendations"][:5]:
                    st.markdown(f"- {rrec}")


# ───────────────────────── Карта потерь ─────────────────────────
def loss_components(audit) -> tuple[float, list[tuple[str, float]]]:
    """(полезная мощность, [(подпись потери, кВт)]). Сумма = P_эл."""
    d = audit.decomposition
    if d is None:
        return audit.regime.p_hydraulic, []
    if hasattr(d, "p_bg_useful"):       # КНС (31-36)
        return d.p_bg_useful, [
            ("Потери КПД", d.dp_efficiency), ("Номинальные", d.dp_nominal),
            ("Дросселирование", d.dp_na_throttle), ("Гидравл. насос→БГ", d.dp_hydraulic)]
    # перекачка (37-42)
    return audit.regime.p_hydraulic, [
        ("Износ", d.dp_wear), ("Неоптим. подача", d.dp_suboptimal),
        ("Завыш. мощность ЭД", d.dp_motor), ("Вязкость", d.dp_viscosity),
        ("Номинальные", d.dp_nominal)]


with tab_losses:
    st.subheader("Цифровая карта потерь мощности")
    useful, losses = loss_components(audit)
    p_el = audit.regime.p_electric
    losses = [(lbl, v) for lbl, v in losses if abs(v) > 1e-6]

    labels = ["P_эл (подвод)"] + [l for l, _ in losses] + ["Полезная мощность"]
    measures = ["absolute"] + ["relative"] * len(losses) + ["total"]
    values = [p_el] + [-v for _, v in losses] + [0]
    fig = go.Figure(go.Waterfall(
        orientation="v", measure=measures, x=labels, y=values,
        textposition="outside", text=[fmt(p_el, 1)] + [fmt(-v, 1) for _, v in losses] + [fmt(useful, 1)],
        connector={"line": {"color": "#bbb"}},
        decreasing={"marker": {"color": "#e07a5f"}},
        increasing={"marker": {"color": "#81b29a"}},
        totals={"marker": {"color": "#3d5a80"}}))
    fig.update_layout(height=440, yaxis_title="кВт", margin=dict(t=30, b=10),
                      font=dict(family="sans-serif"))
    st.plotly_chart(fig, width="stretch")

    st.markdown("**Структура (доли от подведённой мощности P_эл):**")
    t_year = audit.regime and (agg.regime.t_year or 8760)
    rows = [("Полезная мощность", useful)] + losses
    st.dataframe(
        {"Составляющая": [r[0] for r in rows],
         "кВт": [fmt(r[1], 2) for r in rows],
         "% от P_эл": [fmt(r[1] / p_el * 100, 1) for r in rows],
         "тыс. ₽/год": [fmt(r[1] * t_year * tariff / 1000, 0) for r in rows]},
        width="stretch", hide_index=True)
    st.caption(f"₽/год — по годовой наработке {fmt(t_year,0)} ч и тарифу {fmt(tariff,2)} ₽/кВт·ч.")


# ───────────────────────── Рабочая точка ─────────────────────────
def _pump_qh_curve(p):
    """Q-H: паспортная кривая или модельная парабола (центробежный). → (qs, hs, паспорт?) | None."""
    if p.curve_qh:
        return [c[0] for c in p.curve_qh], [c[1] for c in p.curve_qh], True
    if p.kind.value == "объёмный" or not (p.q_nom and p.h_nom):
        return None
    import numpy as np
    h0 = 1.22 * p.h_nom                       # напор при закрытой задвижке ~1,22·H_ном
    a = (h0 - p.h_nom) / (p.q_nom ** 2)
    qs = np.linspace(0, 1.5 * p.q_nom, 41)
    return qs, h0 - a * qs ** 2, False


def _system_curve(q_work, h_fact, p_in, p_bg, rho, q_nom):
    """Характеристика трубопровода H = H_ст + k·Q², проходящая через рабочую точку."""
    import numpy as np
    if not q_work or h_fact is None:
        return None
    h_st = ((p_bg - p_in) * 1e6 / (rho * 9.81)) if (p_bg and p_bg > p_in) else 0.35 * h_fact
    h_st = max(0.0, min(h_st, 0.95 * h_fact))
    k = (h_fact - h_st) / (q_work ** 2)
    qs = np.linspace(0, 1.5 * (q_nom or q_work), 41)
    return qs, h_st + k * qs ** 2


with tab_point:
    st.subheader("Рабочая точка: насос × трубопровод")
    p = agg.pump
    reg = audit.regime
    rmp = agg.regime
    q_work = rmp.flow()
    volumetric = p.kind.value == "объёмный"
    if volumetric:
        ui.note("Насос объёмного действия (плунжерный): паспортная кривая Q-H неприменима — "
                "подача задаётся числом ходов. Показаны фактические точки.")

    cc = st.columns(2)
    with cc[0]:
        fig = go.Figure()
        pc = _pump_qh_curve(p)
        if pc:
            qs, hs, is_pass = pc
            fig.add_trace(go.Scatter(x=qs, y=hs, mode="lines",
                          name="Кривая насоса · паспорт" if is_pass else "Кривая насоса · модель",
                          line=dict(color="#1f4e79", width=3, dash=None if is_pass else "dot")))
        sc = _system_curve(q_work, reg.h_fact, rmp.p_in, rmp.p_bg, rmp.rho, p.q_nom)
        if sc and not volumetric:
            fig.add_trace(go.Scatter(x=sc[0], y=sc[1], mode="lines", name="Характеристика трубопровода",
                          line=dict(color="#2e9e6b", width=2.5, dash="dash")))
        if p.q_nom and p.h_nom and not volumetric:
            fig.add_trace(go.Scatter(x=[p.q_nom], y=[p.h_nom], mode="markers+text", text=["номинал"],
                          textposition="top center", name="Номинал",
                          marker=dict(size=13, color="#2f80ed", symbol="diamond")))
        if audit.spec.reference and audit.spec.reference.h_due:
            fig.add_trace(go.Scatter(x=[q_work], y=[audit.spec.reference.h_due], mode="markers",
                          name="Должный напор", marker=dict(size=12, color="#e0a106")))
        fig.add_trace(go.Scatter(x=[q_work], y=[reg.h_fact], mode="markers+text", text=["раб. точка"],
                      textposition="bottom center", name="Факт",
                      marker=dict(size=16, color="#d9534f", symbol="x", line=dict(width=2, color="#9c2b27"))))
        fig.update_layout(title="Q–H: насос и трубопровод", xaxis_title="Q, м³/ч", yaxis_title="H, м",
                          height=420, margin=dict(t=46, b=10), legend=dict(orientation="h", y=-0.22),
                          plot_bgcolor="#f7fafd")
        st.plotly_chart(fig, width="stretch")
    with cc[1]:
        fig = go.Figure()
        if p.curve_qeta:
            fig.add_trace(go.Scatter(x=[c[0] for c in p.curve_qeta], y=[c[1] for c in p.curve_qeta],
                          mode="lines", name="Q-η · паспорт", line=dict(color="#1f4e79", width=3)))
        elif p.q_nom and p.eta_nom and not volumetric:
            import numpy as np
            qe = np.linspace(0.2 * p.q_nom, 1.4 * p.q_nom, 31)
            fig.add_trace(go.Scatter(x=qe, y=p.eta_nom * (1 - 0.9 * ((qe - p.q_nom) / p.q_nom) ** 2),
                          mode="lines", name="Q-η · модель", line=dict(color="#1f4e79", width=3, dash="dot")))
        if p.q_nom and p.eta_nom and not volumetric:
            fig.add_trace(go.Scatter(x=[p.q_nom], y=[p.eta_nom], mode="markers+text", text=["номинал"],
                          textposition="top center", name="Номинал",
                          marker=dict(size=13, color="#2f80ed", symbol="diamond")))
        fig.add_trace(go.Scatter(x=[q_work], y=[reg.eta_unit], mode="markers+text", text=["факт"],
                      textposition="bottom center", name="КПД факт",
                      marker=dict(size=16, color="#d9534f", symbol="x", line=dict(width=2, color="#9c2b27"))))
        fig.update_layout(title="Q–η: КПД насоса", xaxis_title="Q, м³/ч", yaxis_title="η, о.е.",
                          height=420, margin=dict(t=46, b=10), legend=dict(orientation="h", y=-0.22),
                          plot_bgcolor="#f7fafd")
        st.plotly_chart(fig, width="stretch")
    st.caption(f"Рабочая подача Q = {fmt(q_work,2)} м³/ч · напор факт {fmt(reg.h_fact,1)} м · "
               f"КПД факт {fmt(reg.eta_unit,3)}. Пунктир — модельные кривые (нет паспортных координат).")


# ───────────────────────── Модель vs Отчёт (3 источника) ─────────────────────────
def fmt_report(r) -> str:
    """Значение отчёта: одиночное или диапазон (для многодатовых отчётов 2026)."""
    if r["report"] is None and r["report_lo"] is None:
        return "—"
    if r["report_lo"] is not None and r["report_hi"] is not None and r["report_lo"] != r["report_hi"]:
        return f"{fmt(r['report_lo'], 3)}…{fmt(r['report_hi'], 3)}"
    return fmt(r["report"], 3)


with tab_recon:
    st.subheader("Трёхсторонняя сверка: модель ↔ расчет.xlsx ↔ отчёт")
    st.caption("Третий источник — текстовый отчёт энергоаудита (.doc/.docx): независимый "
               "«человеческий» эталон. Колонки статусов: М↔xlsx · М↔отчёт · источники (xlsx↔отчёт).")
    rec = lib.get_reconciliation()
    rows = [r for r in rec["rows"]
            if r["object_id"] == object_id and r["aggregate_id"] == agg_id]
    if not rows:
        st.info("Для этого объекта нет текстового отчёта (например, ДНС-7с — телеметрия). "
                "Трёхсторонняя сверка доступна для объектов из отчётов энергоаудита.")
    else:
        import pandas as pd
        abs_rows = [r for r in rows if r["kind"] == "абс"]
        rel_rows = [r for r in rows if r["kind"] == "отн"]

        def build_df(rs):
            return pd.DataFrame([{
                "Показатель": r["metric"], "Модель": fmt(r["model"], 3),
                "расчет.xlsx": fmt(r["xlsx"], 3), "Отчёт .doc": fmt_report(r),
                "М↔xlsx": r["st_model_xlsx"], "М↔отч": r["st_model_report"],
                "Ист.": r["st_sources"], "Примечание": r["note"]} for r in rs])

        def style(df):
            return df.style.map(lambda v: f"background-color:{STATUS_BG.get(v,'')}",
                                subset=["М↔xlsx", "М↔отч", "Ист."])

        st.markdown("**Абсолютные показатели**")
        st.dataframe(style(build_df(abs_rows)), width="stretch", hide_index=True)
        if rel_rows:
            st.markdown("**Относительные утверждения отчёта** (модель воспроизводит из своих величин)")
            st.dataframe(style(build_df(rel_rows)), width="stretch", hide_index=True)

        src_bad = [r for r in rows if r["st_sources"] == "✗"]
        mr_bad = [r for r in rows if r["st_model_report"] == "✗"]
        if src_bad:
            st.warning("⚠ Источники расходятся (xlsx ≠ отчёт) — разные итерации/замеры/привязка "
                       "агрегатов. Причина в колонке «Примечание»; разбор — docs/verification.md.")
        elif mr_bad:
            st.warning("Есть ✗ модель↔отчёт — см. «Примечание» (как правило, рассогласование "
                       "источников, а не ошибка модели).")
        else:
            st.success("Модель согласуется и с инженерным расчётом, и с текстовым отчётом.")

        # Цитаты из отчёта по этому агрегату
        facts = lib.get_report_facts(object_id)
        ra = facts.get("aggregates", {}).get(agg_id, {})
        if ra.get("claims"):
            st.markdown("**Выдержки из отчёта (проза):**")
            for txt in dict.fromkeys(c["text"] for c in ra["claims"] if c["text"]):
                st.markdown(f"> {txt}")

    st.markdown("---")
    s = rec["summary"]
    cc = st.columns(4)
    cc[0].metric("Строк сверки", s["total_rows"])
    cc[1].metric("Модель↔отчёт ✓", s["model_report"].get("✓", 0))
    cc[2].metric("Расхождения источников", s["sources"].get("⚠", 0) + s["sources"].get("✗", 0))
    if s.get("source_agreement_rate") is not None:
        cc[3].metric("Согласованность источников", f"{s['source_agreement_rate'] * 100:.0f}%")


# ───────────────────────── Мероприятия + оптимизация ─────────────────────────
with tab_measures:
    st.subheader("Реестр мероприятий с ТЭО")
    from ppd_audit.measures import suggest_measures
    from ppd_audit.optimize import optimize_setpoint

    evals = suggest_measures(audit, tariff)
    if evals:
        st.dataframe(
            {"Мероприятие": [e.name for e in evals],
             "Класс": [e.cls for e in evals],
             "Экономия, кВт·ч/год": [fmt(e.energy_saving_kwh, 0) for e in evals],
             "Экономия, тыс. ₽/год": [fmt(e.money_saving_krub, 1) for e in evals],
             "CAPEX, тыс. ₽": [fmt(e.capex_krub, 0) for e in evals],
             "Окупаемость, лет": [fmt(e.payback_years, 2) if e.payback_years else "—"
                                  for e in evals]},
            width="stretch", hide_index=True)
    else:
        st.info("Применимых мероприятий не выявлено (потери в пределах нормы).")

    st.markdown("---")
    st.subheader("Оптимизация уставки (с ограничениями)")
    opt = optimize_setpoint(audit, lib.constraints())
    cc = st.columns(4)
    cc[0].metric("p_вых текущее, МПа", fmt(opt.current_p_out, 2))
    cc[1].metric("p_вых оптимум, МПа", fmt(opt.optimal_p_out, 2))
    cc[2].metric("Экономия, кВт·ч/год", fmt(opt.saving_kwh_year, 0))
    cc[3].metric("Частота ПЧ, Гц", fmt(opt.vfd_freq_hz, 1) if opt.vfd_freq_hz else "—")
    for n in opt.notes:
        (st.success if opt.within_constraints else st.warning)(n)


# ───────────────────────── Формулы (drill-down) ─────────────────────────
with tab_formulas:
    st.subheader("Как получено каждое число — формулы методики")
    st.caption("Символьная формула (Методика, разд. 8) → подстановка фактических величин → "
               "результат. Число в скобках — номер формулы методики.")
    order = ["8", "11", "13", "14", "16", "17", "24", "25-26", "27", "44"]
    for fid in order:
        t = audit.trace.get(fid)
        if not t:
            continue
        with st.container(border=True):
            cL, cR = st.columns([3, 1])
            cL.markdown(f"**({fid}) {_FORMULA_NAME.get(fid, '')}**")
            cR.markdown(
                f"<div style='text-align:right;font-size:1.25em;color:#2f6098'>"
                f"<b>{fmt(t['value'], 4)}</b></div>", unsafe_allow_html=True)
            if fid in _FORMULA_LATEX:
                st.latex(_FORMULA_LATEX[fid])
            subst = t.get("subst", "")
            if re.search(r"[А-Яа-яα-ω]", subst):     # символьная подстановка (напр. 25-26)
                st.caption(f"подстановка: {_clean_nums(subst)} → {_clean_nums(t['value'])}")
            else:
                st.latex(_subst_to_latex(subst) + " = " + _clean_nums(t["value"]))


# ───────────────────────── Качество данных ─────────────────────────
with tab_quality:
    st.subheader("Качество и происхождение данных")
    st.write(f"**Источник:** {obj.source}")
    rm = agg.regime
    fields = {
        "ρ (плотность)": rm.rho, "p_вх": rm.p_in, "p_вых": rm.p_out, "p_БГ": rm.p_bg,
        "Q_сут": rm.q_day, "T (сут)": rm.t, "W (ЭЭ/сут)": rm.w,
        "P_эл": rm.p_electric, "T_год": rm.t_year}
    st.markdown("**Полнота режима:**")
    st.dataframe({"Параметр": list(fields), "Значение": [fmt(v, 3) if v is not None else "— нет данных"
                                                          for v in fields.values()],
                  "Статус": ["✓" if v is not None else "—" for v in fields.values()]},
                 width="stretch", hide_index=True)

    # отчёт качества телеметрии (если есть, напр. ДНС-7с)
    import json
    qpath = lib._ROOT / "data" / "generated" / object_id / "quality_report.json"
    if qpath.exists():
        st.markdown("**Отчёт качества телеметрии:**")
        rep = json.loads(qpath.read_text(encoding="utf-8"))
        if rep.get("flags"):
            for fl in rep["flags"]:
                st.warning(fl)
        bal = rep.get("balances", {})
        if "sec_fact" in bal:
            st.write("Баланс/УРЭ:", bal.get("sec_fact"))
    else:
        st.caption("Для объекта используется инженерный «… расчет.xlsx» как эталон; "
                   "телеметрических рядов нет (квалификация — по полноте режима выше).")


# ───────────────────────── Схема ППД (диаграмма + Sankey) ─────────────────────────
_CAT_COLOR = {"source": "#d6e8f5", "prep": "#dbeaf2", "meter": "#e4e8ec",
              "pump": "#aacbe6", "manifold": "#c4e0cb", "valve": "#f0dca0",
              "wells": "#f0cfa6", "reservoir": "#eab8b8", "node": "#e0e0e0"}


def _node_hover(n, typ, au, rm):
    """Текст всплывающей подсказки: что в узле происходит + фактические значения."""
    lines = ["<b>" + str(n.get("label", "")).replace("\n", " ") + "</b>"]
    if n.get("hint"):
        lines.append(n["hint"])
    if typ == "source":
        lines.append(f"p_вх = {fmt(rm.p_in, 2)} МПа · Q = {fmt(rm.q_day, 0)} м³/сут")
    elif typ == "pump" and au is not None:
        r = au.regime
        kz = au.trace.get("24", {}).get("value")
        ratio = (r.eta_unit / r.eta_nom) if r.eta_nom else 1.0
        verdict = "норма" if ratio >= 0.9 else ("пониженный КПД" if ratio >= 0.78 else "низкий КПД")
        lines += ["─────────────",
                  "состояние: <b>в работе</b>",
                  f"КПД факт {fmt(r.eta_unit, 3)} / ном {fmt(r.eta_nom, 3)} — <b>{verdict}</b>",
                  f"K_з {fmt(kz, 2)} · P_эл {fmt(r.p_electric, 0)} кВт · напор {fmt(r.h_fact, 0)} м",
                  f"УРЭ факт {fmt(au.sec_fact, 3)} / расч {fmt(au.sec_calc, 3)} кВт·ч/м³",
                  f"потери по КПД ≈ {fmt(au.dw_efficiency, 0)} кВт·ч/год"]
    elif typ == "manifold":
        lbl = str(n.get("label", "")).lower()
        if ("бг" in lbl or "гребён" in lbl) and rm.p_bg:
            lines.append(f"p_БГ = {fmt(rm.p_bg, 2)} МПа")
        else:
            lines.append(f"p_вых = {fmt(rm.p_out, 2)} МПа")
    elif typ == "valve":
        lines.append("дросселирование: срезается ΔP·Q (кандидат на частотное регулирование)")
    elif typ == "wells":
        lines.append("приёмистость P–Q; ограничение по лимиту закачки")
    elif typ == "reservoir":
        lines.append("отклик пласта (CRM): полезная vs циркулирующая закачка")
    return "<br>".join(lines)


def _topology_figure(topo, object_id, sel_agg, rm):
    """Интерактивная as-built схема: трубопроводы + узлы с hover и подсветкой.

    Насосы подсвечиваются по КПД (зелёный/жёлтый/красный), выбранный агрегат — золотой
    рамкой. Наведение на узел показывает, что в нём происходит, и фактические значения.
    """
    nodes = topo.get("nodes", [])
    pos = {n["id"]: (n["x"], n["y"]) for n in nodes}

    pumps = {}  # node_id -> AuditResult (для подсветки/ховера насосов)
    for n in nodes:
        if n.get("type") == "pump" and n.get("agg"):
            try:
                pumps[n["id"]] = lib.get_audit(object_id, n["agg"])
            except Exception:
                pass

    def eta_fill(au):
        r = (au.regime.eta_unit / au.regime.eta_nom) if au.regime.eta_nom else 1.0
        return "#7cc47c" if r >= 0.9 else ("#f0c64b" if r >= 0.78 else "#e8836b")

    fig = go.Figure()
    # --- трубопроводы: двухслойная «труба», дросселирование — оранжевый пунктир ---
    for e in topo.get("edges", []):
        if e.get("from") not in pos or e.get("to") not in pos:
            continue
        x0, y0 = pos[e["from"]]
        x1, y1 = pos[e["to"]]
        thr = e.get("kind") == "throttle"
        outer, inner = ("#b8860b", "#f3cf5a") if thr else ("#2f6098", "#a9d2ef")
        dash = "dash" if thr else None
        for w, c in ((9, outer), (4, inner)):
            fig.add_trace(go.Scatter(x=[x0, x1], y=[y0, y1], mode="lines", hoverinfo="skip",
                                     showlegend=False, line=dict(color=c, width=w, dash=dash)))
        fig.add_annotation(x=x1, y=y1, ax=x0, ay=y0, xref="x", yref="y", axref="x", ayref="y",
                           text="", showarrow=True, arrowhead=3, arrowwidth=1.4,
                           arrowcolor="#2f4858", standoff=38, startstandoff=34, opacity=0.85)

    # --- узлы: боксы + подписи + прозрачный hover-слой ---
    hx, hy, htext = [], [], []
    for n in nodes:
        x, y = pos[n["id"]]
        typ = n.get("type", "node")
        au = pumps.get(n["id"])
        fill = eta_fill(au) if au is not None else _CAT_COLOR.get(typ, "#e0e0e0")
        border, bw = ("#e8a33d", 4.5) if (n.get("agg") and n["agg"] == sel_agg) else ("#5a6b7b", 1.4)
        fig.add_shape(type="rect", x0=x - 0.40, x1=x + 0.40, y0=y - 0.30, y1=y + 0.30,
                      line=dict(color=border, width=bw), fillcolor=fill, layer="above")
        fig.add_annotation(x=x, y=y + 0.07, showarrow=False, font=dict(size=11, color="#13212e"),
                           text="<b>" + str(n.get("label", "")).split("\n")[0] + "</b>")
        sub = n.get("sub") or " ".join(str(n.get("label", "")).split("\n")[1:])
        if sub:
            fig.add_annotation(x=x, y=y - 0.14, showarrow=False, font=dict(size=8, color="#3c4a57"),
                               text=str(sub).replace("\n", " "))
        hx.append(x)
        hy.append(y)
        htext.append(_node_hover(n, typ, au, rm))
    fig.add_trace(go.Scatter(x=hx, y=hy, mode="markers", showlegend=False, hoverinfo="text",
                             hovertext=htext, marker=dict(size=54, color="rgba(0,0,0,0)")))

    xs = [n["x"] for n in nodes] or [0]
    ys = [n["y"] for n in nodes] or [0]
    fig.update_xaxes(visible=False, range=[min(xs) - 0.85, max(xs) + 0.85])
    fig.update_yaxes(visible=False, range=[min(ys) - 1.0, max(ys) + 1.0])
    fig.update_layout(height=480, margin=dict(t=8, b=8, l=8, r=8), plot_bgcolor="white",
                      hoverlabel=dict(bgcolor="white", font_size=12), showlegend=False)
    return fig


with tab_scheme:
    st.subheader("Схема работы ППД и поток мощности")
    rm_s = agg.regime
    n_agg = len(obj.working_aggregates())
    topo = lib.get_topology(object_id)

    if topo:
        st.markdown(f"**{topo.get('title', 'Технологическая схема')}** — as-built по техсхеме")
        st.caption("🖱️ Наведите курсор на узел — что в нём происходит и фактические значения. "
                   "Насосы окрашены по КПД: 🟢 норма · 🟡 пониженный · 🔴 низкий. "
                   "Золотая рамка — выбранный агрегат · оранжевый пунктир — дросселирование.")
        st.plotly_chart(_topology_figure(topo, object_id, agg_id, rm_s),
                        width="stretch", config={"displayModeBar": False})
        st.caption(
            f"Источник: {topo.get('source', 'технологическая схема объекта')}. "
            f"Факт. режим выбранного агрегата: p_вх={fmt(rm_s.p_in, 2)} · p_вых={fmt(rm_s.p_out, 2)}"
            + (f" · p_БГ={fmt(rm_s.p_bg, 2)}" if rm_s.p_bg else "")
            + f" МПа · Q={fmt(rm_s.q_day, 0)} м³/сут.")
    else:
        st.caption("Типовая цепочка ППД с фактическими параметрами объекта. As-built топология "
                   "для этого объекта пока не заведена (`config/topology/<id>.yaml`).")
        # --- Параметрическая цепочка стадий (fallback) ---
        stages = [
            ("Источник /\nводоподготовка", "приём воды", "#cde3f0"),
            (f"КНС {obj.name}", f"НА ×{n_agg} · Q={fmt(rm_s.q_day, 0)} м³/сут", "#a8c8e0"),
            ("Выкид НА", f"p_вых={fmt(rm_s.p_out, 2)} МПа", "#a8c8e0"),
        ]
        if rm_s.p_bg:
            stages.append(("БГ / гребёнка", f"p_БГ={fmt(rm_s.p_bg, 2)} МПа", "#bcd9c6"))
        stages.append(("ЗРА / штуцеры", "дросселирование", "#e9d8a6"))
        stages.append(("Нагнетательные\nскважины", "приёмистость P–Q", "#e9c6a6"))
        stages.append(("Пласт", "отклик (CRM)", "#e6b8b8"))

        fig_s = go.Figure()
        n_st = len(stages)
        for i, (title, sub, color) in enumerate(stages):
            fig_s.add_shape(type="rect", x0=i - 0.45, x1=i + 0.45, y0=-0.5, y1=0.5,
                            line=dict(color="#557", width=1.5), fillcolor=color)
            fig_s.add_annotation(x=i, y=0.20, showarrow=False, font=dict(size=12),
                                 text="<b>" + title.replace("\n", "<br>") + "</b>")
            fig_s.add_annotation(x=i, y=-0.26, showarrow=False, font=dict(size=10, color="#333"),
                                 text=sub.replace("\n", "<br>"))
            if i < n_st - 1:
                fig_s.add_annotation(x=i + 0.55, y=0, ax=i + 0.45, ay=0, xref="x", yref="y",
                                     axref="x", ayref="y", text="", showarrow=True, arrowhead=2,
                                     arrowwidth=2, arrowcolor="#557")
        fig_s.add_annotation(x=0.5, y=0.66, showarrow=False, font=dict(size=10, color="#557"),
                             text=f"p_вх={fmt(rm_s.p_in, 2)} МПа")
        fig_s.update_xaxes(visible=False, range=[-0.7, n_st - 0.3])
        fig_s.update_yaxes(visible=False, range=[-0.95, 0.95])
        fig_s.update_layout(height=260, margin=dict(t=10, b=10, l=10, r=10), plot_bgcolor="white")
        st.plotly_chart(fig_s, width="stretch")

    # --- Sankey: поток мощности P_эл → полезная + потери ---
    st.markdown("**Поток мощности: P_эл → полезная мощность + статьи потерь**")
    useful_s, losses_s = loss_components(audit)
    losses_s = [(lbl, v) for lbl, v in losses_s if abs(v) > 1e-6]
    p_el_s = audit.regime.p_electric or 0.0
    # подписи с числами (кВт) — контраст не зависит от наложения текста на узлы
    node_labels = [f"P_эл  {fmt(p_el_s, 0)} кВт", f"Полезная  {fmt(useful_s, 0)}"] \
        + [f"{lbl}  {fmt(v, 0)}" for lbl, v in losses_s]
    node_colors = ["#2f80ed", "#2e9e6b"] + ["#e08a6b"] * len(losses_s)
    link_src = [0] * (1 + len(losses_s))
    link_tgt = list(range(1, 2 + len(losses_s)))
    link_val = [max(useful_s, 1e-9)] + [max(v, 1e-9) for _, v in losses_s]
    link_col = ["rgba(46,158,107,0.40)"] + ["rgba(224,138,107,0.38)"] * len(losses_s)
    fig_sk = go.Figure(go.Sankey(
        arrangement="snap",
        textfont=dict(color="#13212e", size=14, family="sans-serif"),
        node=dict(label=node_labels, color=node_colors, pad=26, thickness=22,
                  line=dict(color="#33495f", width=0.8)),
        link=dict(source=link_src, target=link_tgt, value=link_val, color=link_col)))
    fig_sk.update_layout(height=380, margin=dict(t=14, b=14, l=10, r=10),
                         font=dict(size=14, color="#13212e"), paper_bgcolor="white")
    st.plotly_chart(fig_sk, width="stretch")
    pct_useful = useful_s / p_el_s * 100 if p_el_s else 0.0
    st.caption(f"P_эл = {fmt(p_el_s, 1)} кВт · полезная {fmt(useful_s, 1)} кВт "
               f"({fmt(pct_useful, 1)} %). Ширина потока пропорциональна доле мощности.")


# ───────────────────────── Новый объект (онбординг) ─────────────────────────
with tab_newobj:
    import pandas as pd
    st.subheader("Подключение нового объекта: что нужно для расчёта")
    st.caption("Откуда модель берёт данные: телеметрия (автоматически) + паспорта/конфиг "
               "(вводятся один раз). Ниже — требования и проверка готовности текущего объекта.")

    st.markdown("### 1. Требуемая телеметрия (Методика, табл. 8.2.1)")
    st.dataframe(pd.DataFrame(TELEMETRY_REQUIREMENTS,
                              columns=["Параметр", "Обозн.", "Ед.", "Обязательность", "Источник"]),
                 width="stretch", hide_index=True)

    st.markdown("### 2. Что вводится вручную (паспорта и конфиг)")
    st.markdown(
        "- **Насос:** модель, тип (центробежный/объёмный), Q_ном, H_ном, η_нас.ном, P_ном, "
        "n об/мин, кривые Q-H и Q-η (координаты) — из паспорта/каталога.\n"
        "- **Электродвигатель:** модель, P_ном, η_ЭД.ном, cos φ, U, синхронный/асинхронный.\n"
        "- **ПЧ / трансмиссия:** наличие ПЧ (η_пч=0,97), КПД трансмиссии (если есть).\n"
        "- **Жидкость:** ρ и ν — по замеру; по умолчанию по типу воды из `config/fluids.yaml`.\n"
        "- **Эталоны для сверки** (опц.): инженерный `… расчет.xlsx` и текстовый отчёт `.doc`.")

    st.markdown("### 3. Готовность текущего объекта")
    rm_n = agg.regime
    p_n, m_n = agg.pump, agg.motor
    checks = [
        ("Телеметрия: p_вх", rm_n.p_in), ("Телеметрия: p_вых", rm_n.p_out),
        ("Телеметрия: p_БГ (КНС)", rm_n.p_bg), ("Телеметрия: Q_сут", rm_n.q_day),
        ("Телеметрия: W (ЭЭ/сут)", rm_n.w), ("Телеметрия: T (наработка)", rm_n.t),
        ("Плотность ρ", rm_n.rho),
        ("Паспорт насоса: H_ном", p_n.h_nom), ("Паспорт насоса: Q_ном", p_n.q_nom),
        ("Паспорт насоса: η_ном", p_n.eta_nom),
        ("Кривая Q-H", p_n.curve_qh if p_n.curve_qh else None),
        ("Паспорт ЭД: P_ном", m_n.p_nom), ("Паспорт ЭД: η_ном", m_n.eta_nom),
    ]

    def _val(v):
        if isinstance(v, (int, float)):
            return fmt(v, 3)
        return "список координат" if v else "—"

    st.dataframe(pd.DataFrame([{"Поле": k, "Статус": "✓ есть" if v else "— нет",
                                "Значение": _val(v)} for k, v in checks]),
                 width="stretch", hide_index=True)
    missing = [k for k, v in checks if not v]
    if missing:
        st.warning("Не заполнено: " + ", ".join(missing) + ". Часть полей опциональна "
                   "(объёмные насосы и объекты без паспортной кривой Q-H считаются корректно "
                   "по своей ветке расчёта).")
    else:
        st.success("Все ключевые поля заполнены.")

    st.markdown("### 4. Шаблон конфигурации")
    st.caption("Положить файлы в «НТУ цифровая платформа/<вид воды>/…», затем создать паспорт:")
    st.code(NEW_OBJECT_YAML_TEMPLATE, language="yaml")
    st.markdown("Чтобы объект попал в сверку — добавить запись в `config/verification.yaml`:")
    st.code(NEW_OBJECT_VERIFICATION_TEMPLATE, language="yaml")
    st.markdown("Затем выполнить (сконвертирует `.doc`, создаст `plants/<id>.yaml`, "
                "добавит объект в обе сверки и в дашборд):")
    st.code("python -m ppd_audit.verify", language="bash")
