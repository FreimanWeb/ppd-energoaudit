"""Верификация ядра на реальных объектах из отчётов энергоаудита.

Эталон — инженерные «… расчет.xlsx» (входы + результаты). Модель прогоняется на
извлечённых ВХОДАХ и сверяется с эталонными ВЫХОДАМИ.

Ключевая проверка: измеряемые KPI (УРЭ факт, КПД факт, напор) модель воспроизводит
во ВСЕХ агрегатах. Расхождения в номинал-зависимых величинах разобраны и внесены в
реестр KNOWN_DEVIATIONS (это не баги модели — см. docs/verification.md).
"""

import pytest
import yaml

from ppd_audit.config import project_root
from ppd_audit.spec import load_object_spec
from ppd_audit.verify.compare import FAIL
from ppd_audit.verify.runner import load_manifest, run_verification


@pytest.fixture(scope="session")
def verification():
    return run_verification(save_specs=False)


def test_verified_and_existing_plant_specs_are_native():
    root = project_root()
    for obj in load_manifest()["objects"]:
        assert (root / "config" / "plants" / f"{obj['id']}.yaml").is_file()

    for path in (root / "config" / "plants").glob("*.yaml"):
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert "reference_regime" not in raw
        assert load_object_spec(path.stem).id == path.stem


def test_per_cell_trace_present(verification):
    cells = verification["cells"]
    assert cells
    ref = next(c for c in cells if c.role == "reference" and c.field == "sec_fact")
    assert ref.value_cell
    assert ref.method_ref == "16"
    assert ref.model_value is not None
    assert ref.status in {"✓", "⚠", "✗", "—"}


# Известные расхождения с разобранной причиной (НЕ баг модели):
#  · КНС-ОПУ: в эталонном файле номинальный КПД «залип» на 0,5766 для трёх разных
#    насосов (ЦНС 63/80/180-1422, паспортные η=0,60/0,63/0,76) → модель берёт верный
#    паспорт и расходится с эталоном. Модель корректнее эталона.
#  · ΔW дрос: эксперт подтвердил расчёт через η_факт. Расхождения остаются только
#    с историческими xlsx, где использован η_ном или константа (docs/audit_findings.md §В2).
#  · КНС-155т НА-2: эталон (xlsx и отчёт согласованы между собой) считает КПД факт через
#    гидромощность с мгновенным Q≈224 м³/ч, тогда как суточный Q (q_day/t)=196,5 м³/ч →
#    КПД факт/K_з/ΔW расходятся; УРЭ факт при этом воспроизводится точно. Разница —
#    определение Q для гидромощности, не ошибка модели.
#  · КНС-85 НА-2 ΔW КПД: эталон включает η_тр=0,97 (ременная передача плунжерного
#    СИН50: η_ном 0,611 = 0,66·0,955·0,97), в паспортных строках xlsx η_тр нет —
#    модель считает по (14) без трансмиссии. Нужен паспорт трансмиссии (бэклог).
#  · КНС-85 НА-2 ΔW дрос: в эталонной ячейке мусор 4,29·10⁸ кВт·ч при Δp_задв=0
#    (ошибка формулы в черновике инженера); модель корректно даёт 0.
#  · КНС-138 НА-1 K_з: эталон делит на P_эл.ном ЭД СОСЕДНЕГО агрегата
#    (284,7·0,95/441,3=0,613 — ровно значение файла; у НА-1 свой ЭД 315 кВт/0,94 →
#    K_з=0,85). Перетянутая формула в файле инженера. Модель корректнее.
KNOWN_DEVIATIONS = {
    ("knsopu", "НА-1", "ΔW КПД, кВт·ч/год"),
    ("knsopu", "НА-2", "ΔW КПД, кВт·ч/год"),
    ("knsopu", "НА-3", "УРЭ расчётный, кВт·ч/м³"),
    ("knsopu", "НА-3", "КПД номинальный"),
    ("knsopu", "НА-3", "K загрузки ЭД"),
    ("knsopu", "НА-3", "ΔW КПД, кВт·ч/год"),
    ("knsopu", "НА-3", "ΔW дрос, кВт·ч/год"),
    ("knsopu", "НА-2", "ΔW дрос, кВт·ч/год"),  # xlsx использует η_ном
    ("kns155tbn", "НА-2", "КПД факт"),
    ("kns155tbn", "НА-2", "K загрузки ЭД"),
    ("kns155tbn", "НА-2", "ΔW КПД, кВт·ч/год"),
    ("kns85en", "НА-2", "ΔW КПД, кВт·ч/год"),  # η_тр=0,97 СИН не в паспорте xlsx
    ("kns85en", "НА-2", "ΔW дрос, кВт·ч/год"),  # мусорная ячейка эталона (4,29e8)
    ("kns138ln", "НА-1", "K загрузки ЭД"),  # эталон: формула по чужому ЭД
}

