"""Карточки нагнетательных скважин из выгрузки АРМИТС.

Выгрузка — архив с папкой на каждую КНС и файлом «inf_skw<номер>.xls» на
каждую скважину. Из карточки берутся:

- лист «Режим»: состояние скважины, текущая приёмистость, давление на устье
  до и после штуцера;
- лист «Динамика»: помесячная история — приёмистость, диаметр штуцера,
  давление на устье, на блок-гребёнке, пластовое и забойное, коэффициент
  приёмистости, объём закачки и время работы;
- лист «ГДИ»: плотность закачиваемого агента по исследованиям.

Давления в карточке — в атмосферах, расходы — в м³/сут, объём — в м³/мес.
"""

from __future__ import annotations

import calendar
import re
import zipfile
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from .pipelines import well_from_file_code


_FILE = re.compile(r"inf_skw(.+)\.xls$", re.IGNORECASE)
_MONTH = re.compile(r"^(\d{2})\.(\d{4})$")

# Колонки листа «Динамика» (строки данных начинаются после трёх строк шапки).
_DYN = {
    "q": 1,
    "choke": 4,
    "p_head": 5,
    "p_bg": 6,
    "p_res": 7,
    "p_bottom": 8,
    "injectivity": 9,
    "volume": 11,
    "hours_work": 12,
    "hours_idle": 13,
}


def _number(value: object) -> float | None:
    if value in (None, ""):
        return None
    match = re.search(r"-?\d+(?:[.,]\d+)?", str(value))
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


@dataclass(frozen=True)
class MonthRecord:
    """Строка помесячной истории скважины."""

    month: date
    q_m3_day: float | None
    choke_mm: float | None
    p_head_atm: float | None
    p_bg_atm: float | None
    p_reservoir_atm: float | None
    p_bottom_atm: float | None
    injectivity: float | None
    volume_m3: float | None
    hours_work: float | None
    hours_idle: float | None

    @property
    def calendar_hours(self) -> float:
        return 24.0 * calendar.monthrange(self.month.year, self.month.month)[1]

    @property
    def rate_m3h(self) -> float | None:
        """Средний расход в часы работы: объём за месяц / время работы."""
        if not self.volume_m3 or not self.hours_work:
            return None
        return self.volume_m3 / self.hours_work

    @property
    def mean_rate_m3h(self) -> float | None:
        """Среднекалендарный расход: объём за месяц / часы месяца.

        Для расчёта трения в общих водоводах берётся именно он: скважины,
        работающие циклически, не качают одновременно весь месяц.
        """
        if not self.volume_m3:
            return None
        return self.volume_m3 / self.calendar_hours


@dataclass
class WellCard:
    """Карточка нагнетательной скважины."""

    well: str
    state: str
    q_m3_day: float | None
    p_before_choke_atm: float | None
    p_after_choke_atm: float | None
    agent_density: float | None
    current: MonthRecord | None
    months: list[MonthRecord] = field(default_factory=list)

    @property
    def operating(self) -> bool:
        return self.state.lower().startswith("действ")

    @property
    def last_month(self) -> MonthRecord | None:
        return self.months[-1] if self.months else None

    def annual_volume_m3(self, months: int = 12) -> float:
        """Объём закачки за последние полные месяцы, м³."""
        return sum(record.volume_m3 or 0.0 for record in self.months[-months:])

    def annual_hours(self, months: int = 12) -> float:
        """Время работы за последние полные месяцы, ч."""
        return sum(record.hours_work or 0.0 for record in self.months[-months:])


def _month(value: object) -> date | None:
    match = _MONTH.match(str(value).strip())
    if not match:
        return None
    return date(int(match.group(2)), int(match.group(1)), 1)


def _cell(sheet, row: int, column: int) -> object:
    if row >= sheet.nrows or column >= sheet.ncols:
        return ""
    return sheet.cell_value(row, column)


def parse_card(content: bytes, file_code: str) -> WellCard:
    """Разобрать один файл карточки скважины (формат .xls)."""
    import xlrd

    book = xlrd.open_workbook(file_contents=content)
    regime = book.sheet_by_name("Режим")
    dynamics = book.sheet_by_name("Динамика")

    rows: list[MonthRecord] = []
    for row in range(3, dynamics.nrows):
        month = _month(_cell(dynamics, row, 0))
        if month is None:
            continue
        value = {key: _number(_cell(dynamics, row, column)) for key, column in _DYN.items()}
        rows.append(
            MonthRecord(
                month=month,
                q_m3_day=value["q"],
                choke_mm=value["choke"],
                p_head_atm=value["p_head"],
                p_bg_atm=value["p_bg"],
                p_reservoir_atm=value["p_res"],
                p_bottom_atm=value["p_bottom"],
                injectivity=value["injectivity"],
                volume_m3=value["volume"],
                hours_work=value["hours_work"],
                hours_idle=value["hours_idle"],
            )
        )
    # Первая строка — текущий неполный месяц, далее история. В истории иногда
    # повторно встречается текущий месяц; полными считаются только месяцы до него.
    current = rows[0] if rows else None
    history = sorted(
        (record for record in rows[1:] if current is None or record.month < current.month),
        key=lambda record: record.month,
    )

    density = None
    if "ГДИ" in book.sheet_names():
        survey = book.sheet_by_name("ГДИ")
        for row in range(survey.nrows - 1, 3, -1):
            candidate = _number(_cell(survey, row, 9))
            if candidate:
                density = candidate * 1000.0  # г/см³ → кг/м³
                break

    return WellCard(
        well=well_from_file_code(file_code),
        state=str(_cell(regime, 4, 1)).strip(),
        q_m3_day=_number(_cell(regime, 8, 1)),
        p_before_choke_atm=_number(_cell(regime, 8, 4)) or None,
        p_after_choke_atm=_number(_cell(regime, 8, 6)) or None,
        agent_density=density,
        current=current,
        months=history,
    )


def _decoded(info: zipfile.ZipInfo) -> str:
    """Имя файла в архиве: без флага UTF-8 Windows-архиватор пишет cp866."""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp866")
    except UnicodeError:
        return info.filename


def read_cards(archive: Path, folder: str) -> list[WellCard]:
    """Карточки скважин одной КНС из архива выгрузки.

    ``folder`` — имя папки станции в архиве или его начало («54», «ОПУ»).
    """
    cards: list[WellCard] = []
    with zipfile.ZipFile(archive) as bundle:
        for info in bundle.infolist():
            if info.is_dir():
                continue
            parts = _decoded(info).replace("\\", "/").split("/")
            if len(parts) < 2 or not parts[-2].startswith(folder):
                continue
            match = _FILE.search(parts[-1])
            if not match:
                continue
            cards.append(parse_card(bundle.read(info), match.group(1)))
    return sorted(cards, key=lambda card: card.well)
