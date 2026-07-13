"""Сверка модели и парсера с ТЕКСТОВЫМИ отчётами энергоаудита (.doc/.docx).

Независимый «человеческий» эталон: те же объекты, описанные прозой и таблицами.
Проверяем:
  · парсер воспроизводит фикстуры tests/reports/<id>.json (регрессия извлечения);
  · якорные значения из отчётов (независимая «ручная» сверка) сходятся;
  · извлечены и абсолютные, и ОТНОСИТЕЛЬНЫЕ показатели (Δ УРЭ, КПД в п.п., напор);
  · модель воспроизводит относительные утверждения прозы (где источники согласованы);
  · плунжерный НА-1 КНС-25 идёт по ветке объёмного насоса;
  · расхождения источников (xlsx ↔ отчёт) — только из разобранного реестра.

Отчёты лежат разобранными в data/reports/<id>.docx (бинарные .doc сконвертированы
LibreOffice; конвертация не требуется на каждом прогоне). См. docs/verification.md.
"""

import json
from pathlib import Path

import pytest

from ppd_audit.core.audit import audit_aggregate
from ppd_audit.ingest.report_calc import parse_calc_file
from ppd_audit.ingest.report_doc import parse_report
from ppd_audit.verify.reconcile import FAIL, run_reconciliation


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "data" / "reports"
FIXTURES = Path(__file__).resolve().parent

OBJECTS = ["kns25", "kns155bn", "kns10bn", "kns154bn", "knsopu", "kns14an"]
NTU = ROOT / "data" / "raw" / "ntu"

# Расхождения источников (xlsx ≠ отчёт) с разобранной причиной — НЕ баг модели/парсера.
# OPU: отчёт многодатовый, xlsx — иной снимок, привязка ЦНС-63/80 различается, η_ном «залип».
# КНС-14: в xlsx тип/порядок агрегатов (REDA↔СИН) инвертирован относительно отчёта.
# КНС-10 НА-1: р_вых в «исходных данных» (8,92→703 м) ≠ «тех.параметрам» (949 м); xlsx — по 8,92.
KNOWN_SOURCE_DISAGREEMENTS = {
    ("kns14an", "НА-2", "ΔW КПД, кВт·ч/год"),
    ("knsopu", "НА-1", "ΔW КПД, кВт·ч/год"),
    ("knsopu", "НА-2", "УРЭ факт, кВт·ч/м³"),
    ("knsopu", "НА-2", "КПД факт"),
    ("knsopu", "НА-2", "ΔW КПД, кВт·ч/год"),
    ("kns10bn", "НА-1", "Напор факт, м"),
}
# Модель↔отчёт ✗ (производные от рассогласованной привязки агрегатов OPU/КНС-14).
# КНС-155т НА-2: xlsx и отчёт согласованы между собой (ист ✓), но оба считают КПД факт
# через мгновенный Q≈224 м³/ч, а модель — через суточный Q=196,5; УРЭ факт совпадает.
# КНС-85 НА-2 (СИН50, плунжер с ременной передачей): xlsx и отчёт включают η_тр=0,97
# в η_ном (0,611=0,66·0,955·0,97), но в паспортных строках η_тр не приводят → модель
# считает по (14) без трансмиссии (η_ном 0,630) → производные ΔW_кпд и «КПД снижен»
# расходятся. Причина разобрана в docs/audit_findings.md §В3; лечится паспортом η_тр.
KNOWN_MODEL_REPORT_FAILS = KNOWN_SOURCE_DISAGREEMENTS | {
    ("knsopu", "НА-2", "УРЭ расчётный, кВт·ч/м³"),
    ("knsopu", "НА-2", "КПД снижен, п.п."),
    ("knsopu", "НА-2", "УРЭ выше расч., кВт·ч/м³"),
    ("kns155tbn", "НА-2", "КПД факт"),
    ("kns155tbn", "НА-2", "K загрузки ЭД"),
    ("kns155tbn", "НА-2", "ΔW КПД, кВт·ч/год"),
    ("kns155tbn", "НА-2", "КПД снижен, п.п."),
    ("kns155tbn", "НА-2", "УРЭ выше расч., кВт·ч/м³"),
    ("kns85en", "НА-2", "ΔW КПД, кВт·ч/год"),
    ("kns85en", "НА-2", "КПД снижен, п.п."),
}