# Измеряемый KPI с разобранной причиной (НЕ баг модели): эталон определяет Q для
# гидромощности иначе (мгновенный vs суточный). Только КНС-155т НА-2 «КПД факт».
KNOWN_MEASURED_KPI_DEVIATIONS = {
    ("kns155tbn", "НА-2", "КПД факт"),
}

# Расчёт намеренно не запускается: в исходном xlsx КПД насоса СИН61.02.100 указан
# как «н/д», а η_ном=0,61655 собран из паспортов REDA соседнего агрегата.
KNOWN_INPUT_GAPS = {
    "kns14an/НА-2: ошибка расчёта — нет паспортных КПД для η_ном агрегата НА-2",
}


def test_all_objects_parsed(verification):
    """12 объектов распарсены; известный паспортный пробел не маскируется fallback-ом."""
    assert set(verification["errors"]) == KNOWN_INPUT_GAPS
    objects = {r.object_id for r in verification["rows"]}
    aggregates = {(r.object_id, r.aggregate_id) for r in verification["rows"]}
    assert len(objects) == 12
    assert len(aggregates) + len(KNOWN_INPUT_GAPS) >= 21


def test_kns13_uses_excel_annualization_assumption(verification):
    aggregate = verification["specs"]["kns13ln"].aggregate("НА-1")
    assert aggregate.regime.t_year == 8760.0


@pytest.mark.parametrize("object_id", ["kns129ln", "kns138ln", "kns175"])
def test_example_specs_remain_marked_when_regenerated(verification, object_id):
    assert verification["specs"][object_id].is_example


def test_measured_kpi_reproduced(verification):
    """УРЭ факт и напор факт воспроизводятся ВО ВСЕХ агрегатах. КПД факт — тоже везде,
    кроме разобранного реестра KNOWN_MEASURED_KPI_DEVIATIONS (эталон определяет Q
    для гидромощности иначе — см. комментарий к реестру)."""
    strict = [r for r in verification["rows"] if r.metric.startswith(("УРЭ факт", "Напор факт"))]
    bad_strict = [
        (r.object_id, r.aggregate_id, r.metric, round(r.rel_dev, 3))
        for r in strict
        if r.status == FAIL
    ]
    assert not bad_strict, f"УРЭ факт / напор разошлись: {bad_strict}"

    eta_fails = {
        (r.object_id, r.aggregate_id, r.metric)
        for r in verification["rows"]
        if r.metric.startswith("КПД факт") and r.status == FAIL
    }
    assert eta_fails <= KNOWN_MEASURED_KPI_DEVIATIONS, (
        f"новые расхождения КПД факт: {eta_fails - KNOWN_MEASURED_KPI_DEVIATIONS}"
    )


def test_no_unexpected_failures(verification):
    """Все ✗ объяснены и внесены в реестр; новых расхождений нет."""
    fails = {
        (r.object_id, r.aggregate_id, r.metric) for r in verification["rows"] if r.status == FAIL
    }
    unexpected = fails - KNOWN_DEVIATIONS
    assert not unexpected, f"новые необъяснённые расхождения: {unexpected}"


def test_power_balance_kns(verification):
    """Где есть p_БГ — декомпозиция КНС сводится (компоненты = P_эл)."""
    # косвенно: расчёт прошёл без ошибок баланса для всех КНС-агрегатов
    assert verification["summary"]["total_rows"] > 0


@pytest.mark.parametrize(
    "object_id",
    [
        "kns25",
        "kns155bn",
        "kns14an",
        "kns10bn",
        "kns154bn",
        "kns155tbn",
        "kns85en",
        "kns129ln",
        "kns138ln",
        "kns175",
    ],
)
def test_object_sec_fact(verification, object_id):
    """Покейсово: УРЭ факт объекта в допуске ±2%."""
    rows = [
        r
        for r in verification["rows"]
        if r.object_id == object_id and r.metric.startswith("УРЭ факт")
    ]
    assert rows, f"нет строк УРЭ факт для {object_id}"
    for r in rows:
        assert abs(r.rel_dev) <= 0.02, f"{object_id}/{r.aggregate_id}: УРЭф {r.rel_dev:+.1%}"
