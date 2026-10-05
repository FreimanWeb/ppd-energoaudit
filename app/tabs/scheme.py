"""Схема ППД — as-built технологическая схема или типовая цепочка."""

from __future__ import annotations

import re
from datetime import timedelta
from html import escape
from pathlib import Path

import lib
import streamlit as st
import ui

from tabs.common import Ctx, fmt


def _aggregate_pressure_text(snapshots, timestamp) -> str:
    """Давления НА только в точный момент выбранного показателя."""
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


def _topology_svg(topo, selected_audit, sel_agg, rm, pressure_labels) -> str:
    """Предметная схема оборудования; топология и давления остаются исходными."""
    nodes = topo.get("nodes", [])
    by_id = {node["id"]: node for node in nodes}
    max_y = max((node["y"] for node in nodes), default=0)
    min_x = min((node["x"] for node in nodes), default=0)
    pos = {
        node["id"]: (
            110 + (node["x"] - min_x) * 220,
            100 + (max_y - node["y"]) * 150 + (160 if node.get("type") == "reservoir" else 0),
        )
        for node in nodes
    }
    width = max((x for x, _ in pos.values()), default=600) + 140
    height = max(
        (y + (190 if by_id[key].get("type") == "wells" else 90) for key, (_, y) in pos.items()),
        default=250,
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        'role="img" aria-label="Технологическая схема ППД" class="ppd-equipment">',
        "<title>Система ППД: оборудование, водоводы, скважины и пласт</title>",
        (Path(__file__).resolve().parents[2] / "shared" / "ppd-symbols.svg").read_text(),
        '<rect width="100%" height="100%" rx="12" fill="#f8fbfa"/>',
    ]
    pump_pos = [pos[n["id"]] for n in nodes if n.get("type") == "pump"]
    if pump_pos:
        x0 = min(x for x, _ in pump_pos) - 100
        y0 = min(y for _, y in pump_pos) - 70
        hall_height = max(y for _, y in pump_pos) - y0 + 70
        parts.append(
            f'<rect x="{x0}" y="{y0}" width="200" height="{hall_height}" '
            'rx="10" fill="#edf4f1" stroke="#d8e3df"/>'
            f'<text x="{x0 + 12}" y="{y0 + 18}" class="ppd-hall">МАШИННЫЙ ЗАЛ</text>'
        )
    # Соединения рисуются раньше оборудования, чтобы трубы не проходили поверх него.
    for edge in topo.get("edges", []):
        source, target = by_id.get(edge.get("from")), by_id.get(edge.get("to"))
        if source is None or target is None:
            continue
        x0, y0 = pos[source["id"]]
        x1, y1 = pos[target["id"]]
        if source.get("type") == "wells":
            y0 += 160
        else:
            x0 += 72 if source.get("type") == "pump" else 40
        x1 -= 72 if target.get("type") == "pump" else 40
        if target.get("type") == "reservoir":
            x1 += 40
        middle = (x0 + x1) / 2
        throttled = edge.get("kind") == "throttle"
        color = "#c58b25" if throttled else "#4a5d57"
        dash = ' stroke-dasharray="7 4"' if throttled else ""
        parts.append(
            f'<g data-from="{escape(source["id"], quote=True)}" '
            f'data-to="{escape(target["id"], quote=True)}">'
            f'<path d="M{x0} {y0} H{middle} V{y1} H{x1}" '
            f'fill="none" stroke="{color}" stroke-width="3"{dash} '
            'marker-end="url(#ppd-flow)"/>'
        )
        if target.get("type") == "pump":
            label = pressure_labels.get(target.get("agg"), (None, None))[0]
        elif source.get("type") == "pump":
            label = pressure_labels.get(source.get("agg"), (None, None))[1]
        else:
            label = None
        if label:
            label_y = y1 - 40 if target.get("type") == "pump" else y0 - 40
            parts.append(
                f'<text x="{middle}" y="{label_y}" class="ppd-pressure">{escape(label)}</text>'
            )
        parts.append("</g>")
    # Пласт находится позади скважины и её перфорации.
    for node in sorted(nodes, key=lambda n: n.get("type") != "reservoir"):
        x, y = pos[node["id"]]
        typ = node.get("type", "node")
        selected = bool(node.get("agg") and node["agg"] == sel_agg)
        audit = selected_audit if selected and typ == "pump" else None
        fill = "white"
        if audit is not None:
            ratio = audit.regime.eta_unit / audit.regime.eta_nom if audit.regime.eta_nom else 1
            fill = "#cfe8dc" if ratio >= 0.9 else ("#f6e3b4" if ratio >= 0.78 else "#f2cecb")
        symbol = (
            typ
            if typ in {"source", "prep", "meter", "pump", "valve", "wells", "reservoir"}
            else "manifold"
        )
        if typ == "manifold" and "выкид" in node.get("label", "").lower():
            symbol = "meter"
        if typ == "prep" and "ёмк" in node.get("label", "").lower():
            symbol = "source"
        hover = _node_hover(node, typ, audit, rm).replace("<br>", "\n")
        hover = re.sub(r"</?b>", "", hover)
        parts.append(
            f'<g data-node="{escape(node["id"], quote=True)}" '
            f'data-selected="{str(selected).lower()}" transform="translate({x} {y})" '
            f'style="color:{"#1f4e4a" if selected else "#4a5d57"};--pump-fill:{fill}">'
            f"<title>{escape(hover)}</title>"
            f'<use href="#ppd-{symbol}"/>'
        )
        label_y = -45 if typ == "wells" else (8 if typ == "reservoir" else 55)
        label = str(node.get("label", "")).replace("\n", " ")
        parts.append(f'<text y="{label_y}" class="ppd-label">{escape(label)}</text>')
        sub = str(node.get("sub", "")).replace("\n", " ")
        if sub:
            parts.append(f'<text y="{label_y + 17}" class="ppd-sub">{escape(sub)}</text>')
        if selected:
            parts.append(
                '<rect x="-82" y="-33" width="164" height="66" '
                'rx="8" fill="none" stroke="#c58b25" stroke-width="2"/>'
            )
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


