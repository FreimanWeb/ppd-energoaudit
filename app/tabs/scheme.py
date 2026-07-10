"""🗺️ Схема ППД — as-built технологическая схема (или типовая цепочка) + Sankey мощности."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

import lib
from tabs.common import Ctx, fmt, loss_components

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


def _fallback_chain(ctx: Ctx) -> None:
    """Типовая параметрическая цепочка ППД, когда as-built топологии нет."""
    obj, rm_s = ctx.obj, ctx.agg.regime
    n_agg = len(obj.working_aggregates())
    st.caption("Типовая цепочка ППД с фактическими параметрами объекта. As-built топология "
               "для этого объекта пока не заведена (`config/topology/<id>.yaml`).")
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


def _sankey(ctx: Ctx) -> None:
    st.markdown("**Поток мощности: P_эл → полезная мощность + статьи потерь**")
    audit = ctx.audit
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


def render(ctx: Ctx) -> None:
    st.subheader("Схема работы ППД и поток мощности")
    rm_s = ctx.agg.regime
    topo = lib.get_topology(ctx.object_id)

    if topo:
        st.markdown(f"**{topo.get('title', 'Технологическая схема')}** — as-built по техсхеме")
        st.caption("🖱️ Наведите курсор на узел — что в нём происходит и фактические значения. "
                   "Насосы окрашены по КПД: 🟢 норма · 🟡 пониженный · 🔴 низкий. "
                   "Золотая рамка — выбранный агрегат · оранжевый пунктир — дросселирование.")
        st.plotly_chart(_topology_figure(topo, ctx.object_id, ctx.agg_id, rm_s),
                        width="stretch", config={"displayModeBar": False})
        st.caption(
            f"Источник: {topo.get('source', 'технологическая схема объекта')}. "
            f"Факт. режим выбранного агрегата: p_вх={fmt(rm_s.p_in, 2)} · p_вых={fmt(rm_s.p_out, 2)}"
            + (f" · p_БГ={fmt(rm_s.p_bg, 2)}" if rm_s.p_bg else "")
            + f" МПа · Q={fmt(rm_s.q_day, 0)} м³/сут.")
    else:
        _fallback_chain(ctx)

    _sankey(ctx)
