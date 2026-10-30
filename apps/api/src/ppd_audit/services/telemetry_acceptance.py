"""Приёмка сырых измерений: без переноса состояний и подмены расчёта аудитом."""

from collections import Counter, defaultdict
from datetime import datetime
from itertools import pairwise
from math import isfinite


_UNITS = {
    "p_in": ("МПа",),
    "p_out": ("МПа",),
    "p_bg": ("МПа",),
    "power": ("кВт",),
    "flow_rate": ("м³/ч",),
    "density": ("кг/м³",),
    "q_day": ("м³/сут", "м³"),
    "energy": ("кВт·ч", "кВт·ч/сут"),
    "runtime": ("ч",),
}


def acceptance_report(rows: list[dict]) -> dict:
    """Полнота входов, а не разрешение инженерных/экономических выводов."""
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["metric"]].append(row)
    signals = []
    valid_rows = {}
    for metric in dict.fromkeys([*_UNITS, *grouped]):
        samples = grouped[metric]
        accepted = []
        issues: Counter[str] = Counter()
        for row in samples:
            value = row["value"]
            if row.get("is_station") and metric not in {"p_bg", "density"}:
                issues["Станционные данные не распределены на агрегат"] += 1
            elif row.get("quality") not in (None, "", "good", "ready"):
                issues[f"Качество не подтверждено: метка {row['quality']}"] += 1
            elif metric in _UNITS and row["unit"] not in _UNITS[metric]:
                issues[f"Ожидаемые единицы: {', '.join(_UNITS[metric])}"] += 1
            elif not isinstance(value, (int, float)) or not isfinite(value) or value < 0:
                issues["Отрицательное или неконечное значение"] += 1
            elif metric == "density" and value == 0:
                issues["Нулевая плотность"] += 1
            elif metric == "runtime" and value > 24:
                issues["Суточная наработка выше 24 ч"] += 1
            else:
                accepted.append(row)
        counts = Counter(row["timestamp"] for row in accepted)
        duplicates = {stamp for stamp, count in counts.items() if count > 1}
        if duplicates:
            issues["Неоднозначные записи на один момент"] = sum(counts[t] for t in duplicates)
            accepted = [row for row in accepted if row["timestamp"] not in duplicates]
        if metric in {"energy", "q_day", "runtime"}:
            days = Counter(row["timestamp"][:10] for row in accepted)
            if any(count > 1 for count in days.values()):
                issues["Несколько суточных итогов на одну дату"] = sum(
                    count for count in days.values() if count > 1
                )
        valid_rows[metric] = accepted
        times = sorted({row["timestamp"] for row in accepted})
        gaps = [
            (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds() / 3600
            for a, b in pairwise(times)
        ]
        signals.append({
            "metric": metric,
            "unit": ", ".join(sorted({row["unit"] for row in samples}))
            or _UNITS.get(metric, ("—",))[0],
            "records": len(samples),
            "valid": len(accepted),
            "first": times[0] if times else None,
            "last": times[-1] if times else None,
            "days": len({stamp[:10] for stamp in times}),
            "max_gap_hours": max(gaps) if gaps else None,
            "issues": [f"{message}: {count}" for message, count in issues.items()]
            if samples
            else ["Измерений за период нет"],
        })
    daily = {}
    for metric in ("energy", "q_day"):
        by_day = defaultdict(list)
        for row in valid_rows[metric]:
            by_day[row["timestamp"][:10]].append(row["value"])
        daily[metric] = {
            day
            for day, values in by_day.items()
            if len(values) == 1 and (metric != "q_day" or values[0] > 0)
        }
    common_days = daily["energy"] & daily["q_day"]
    required = ("p_in", "p_out", "power", "flow_rate", "density")
    common_times = set.intersection(
        *({r["timestamp"] for r in valid_rows[m] if r["value"] > 0} for m in required)
    )
    missing = [m for m in required if not valid_rows[m]]
    return {
        "signals": signals,
        "calculations": [
            {
                "name": "Суточный УРЭ W/Q",
                "status": "available" if common_days else "blocked",
                "reason": (
                    f"Однозначные W и положительный Q за одни сутки: {len(common_days)} дн. "
                    "Это полнота входов, не проверка достоверности."
                )
                if common_days
                else (
                    "Нужны суточные energy и положительный q_day одного агрегата за одни сутки, "
                    "по одной записи на показатель/сутки; станционные итоги не подходят."
                ),
            },
            {
                "name": "Синхронный набор для мгновенного режима",
                "status": "available" if common_times else "blocked",
                "reason": (
                    "Совпадающие моменты p_in, p_out, power, flow_rate, density: "
                    f"{len(common_times)}. Далее нужны паспорт и физические проверки."
                )
                if common_times
                else (
                    "Нет совместного положительного набора p_in/p_out/power/flow_rate/density "
                    "без переноса значений. "
                )
                + (
                    f"Отсутствуют пригодные сигналы: {', '.join(missing)}."
                    if missing
                    else "Сигналы есть, но времена не совпадают или значения нулевые."
                ),
            },
        ],
        "note": (
            "Проверяется полнота сырых входов выбранного периода, не исправность оборудования "
            "и не готовность экономики. Максимальный интервал — между пригодными записями; "
            "без заданной частоты он не доказывает пропуск. Давления-состояния здесь "
            "не переносятся из прошлого; расчёт режима умеет обрабатывать их отдельно."
        ),
    }