def _fallback_topology(ctx: Ctx) -> dict:
    """Та же предметная схема для объектов без описания топологии."""
    nodes = [{"id": "src", "type": "source", "x": 0, "y": 0, "label": "Приём воды"}]
    edges = []
    count = len(ctx.obj.aggregates)
    for index, aggregate in enumerate(ctx.obj.aggregates):
        node_id = f"pump-{index}"
        nodes.append({
            "id": node_id,
            "type": "pump",
            "agg": aggregate.id,
            "x": 1,
            "y": (count - 1) / 2 - index,
            "label": aggregate.id,
            "sub": aggregate.pump.model or "",
        })
        edges.extend([{"from": "src", "to": node_id}, {"from": node_id, "to": "man"}])
    nodes.extend([
        {"id": "man", "type": "meter", "x": 2, "y": 0, "label": "Выход из станции"},
        {
            "id": "comb",
            "type": "manifold",
            "x": 3,
            "y": 0,
            "label": "Блок гребёнок",
            "sub": f"p_БГ={fmt(ctx.agg.regime.p_bg, 2)} МПа"
            if ctx.agg.regime.p_bg is not None
            else "",
        },
        {"id": "valve", "type": "valve", "x": 4, "y": 0, "label": "ЗРА / штуцеры"},
        {"id": "wells", "type": "wells", "x": 5, "y": 0, "label": "Нагнетательные скважины"},
        {"id": "res", "type": "reservoir", "x": 6, "y": 0, "label": "Пласт / призабойная зона"},
    ])
    edges.extend([
        {"from": "man", "to": "comb"},
        {"from": "comb", "to": "valve"},
        {"from": "valve", "to": "wells", "kind": "throttle"},
        {"from": "wells", "to": "res"},
    ])
    return {"nodes": nodes, "edges": edges}


def render(ctx: Ctx) -> None:
    st.subheader("Схема работы ППД — оборудование и водоводы")
    topo = lib.get_topology(ctx.object_id)
    if topo:
        st.markdown(f"**{topo.get('title', 'Технологическая схема')}**")
        ui.provenance(("Схема по технологическим материалам", "ok"), ("Расчётные показатели", ""))
        st.caption(f"Источник: {topo.get('source', 'технологическая схема объекта')}.")
    else:
        topo = _fallback_topology(ctx)
        ui.provenance(("Типовая схема", "warn"), ("Расчётные показатели", ""))
        st.caption("Типовая цепочка: ветви агрегатов из паспорта; расположение водоводов условное.")
    st.caption(
        "Насос: зелёный — КПД близок к номинальному, жёлтый — понижен, красный — низкий. "
        "Золотая рамка — выбранный агрегат; пунктир — участок дросселирования. "
        "Подробности — при наведении на оборудование."
    )
    svg = _topology_svg(
        topo, ctx.audit, ctx.agg_id, ctx.agg.regime, _aggregate_pressure_labels(ctx)
    )
    st.markdown(
        """<style>
        .ppd-scheme {overflow-x:auto;border:1px solid #d8e3df;border-radius:12px;}
        .ppd-equipment {display:block;width:100%;min-width:1000px;font-family:Segoe UI,Arial;}
        .ppd-equipment text {fill:#26332f;text-anchor:middle;}
        .ppd-label {font-size:13px;font-weight:600;}
        .ppd-sub {font-size:11px;fill:#5a6b66!important;}
        .ppd-pressure {font-size:11px;paint-order:stroke;stroke:#f8fbfa;stroke-width:5px;}
        .ppd-hall {font-size:11px;font-weight:700;
                   text-anchor:start!important;fill:#1f4e4a!important;}
        .ppd-equipment [data-node]:hover {filter:drop-shadow(0 0 3px #b9ccc5);}
        </style>"""
        + f'<div class="ppd-scheme">{svg}</div>',
        unsafe_allow_html=True,
    )