@pytest.fixture(scope="session")
def reports():
    return {oid: parse_report(REPORTS / f"{oid}.docx", oid, oid) for oid in OBJECTS}


@pytest.fixture(scope="session")
def reconciliation():
    return run_reconciliation()


def _approx(a, b, rel=0.02, abs_=1e-6):
    return abs(a - b) <= max(abs_, rel * abs(b))


# ───────────────────────── парсинг и фикстуры ─────────────────────────


def test_all_reports_parsed(reports):
    """≥4 объектов распарсены (вкл. конвертацию бинарных .doc), есть агрегаты."""
    assert len(reports) >= 4
    for oid, r in reports.items():
        assert r.aggregates, f"{oid}: нет агрегатов"
        assert r.template in ("2024", "2026")


@pytest.mark.parametrize("oid", OBJECTS)
def test_parser_matches_fixture(reports, oid):
    """Парсер воспроизводит фикстуру tests/reports/<id>.json (регрессия извлечения)."""
    fx = json.loads((FIXTURES / f"{oid}.json").read_text(encoding="utf-8"))
    r = reports[oid]
    assert r.template == fx["template"]
    for agg_id, exp in fx["aggregates"].items():
        ar = r.aggregate(agg_id)
        assert ar is not None, f"{oid}: нет {agg_id}"
        for field, ev in exp.items():
            if field in ("pump_model", "ranges", "claims"):
                continue
            got = getattr(ar.reference, field)
            assert got is not None and _approx(got, ev, rel=0.01), (
                f"{oid}/{agg_id}.{field}: {got} ≠ {ev}"
            )


def test_absolute_and_relative_extracted(reports):
    """Из отчётов извлечены И абсолютные, И относительные показатели."""
    has_abs = has_rel = False
    for r in reports.values():
        for a in r.aggregates:
            if a.reference.sec_fact is not None:
                has_abs = True
            if a.claims:
                has_rel = True
    assert has_abs and has_rel


# ───────────────────────── якорные значения (ручная сверка) ─────────────────────────


def test_anchor_kns25(reports):
    """КНС-25: УРЭ Н-1≈4,41; Н-2≈7,0; КПД снижен 2,59/3,04 п.п.; УРЭ выше 0,14/0,389; Н-2 −43 м (3%)."""
    r = reports["kns25"]
    h1, h2 = r.aggregate("НА-1"), r.aggregate("НА-2")
    assert _approx(h1.reference.sec_fact, 4.41)
    assert _approx(h2.reference.sec_fact, 7.0, rel=0.02)
    cl1 = {c.metric: c for c in h1.claims}
    cl2 = {c.metric: c for c in h2.claims}
    assert _approx(cl1["eta_reduction_pp"].value, 2.59, rel=0.02)
    assert _approx(cl1["sec_over_calc"].value, 0.14, rel=0.05)
    assert _approx(cl2["eta_reduction_pp"].value, 3.04, rel=0.02)
    assert _approx(cl2["sec_over_calc"].value, 0.389, rel=0.05)
    assert _approx(cl2["head_drop_m"].value, 43.0, rel=0.05)
    assert _approx(cl2["head_drop_pct"].value, 3.0, rel=0.1)


def test_anchor_kns155(reports):
    """КНС-155: КПД снижен 4,384 п.п.; УРЭ выше 0,379; рабочая точка ниже 54 м (4,78%)."""
    r = reports["kns155bn"]
    a = r.aggregate("НА-1")
    cl = {c.metric: c for c in a.claims}
    assert _approx(cl["eta_reduction_pp"].value, 4.384, rel=0.01)
    assert _approx(cl["sec_over_calc"].value, 0.379, rel=0.05)
    assert _approx(cl["head_drop_m"].value, 54.0, rel=0.02)
    assert _approx(cl["head_drop_pct"].value, 4.78, rel=0.02)


# ───────────────────────── модель ↔ отчёт ─────────────────────────


