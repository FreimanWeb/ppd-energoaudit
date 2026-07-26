"""Парсер текстовых отчётов энергоаудита («Промежуточный отчет НТУ по …», .docx).

Отчёты — независимый «человеческий» эталон: те же объекты описаны прозой и таблицами
(паспорт насоса/ЭД, исходные параметры, электропотребление «Проток», энергетические
параметры, годовые потери, ТЭО, рекомендации). Извлекаем И таблицы, И числовые
утверждения из прозы — в т.ч. ОТНОСИТЕЛЬНЫЕ:

  «КПД НА снижен на X п.п.»          → eta_reduction_pp   (модель: (η_ном−η_факт)·100)
  «УРЭ больше/превышает расч. на X»  → sec_over_calc      (модель: УРЭ_ф − УРЭ_р)
  «рабочая точка ниже Q-H на N м (Z %)» → head_drop_m / head_drop_pct

Поддерживаются два шаблона:
  · 2024 — агрегаты в виде столбцов значений (КНС-25/155/10/154);
  · 2026 — на каждый агрегат своя таблица с несколькими датами замера; агрегат
    определяется по подписи таблицы («… параметров Н-1 …»), значение берём по
    последней (самой поздней) дате.

Бинарные «.doc» предварительно конвертируются (см. convert.py).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pydantic import BaseModel, Field

from ..spec import ReferenceOutputs, WaterType


# ───────────────────────────── модели фактов отчёта ─────────────────────────────


class ReportClaim(BaseModel):
    """Относительное утверждение из прозы отчёта (может быть диапазоном X…Y)."""

    metric: (
        str  # eta_reduction_pp | sec_over_calc | head_drop_m | head_drop_pct | eta_curve_drop_pp
    )
    value_min: float
    value_max: float  # = value_min, если не диапазон
    unit: str = ""
    aggregate_id: str | None = None
    text: str = ""

    @property
    def value(self) -> float:
        return (self.value_min + self.value_max) / 2.0


class AggregateReport(BaseModel):
    id: str  # НА-1..n
    pump_model: str = ""
    reference: ReferenceOutputs = Field(default_factory=ReferenceOutputs)
    # диапазон [min, max] значений по датам замера (2026: несколько дат; 2024: [v, v]).
    # Модель/xlsx считаются для ОДНОГО замера → сверяем попадание модели в диапазон отчёта.
    ranges: dict[str, list[float]] = Field(default_factory=dict)
    claims: list[ReportClaim] = Field(default_factory=list)

    def range_of(self, field: str) -> tuple[float, float] | None:
        r = self.ranges.get(field)
        return (r[0], r[1]) if r else None


class ObjectReport(BaseModel):
    object_id: str
    object_name: str
    water_type: WaterType = WaterType.fresh
    template: str = "2024"  # 2024 | 2026
    source: str = ""  # путь к разобранному .docx
    source_original: str = ""  # исходный .doc/.docx
    report_date: str = ""
    aggregates: list[AggregateReport] = Field(default_factory=list)
    teo: dict = Field(default_factory=dict)  # сводка ТЭО (потери, экономия, окупаемость)
    recommendations: list[str] = Field(default_factory=list)
    quotes: list[str] = Field(default_factory=list)  # ключевые выводы (цитаты)

    def aggregate(self, agg_id: str) -> AggregateReport | None:
        for a in self.aggregates:
            if a.id == agg_id:
                return a
        return None


# ───────────────────────────── низкоуровневые утилиты ─────────────────────────────

_MONTHS = (
    "январ",
    "феврал",
    "март",
    "апрел",
    "ма",
    "июн",
    "июл",
    "август",
    "сентябр",
    "октябр",
    "ноябр",
    "декабр",
)


def _norm(v) -> str:
    if v is None:
        return ""
    s = str(v).replace("\xa0", " ").replace(" ", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", s.strip().lower().replace("ё", "е"))


def _num(v) -> float | None:
    """Первое число из ячейки (рус. формат): «5 411»→5411, «1 234,6»→1234.6, «н/д»→None."""
    if v is None:
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("\xa0", " ").replace(" ", " ").replace(" ", " ")
    s = re.sub(r"(?<=\d)[ \t]+(?=\d)", "", s)  # пробел как разделитель тысяч
    s = s.replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    return float(m.group()) if m else None


def _iter_blocks(doc: Any):
    """Параграфы и таблицы в порядке документа: ('p', text) | ('tbl', grid)."""
    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            yield "p", Paragraph(child, doc).text
        elif tag == "tbl":
            tbl = Table(child, doc)
            grid = [[c.text for c in row.cells] for row in tbl.rows]
            yield "tbl", grid


def _grid_has_dates(grid: list[list[str]]) -> bool:
    """Есть ли в шапке (первые 3 строки) подпись-дата → шаблон 2026 (ряд замеров)."""
    for row in grid[:3]:
        for cell in row:
            t = _norm(cell)
            if re.search(r"\d{1,2}\s+(" + "|".join(_MONTHS) + r")", t):
                return True
    return False


def _agg_num(text: str) -> int | None:
    """Номер агрегата из подписи: «Н-1», «насосного агрегата № 2», «НА-3»."""
    t = _norm(text)
    m = re.search(r"(?:на|н)\s*[-–]\s*(\d)", t)  # Н-1 / НА-1
    if m:
        return int(m.group(1))
    m = re.search(r"агрегат\w*\s*(?:№\s*)?(\d)", t)
    if m:
        return int(m.group(1))
    m = re.search(r"№\s*(\d)", t)
    if m:
        return int(m.group(1))
    return None


def _row_label(row: list[str]) -> str:
    """Метка строки = первая непустая ячейка."""
    for c in row:
        t = _norm(c)
        if t:
            return t
    return ""


# Метки строк значений: поле ReferenceOutputs → паттерны (искл.).
_VALUE_LABELS: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = [
    ("h_fact", ("напор",), ("должн", "ожидаем", "паспорт")),
    ("p_hydraulic", ("гидравлическая мощность",), ("ожидаем", "расчетной", "расчётной")),
    ("p_electric", ("электрическая мощность",), ("ожидаем",)),
    ("eta_fact", ("кпд среднесут", "кпд на среднесут"), ()),
    ("eta_nom", ("кпд в номинальн", "кпд на в ном", "кпд в ном"), ()),
    ("sec_fact", ("урэ фактическ",), ()),
    ("sec_calc", ("урэ расчетн", "урэ расчётн"), ("ожидаем",)),
    ("load_factor", ("коэффициент загруз",), ("ожидаем", "k´", "k'")),
    ("t_year", ("годовая нараб",), ("планир",)),
]
_DW_EFF_PATS = ("уменьшением кпд", "снижением кпд", "снижения кпд")
_DW_THR_PATS = ("дросселир",)


# ───────────────────────────── шаблон 2024 (столбцы-агрегаты) ─────────────────────────────


def _passport_pumps(grids: list[list[list[str]]]) -> list[str]:
    """Модели насосов из паспортной таблицы (по строкам с номером НА)."""
    for g in grids:
        if any("тип насос" in _norm(c) for c in (g[0] if g else [])):
            models = []
            for row in g[1:]:
                if _num(row[0]) is not None and len(row) > 1 and _norm(row[1]):
                    models.append(str(row[1]).strip())
            if models:
                return models
    return []


def _find_value_row(grids, *pats, exclude=()):
    for g in grids:
        for row in g:
            lbl = _row_label(row)
            if not lbl:
                continue
            if any(p in lbl for p in pats) and not any(e in lbl for e in exclude):
                return row
    return None


def _trailing_values(row: list[str], n: int) -> list[float | None]:
    """Последние n числовых значений строки (хвостовые столбцы-агрегаты)."""
    return [_num(c) for c in row[-n:]] if n else []


def _parse_2024(grids, n_agg: int) -> tuple[list[ReferenceOutputs], list[dict]]:
    refs = [ReferenceOutputs() for _ in range(n_agg)]
    ranges: list[dict] = [{} for _ in range(n_agg)]

    def assign(field: str, vals: list[float | None]):
        for i in range(n_agg):
            v = vals[i] if i < len(vals) else None
            if v is not None:
                setattr(refs[i], field, v)
                ranges[i][field] = [v, v]

    for field, pats, excl in _VALUE_LABELS:
        row = _find_value_row(grids, *pats, exclude=excl)
        if row is not None:
            assign(field, _trailing_values(row, n_agg))
    # годовые потери по КПД (ΔWкпд) — отдельной строкой
    row = _find_value_row(grids, *_DW_EFF_PATS)
    if row is not None:
        assign("dw_efficiency", _trailing_values(row, n_agg))
    return refs, ranges


# ───────────────────────────── шаблон 2026 (таблица на агрегат) ─────────────────────────────


def _ts_values(row: list[str], n_label: int = 3) -> list[float]:
    """Все числовые значения-замеры строки (столбцы дат, после столбцов-меток)."""
    return [v for v in (_num(c) for c in row[n_label:]) if v is not None]


def _read_timeseries(grid, ref: ReferenceOutputs, rng: dict) -> None:
    """Заполнить ref последним замером и rng[field]=[min,max] по всем датам."""
    for row in grid:
        lbl = _row_label(row)
        if not lbl:
            continue
        for field, pats, excl in _VALUE_LABELS:
            if any(p in lbl for p in pats) and not any(e in lbl for e in excl):
                vals = _ts_values(row)
                if vals:
                    setattr(ref, field, vals[-1])  # последняя (поздняя) дата
                    prev = rng.get(field, [vals[0], vals[0]])
                    rng[field] = [min(prev[0], *vals), max(prev[1], *vals)]
                break


def _annual_loss_col(grid) -> int | None:
    """Индекс столбца «кВт·ч» в таблице годовых потерь (2026: [назв|обозн|кВт·ч|тыс.руб])."""
    for row in grid[:2]:
        for j, c in enumerate(row):
            t = _norm(c)
            if "квт·ч" in t or "квт.ч" in t:
                return j
    return None


def _read_annual_loss(grid, ref: ReferenceOutputs, rng: dict) -> None:
    col = _annual_loss_col(grid)
    if col is None:
        return
    for row in grid:
        lbl = _row_label(row)
        v = _num(row[col]) if col < len(row) else None
        if v is None:
            continue
        if any(p in lbl for p in _DW_EFF_PATS):
            ref.dw_efficiency = v
            rng["dw_efficiency"] = [v, v]
        elif any(p in lbl for p in _DW_THR_PATS):
            ref.dw_throttle = v
            rng["dw_throttle"] = [v, v]


def _parse_2026(blocks) -> list[AggregateReport]:
    aggs: dict[int, AggregateReport] = {}
    caption = ""
    for kind, payload in blocks:
        if kind == "p":
            if payload.strip():
                caption = payload
            continue
        grid = payload
        hdr = " ".join(_norm(c) for c in (grid[0] if grid else []))
        is_cont = "продолжение" in hdr
        if _grid_has_dates(grid):  # таблица ряда замеров агрегата
            num = _agg_num(caption) or (max(aggs) if (is_cont and aggs) else None)
            if num is None:
                num = (max(aggs) + 1) if aggs else 1
            ar = aggs.setdefault(num, AggregateReport(id=f"НА-{num}"))
            _read_timeseries(grid, ar.reference, ar.ranges)
        elif "годовые потери" in _norm(caption) or _annual_loss_col(grid) is not None:
            num = _agg_num(caption)
            if num in aggs:
                _read_annual_loss(grid, aggs[num].reference, aggs[num].ranges)
    return [aggs[k] for k in sorted(aggs)]


# ───────────────────────────── проза: относительные утверждения ─────────────────────────────

_RANGE = r"([\d.,]+)\s*(?:[…\-–]{1,3}\s*([\d.,]+))?"


def _mk_claim(metric: str, m: re.Match, unit: str, agg_id, text: str) -> ReportClaim | None:
    lo = _num(m.group(1))
    if lo is None:
        return None
    hi = _num(m.group(2)) if m.lastindex and m.group(2) else lo
    if hi is None:
        hi = lo
    return ReportClaim(
        metric=metric,
        value_min=min(lo, hi),
        value_max=max(lo, hi),
        unit=unit,
        aggregate_id=agg_id,
        text=text.strip()[:300],
    )


def _extract_claims(sentences: list[str], single_agg: str | None) -> list[ReportClaim]:
    claims: list[ReportClaim] = []
    for raw in sentences:
        t = _norm(raw)
        agg = None
        an = _agg_num(raw)
        if an is not None:
            agg = f"НА-{an}"
        elif single_agg:
            agg = single_agg

        # КПД НА снижен на X[…Y] п.п./% (относительно номинального)
        m = re.search(r"кпд[^.]*?сниж\w*\s*(?:на)?\s*" + _RANGE + r"\s*(?:п\.?\s*п|%)", t)
        if m and (
            "номинал" in t or "номин" in t or "относительно ном" in t or "п.п" in t or "п. п" in t
        ):
            if "паспортн" not in t.split("снижен")[0][-40:]:
                c = _mk_claim("eta_reduction_pp", m, "п.п.", agg, raw)
                if c:
                    claims.append(c)
        # КПД насоса относительно паспортной характеристики снижен на X[…Y] п.п.
        m = re.search(
            r"кпд[^.]*?паспортн[^.]*?сниж\w*\s*(?:на)?\s*" + _RANGE + r"\s*(?:п\.?\s*п|%)", t
        )
        if m:
            c = _mk_claim("eta_curve_drop_pp", m, "п.п.", agg, raw)
            if c:
                claims.append(c)
        # УРЭ больше/превышает расчётного на X[…Y] кВт·ч/м³
        m = re.search(r"урэ[^.]*?(?:превыша\w*|больше)[^.]*?расч\w*[^.]*?на\s*" + _RANGE, t)
        if m:
            c = _mk_claim("sec_over_calc", m, "кВт·ч/м³", agg, raw)
            if c:
                claims.append(c)
        # напор/рабочая точка ниже Q-H на N м (Z %)
        m = re.search(
            r"(?:напор|рабоч\w* точк\w*|располагается)[^.]*?ниже[^.]*?на\s*"
            r"([\d.,]+)\s*м[^.()]*\(\s*([\d.,]+)\s*%",
            t,
        )
        if not m:
            m = re.search(
                r"напор[^.]*?сниж\w*\s*(?:на)?\s*([\d.,]+)\s*м[^.()]*\(\s*([\d.,]+)\s*%", t
            )
        if m:
            head_drop_m, head_drop_pct = _num(m.group(1)), _num(m.group(2))
            assert head_drop_m is not None and head_drop_pct is not None
            claims.append(
                ReportClaim(
                    metric="head_drop_m",
                    value_min=head_drop_m,
                    value_max=head_drop_m,
                    unit="м",
                    aggregate_id=agg,
                    text=raw.strip()[:300],
                )
            )
            claims.append(
                ReportClaim(
                    metric="head_drop_pct",
                    value_min=head_drop_pct,
                    value_max=head_drop_pct,
                    unit="%",
                    aggregate_id=agg,
                    text=raw.strip()[:300],
                )
            )
        else:
            # напор относительно паспортной характеристики снижен на X[…Y] %
            m = re.search(r"напор[^.]*?паспортн[^.]*?сниж\w*\s*(?:на)?\s*" + _RANGE + r"\s*%", t)
            if m:
                c = _mk_claim("head_drop_pct", m, "%", agg, raw)
                if c:
                    claims.append(c)
    return claims


# ───────────────────────────── ТЭО / рекомендации ─────────────────────────────


def _parse_teo_2024(grids) -> dict[str, Any]:
    """Карта потерь/ТЭО (таблица «Направление потерь … ЧДД … окупаемость»)."""
    teo: dict[str, Any] = {"measures": []}
    for g in grids:
        head = " ".join(_norm(c) for c in (g[0] if g else []))
        if "направление потерь" not in head:
            continue
        # карта колонок по двум строкам шапки
        hdr = [
            " ".join(_norm(g[r][c]) for r in range(min(2, len(g))) if c < len(g[r]))
            for c in range(len(g[0]))
        ]

        def col(*pats):
            for j, h in enumerate(hdr):
                if any(p in h for p in pats):
                    return j
            return None

        c_kwh = col("квт∙ч", "квт·ч", "квт.ч")
        c_rub = col("тыс.руб", "тыс. руб")
        c_meas = col("предлагаемое", "мероприятие")
        c_pay = col("окупаемост")
        c_elem = col("элемент технолог")
        c_prob = col("выявленные проблем")
        for row in g[2:]:
            lbl = _row_label(row)
            kwh = _num(row[c_kwh]) if c_kwh is not None and c_kwh < len(row) else None
            if lbl.startswith("всего") or "итого" in lbl:
                teo["total_loss_kwh"] = kwh
                teo["total_loss_krub"] = (
                    _num(row[c_rub]) if c_rub is not None and c_rub < len(row) else None
                )
                continue
            meas = str(row[c_meas]).strip() if c_meas is not None and c_meas < len(row) else ""
            if "насос" in lbl and (kwh or meas):
                teo["measures"].append({
                    "element": str(row[c_elem]).strip()
                    if c_elem is not None and c_elem < len(row)
                    else "",
                    "problem": str(row[c_prob]).strip()
                    if c_prob is not None and c_prob < len(row)
                    else "",
                    "loss_kwh": kwh,
                    "loss_krub": _num(row[c_rub])
                    if c_rub is not None and c_rub < len(row)
                    else None,
                    "measure": meas,
                    "payback": str(row[c_pay]).strip()
                    if c_pay is not None and c_pay < len(row)
                    else "",
                })
        break
    # «Всего» в отчётах иногда в тыс.кВт·ч (смешение единиц) — берём надёжную сумму по НА
    losses_kwh = [m["loss_kwh"] for m in teo["measures"] if m.get("loss_kwh")]
    if losses_kwh:
        teo["total_loss_kwh"] = round(sum(losses_kwh), 1)
    return teo


def _parse_teo_2026(grids, paras) -> dict:
    teo: dict = {"measures": []}
    # Сводный реестр потерь → итог
    for g in grids:
        head = " ".join(_norm(c) for c in (g[0] if g else []))
        if "реестр потерь" in head or "сводный реестр" in head:
            for row in g:
                lbl = _row_label(row)
                if "итого" in lbl or lbl.startswith("всего"):
                    nums = [_num(c) for c in row if _num(c) is not None]
                    if nums:
                        teo["total_loss_kwh"] = nums[0]
    # окупаемость / ЧДД из прозы
    for p in paras:
        t = _norm(p)
        if "не окупается" in t or ("чдд" in t and ("< 0" in t or "<0" in t)):
            teo.setdefault("headline", p.strip()[:300])
        m = re.search(r"окупаемост\w*[^.]*?(менее\s*[\d.,]+\s*год\w*)", t)
        if m:
            teo.setdefault("payback", m.group(1))
    return teo


def _collect_recommendations(grids, paras) -> list[str]:
    recs: list[str] = []
    for p in paras:
        t = _norm(p)
        if re.search(
            r"предлагается\s+замен|рекомендуется\s+замен|необходимо\s+(?:замен|капитальн)", t
        ):
            recs.append(re.sub(r"\s+", " ", p.strip())[:300])
    # реестр рекомендаций (2026)
    for g in grids:
        head = " ".join(_norm(c) for c in (g[0] if g else []))
        if "рекомендаци" in head and "реестр" in head:
            for row in g[1:]:
                cells = [str(c).strip() for c in row if str(c).strip()]
                if len(cells) >= 2:
                    recs.append(" — ".join(cells[:2])[:300])
    # уникализировать, сохранить порядок
    seen, out = set(), []
    for r in recs:
        if r and r not in seen:
            seen.add(r)
            out.append(r)
    return out[:12]


_WATER_BY_PATH = {
    "пресная": WaterType.fresh,
    "агрессив": WaterType.aggressive,
    "пластов": WaterType.formation,
}


def _water_type(path: Path) -> WaterType:
    p = _norm(str(path))
    for key, wt in _WATER_BY_PATH.items():
        if key in p:
            return wt
    return WaterType.fresh


def _report_date(name: str) -> str:
    m = re.search(r"(\d{2})[.\-](\d{2})[.\-](\d{4})", name)
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)}" if m else ""


# ───────────────────────────── главный вход ─────────────────────────────


def parse_report(
    docx_path: Path,
    object_id: str,
    object_name: str,
    water_type: WaterType | None = None,
    source_original: str = "",
) -> ObjectReport:
    """Разобрать .docx-отчёт энергоаудита в ObjectReport (таблицы + утверждения прозы)."""
    docx_path = Path(docx_path)
    doc = Document(str(docx_path))
    blocks = list(_iter_blocks(doc))
    grids = [p for k, p in blocks if k == "tbl"]
    paras = [p for k, p in blocks if k == "p" and p.strip()]

    template = "2026" if any(_grid_has_dates(g) for g in grids) else "2024"
    pumps = _passport_pumps(grids)

    if template == "2026":
        agg_reports = _parse_2026(blocks)
        teo = _parse_teo_2026(grids, paras)
    else:
        n_agg = len(pumps) or 1
        refs, ranges = _parse_2024(grids, n_agg)
        agg_reports = [
            AggregateReport(
                id=f"НА-{i + 1}",
                pump_model=pumps[i] if i < len(pumps) else "",
                reference=refs[i],
                ranges=ranges[i],
            )
            for i in range(n_agg)
        ]
        teo = _parse_teo_2024(grids)

    # проставить модели насосов из паспорта по НОМЕРУ агрегата (НА-n → pumps[n-1])
    for ar in agg_reports:
        if ar.pump_model:
            continue
        m = re.match(r"на-(\d)", _norm(ar.id))
        idx = (int(m.group(1)) - 1) if m else -1
        if 0 <= idx < len(pumps):
            ar.pump_model = pumps[idx]

    # относительные утверждения из прозы (и из ячеек ТЭО-таблицы 2024)
    single = agg_reports[0].id if len(agg_reports) == 1 else None
    teo_cells: list[str] = []
    for g in grids:
        head = " ".join(_norm(c) for c in (g[0] if g else []))
        if "направление потерь" in head:
            for row in g[2:]:
                teo_cells.extend(str(c) for c in row if "сниж" in _norm(c))
    claims = _extract_claims(paras + teo_cells, single)
    for c in claims:
        claim_aggregate: AggregateReport | None = None
        for candidate in agg_reports:
            if candidate.id == c.aggregate_id:
                claim_aggregate = candidate
                break
        if claim_aggregate is None and single:
            claim_aggregate = agg_reports[0]
        if claim_aggregate is not None:
            claim_aggregate.claims.append(c)

    recommendations = _collect_recommendations(grids, paras)
    quotes = [c.text for c in claims]
    if teo.get("headline"):
        quotes.append(teo["headline"])
    quotes.extend(recommendations[:3])
    # уникализировать цитаты
    seen, uq = set(), []
    for q in quotes:
        if q and q not in seen:
            seen.add(q)
            uq.append(q)

    return ObjectReport(
        object_id=object_id,
        object_name=object_name,
        water_type=water_type or _water_type(docx_path),
        template=template,
        source=str(docx_path),
        source_original=source_original,
        report_date=_report_date(docx_path.name) or _report_date(source_original),
        aggregates=agg_reports,
        teo=teo,
        recommendations=recommendations,
        quotes=uq[:10],
    )
