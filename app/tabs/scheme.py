"""🗺️ Схема ППД — as-built технологическая схема или типовая цепочка."""

from __future__ import annotations

from datetime import timedelta

import lib
import plotly.graph_objects as go
import streamlit as st
import ui

from tabs.common import Ctx, fmt


_CAT_COLOR = {
    "source": "#d6e8f5",
    "prep": "#dbeaf2",
    "meter": "#e4e8ec",
    "pump": "#aacbe6",
    "manifold": "#c4e0cb",
    "valve": "#f0dca0",
    "wells": "#f0cfa6",
    "reservoir": "#eab8b8",
    "node": "#e0e0e0",
}


def _aggregate_pressure_text(snapshots, timestamp) -> str:
    """Давления НА только в точном timestamp выбранного снимка."""
    p_in, p_out = _pressure_labels(snapshots, timestamp)
    if p_in is None or p_out is None:
        return "p_вх/p_вых: нет данных"
    return f"{p_in} · {p_out}"


def _pressure_labels(snapshots, timestamp) -> tuple[str | None, str | None]:
    snapshot = next((item for item in snapshots if item.timestamp == timestamp), None)
    if snapshot is None:
        return None, None
    return (
        f"p_вх={fmt(snapshot.p_in_mpa, 2)} МПа",
        f"p_вых={fmt(snapshot.p_out_mpa, 2)} МПа",
    )


def _aggregate_pressure_labels(ctx: Ctx) -> dict[str, tuple[str | None, str | None]]:
    start = ctx.snapshot_timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        aggregate.id: _pressure_labels(
            lib.telemetry_snapshots(ctx.object_id, aggregate.id, start, start + timedelta(days=1)),
            ctx.snapshot_timestamp,
        )
        for aggregate in ctx.obj.aggregates
    }


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
        lines += [
            "─────────────",
            "состояние: <b>в работе</b>",
            f"КПД факт {fmt(r.eta_unit, 3)} / ном {fmt(r.eta_nom, 3)} — <b>{verdict}</b>",
            f"K_з {fmt(kz, 2)} · P_эл {fmt(r.p_electric, 0)} кВт · напор {fmt(r.h_fact, 0)} м",
            f"УРЭ факт {fmt(au.sec_fact, 3)} / расч {fmt(au.sec_calc, 3)} кВт·ч/м³",
            f"потери по КПД ≈ {fmt(au.dw_efficiency, 0)} кВт·ч/год",
        ]
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