def test_model_reproduces_report_relative_exact(reports):
    """Чистые объекты (КНС-25, КНС-155): модель ТОЧНО воспроизводит относительные
    утверждения прозы (Δ УРЭ и КПД в п.п.)."""
    for oid, files in {
        "kns25": "Пресная вода/КНС 25 выезд 11.03.2024/кнс 25 расчет.xlsx",
        "kns155bn": "пластовая вода/15Кнс 155 БН 28.03.24/кнс-155 расчет.xlsx",
    }.items():
        spec = parse_calc_file(NTU / files, oid, oid)
        rep = reports[oid]
        for agg in spec.working_aggregates():
            res = audit_aggregate(agg, spec.branch)
            claims = {c.metric: c for c in (rep.aggregate(agg.id) or rep.aggregates[0]).claims}
            if "eta_reduction_pp" in claims:
                model_pp = (res.regime.eta_nom - res.regime.eta_unit) * 100
                assert _approx(model_pp, claims["eta_reduction_pp"].value, rel=0.03, abs_=0.1)
            if "sec_over_calc" in claims:
                model_d = res.sec_fact - res.sec_calc
                assert _approx(model_d, claims["sec_over_calc"].value, rel=0.05, abs_=0.02)


def test_model_reproduces_report_relative_not_fail(reconciliation):
    """Для 2024-объектов относительные показатели модель↔отчёт не уходят в ✗
    (мелкие WARN допустимы — округление η_ном в отчёте)."""
    for r in reconciliation["rows"]:
        if r.kind == "отн" and r.object_id in ("kns25", "kns155bn", "kns10bn", "kns154bn"):
            assert r.st_model_report != FAIL, f"{r.object_id}/{r.aggregate_id} {r.metric}"


def test_plunger_branch_kns25(reports):
    """Плунжерный НА-1 КНС-25 (СТ-А): отчёт и модель — ветка объёмного насоса."""
    rep = reports["kns25"]
    assert "ст-а" in rep.aggregate("НА-1").pump_model.lower()
    spec = parse_calc_file(
        NTU / "Пресная вода/КНС 25 выезд 11.03.2024/кнс 25 расчет.xlsx", "kns25", "КНС-25"
    )
    res = audit_aggregate(spec.aggregate("НА-1"), spec.branch)
    assert res.pump_kind == "объёмный"
    assert res.h_due is None  # для объёмного кривая Q-H неприменима


# ───────────────────────── трёхсторонняя сверка ─────────────────────────


def test_reconciliation_runs(reconciliation):
    """Трёхсторонняя сверка проходит без ошибок и даёт строки по ≥4 объектам."""
    assert not reconciliation["errors"], reconciliation["errors"]
    assert reconciliation["summary"]["total_rows"] > 0
    objs = {r.object_id for r in reconciliation["rows"]}
    assert len(objs) >= 4


def test_no_unexpected_source_disagreements(reconciliation):
    """Все расхождения источников (xlsx ≠ отчёт) разобраны и внесены в реестр."""
    fails = {
        (r.object_id, r.aggregate_id, r.metric)
        for r in reconciliation["rows"]
        if r.st_sources == FAIL
    }
    assert fails <= KNOWN_SOURCE_DISAGREEMENTS, (
        f"новые необъяснённые расхождения источников: {fails - KNOWN_SOURCE_DISAGREEMENTS}"
    )


def test_no_unexpected_model_report_fails(reconciliation):
    """Все ✗ «модель↔отчёт» объяснены (рассогласование привязки агрегатов OPU/КНС-14)."""
    fails = {
        (r.object_id, r.aggregate_id, r.metric)
        for r in reconciliation["rows"]
        if r.st_model_report == FAIL
    }
    assert fails <= KNOWN_MODEL_REPORT_FAILS, (
        f"новые ✗ модель↔отчёт: {fails - KNOWN_MODEL_REPORT_FAILS}"
    )


def test_clean_objects_model_report_agree(reconciliation):
    """Для согласованных объектов измеряемые KPI модель↔отчёт совпадают."""
    for r in reconciliation["rows"]:
        if r.object_id in ("kns25", "kns155bn") and r.metric in ("УРЭ факт, кВт·ч/м³", "КПД факт"):
            assert r.st_model_report in ("✓", "—"), (
                f"{r.object_id}/{r.aggregate_id} {r.metric}: {r.st_model_report}"
            )