def _topology_figure(topo, selected_audit, sel_agg, rm, pressure_labels):
    """Интерактивная as-built схема: трубопроводы + узлы с hover и подсветкой.

    Насосы подсвечиваются по КПД (зелёный/жёлтый/красный), выбранный агрегат — золотой
    рамкой. Наведение на узел показывает, что в нём происходит, и фактические значения.
    """
    nodes = topo.get("nodes", [])
    pos = {n["id"]: (n["x"], n["y"]) for n in nodes}
    nodes_by_id = {n["id"]: n for n in nodes}

    pumps = {
        n["id"]: selected_audit
        for n in nodes
        if n.get("type") == "pump" and n.get("agg") == sel_agg
    }

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
        source, target = nodes_by_id[e["from"]], nodes_by_id[e["to"]]
        thr = e.get("kind") == "throttle"
        outer, inner = ("#b8860b", "#f3cf5a") if thr else ("#2f6098", "#a9d2ef")
        dash = "dash" if thr else None
        for w, c in ((9, outer), (4, inner)):
            fig.add_trace(
                go.Scatter(
                    x=[x0, x1],
                    y=[y0, y1],
                    mode="lines",
                    hoverinfo="skip",
                    showlegend=False,
                    line=dict(color=c, width=w, dash=dash),
                )
            )
        fig.add_annotation(
            x=x1,
            y=y1,
            ax=x0,
            ay=y0,
            xref="x",
            yref="y",
            axref="x",
            ayref="y",
            text="",
            showarrow=True,
            arrowhead=3,
            arrowwidth=1.4,
            arrowcolor="#2f4858",
            standoff=38,
            startstandoff=34,
            opacity=0.85,
        )
        if target.get("type") == "pump":
            label = pressure_labels.get(target.get("agg"), (None, None))[0]
        elif source.get("type") == "pump":
            label = pressure_labels.get(source.get("agg"), (None, None))[1]
        else:
            label = None
        if label:
            fig.add_annotation(
                x=(x0 + x1) / 2,
                y=(y0 + y1) / 2,
                text=label,
                showarrow=False,
                font={"size": 10, "color": "#13212e"},
                bgcolor="white",
            )

    # --- узлы: боксы + подписи + прозрачный hover-слой ---
    hx, hy, htext = [], [], []
    for n in nodes:
        x, y = pos[n["id"]]
        typ = n.get("type", "node")
        au = pumps.get(n["id"])
        fill = eta_fill(au) if au is not None else _CAT_COLOR.get(typ, "#e0e0e0")
        border, bw = (
            ("#e8a33d", 4.5) if (n.get("agg") and n["agg"] == sel_agg) else ("#5a6b7b", 1.4)
        )
        fig.add_shape(
            type="rect",
            x0=x - 0.40,
            x1=x + 0.40,
            y0=y - 0.30,
            y1=y + 0.30,
            line=dict(color=border, width=bw),
            fillcolor=fill,
            layer="above",
        )
        fig.add_annotation(
            x=x,
            y=y + 0.07,
            showarrow=False,
            font=dict(size=11, color="#13212e"),
            text="<b>" + str(n.get("label", "")).split("\n")[0] + "</b>",
        )
        sub = n.get("sub") or " ".join(str(n.get("label", "")).split("\n")[1:])
        if sub:
            fig.add_annotation(
                x=x,
                y=y - 0.14,
                showarrow=False,
                font=dict(size=8, color="#3c4a57"),
                text=str(sub).replace("\n", " "),
            )
        hx.append(x)
        hy.append(y)
        htext.append(_node_hover(n, typ, au, rm))
    fig.add_trace(
        go.Scatter(
            x=hx,
            y=hy,
            mode="markers",
            showlegend=False,
            hoverinfo="text",
            hovertext=htext,
            marker=dict(size=54, color="rgba(0,0,0,0)"),
        )
    )

    xs = [n["x"] for n in nodes] or [0]
    ys = [n["y"] for n in nodes] or [0]
    fig.update_xaxes(visible=False, range=[min(xs) - 0.85, max(xs) + 0.85])
    fig.update_yaxes(visible=False, range=[min(ys) - 1.0, max(ys) + 1.0])
    fig.update_layout(
        height=480,
        margin=dict(t=8, b=8, l=8, r=8),
        plot_bgcolor="white",
        hoverlabel=dict(bgcolor="white", font_size=12),
        showlegend=False,
    )
    return fig


def _fallback_chain(ctx: Ctx, pressure_labels: dict[str, tuple[str | None, str | None]]) -> None:
    """Типовая параметрическая цепочка ППД, когда as-built топологии нет."""
    rm_s = ctx.agg.regime
    st.caption(
        "Типовая схема: параллельные ветви НА. As-built топология для этого объекта "
        "пока не заведена (`config/topology/<id>.yaml`)."
    )
    aggregates = ctx.obj.aggregates
    pump_y = [(len(aggregates) - 1) / 2 - index for index, _ in enumerate(aggregates)]
    stages = []
    if rm_s.p_bg:
        stages.append(("БГ / гребёнка", f"p_БГ={fmt(rm_s.p_bg, 2)} МПа", "#bcd9c6"))
    stages.append(("ЗРА / штуцеры", "дросселирование", "#e9d8a6"))
    stages.append(("Нагнетательные\nскважины", "приёмистость P–Q", "#e9c6a6"))
    stages.append(("Пласт", "отклик (CRM)", "#e6b8b8"))

    fig_s = go.Figure()

    def box(x, y, title, sub, color, *, selected: bool = False):
        fig_s.add_shape(
            type="rect",
            x0=x - 0.45,
            x1=x + 0.45,
            y0=y - 0.36,
            y1=y + 0.36,
            line={
                "color": "#e8a33d" if selected else "#557",
                "width": 3 if selected else 1.5,
            },
            fillcolor=color,
        )
        fig_s.add_annotation(
            x=x,
            y=y + 0.13,
            showarrow=False,
            font={"size": 12},
            text="<b>" + title.replace("\n", "<br>") + "</b>",
        )
        fig_s.add_annotation(
            x=x,
            y=y - 0.18,
            showarrow=False,
            font={"size": 10, "color": "#333"},
            text=sub.replace("\n", "<br>"),
        )

    def arrow(x0, y0, x1, y1, label: str | None = None):
        fig_s.add_annotation(
            x=x1,
            y=y1,
            ax=x0,
            ay=y0,
            xref="x",
            yref="y",
            axref="x",
            ayref="y",
            text="",
            showarrow=True,
            arrowhead=2,
            arrowwidth=2,
            arrowcolor="#557",
        )
        if label:
            fig_s.add_annotation(
                x=(x0 + x1) / 2,
                y=(y0 + y1) / 2,
                showarrow=False,
                font={"size": 10, "color": "#13212e"},
                text=label,
                bgcolor="white",
            )

    box(0, 0, "Источник /\nводоподготовка", "приём воды", "#cde3f0")
    for aggregate, y in zip(ctx.obj.aggregates, pump_y, strict=True):
        selected = aggregate.id == ctx.agg_id
        box(
            1.5,
            y,
            aggregate.id,
            aggregate.pump.model,
            "#a8c8e0",
            selected=selected,
        )
        p_in, p_out = pressure_labels[aggregate.id]
        arrow(0.45, 0, 1.05, y, p_in)
        arrow(1.95, y, 2.55, 0, p_out)

    for index, (title, sub, color) in enumerate(stages):
        x = 3 + index
        box(x, 0, title, sub, color)
        arrow(x - 0.55, 0, x - 0.45, 0)

    fig_s.update_xaxes(visible=False, range=[-0.7, len(stages) + 3.0])
    fig_s.update_yaxes(
        visible=False,
        range=[min(pump_y, default=0) - 0.8, max(pump_y, default=0) + 0.8],
    )
    fig_s.update_layout(
        height=max(260, 120 * len(aggregates)),
        margin={"t": 10, "b": 10, "l": 10, "r": 10},
        plot_bgcolor="white",
    )
    st.plotly_chart(fig_s, width="stretch")


def render(ctx: Ctx) -> None:
    st.subheader("Схема работы ППД")
    rm_s = ctx.agg.regime
    topo = lib.get_topology(ctx.object_id)
    pressure_labels = _aggregate_pressure_labels(ctx)

    if topo:
        st.markdown(f"**{topo.get('title', 'Технологическая схема')}** — as-built по техсхеме")
        ui.provenance(("As-built схема", "ok"), ("Расчётные показатели", ""))
        st.caption(
            "🖱️ Наведите курсор на узел — что в нём происходит и фактические значения. "
            "Насосы окрашены по КПД: 🟢 норма · 🟡 пониженный · 🔴 низкий. "
            "Золотая рамка — выбранный агрегат · оранжевый пунктир — дросселирование."
        )
        st.plotly_chart(
            _topology_figure(topo, ctx.audit, ctx.agg_id, rm_s, pressure_labels),
            width="stretch",
            config={"displayModeBar": False},
        )
        st.caption(
            f"Источник: {topo.get('source', 'технологическая схема объекта')}. "
            f"Факт. режим выбранного агрегата: p_вх={fmt(rm_s.p_in, 2)} · p_вых={fmt(rm_s.p_out, 2)}"
            + (f" · p_БГ={fmt(rm_s.p_bg, 2)}" if rm_s.p_bg else "")
            + f" МПа · Q={fmt(rm_s.q_day, 0)} м³/сут."
        )
    else:
        ui.provenance(("Типовая схема", "warn"), ("Расчётные показатели", ""))
        _fallback_chain(ctx, pressure_labels)
