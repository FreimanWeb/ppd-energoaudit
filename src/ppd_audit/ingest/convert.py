"""Конвертация бинарных «.doc» отчётов энергоаудита в «.docx» для парсинга.

Старые отчёты НТУ лежат в бинарном формате Word (.doc) — python-docx их не читает.
Конвертируем через LibreOffice (`soffice --headless --convert-to docx`), складывая
готовые копии в `data/reports/<id>.docx` (оригиналы в «НТУ цифровая платформа» не трогаем).

Резервные конвертеры (antiword/textract) не используются: они теряют структуру таблиц,
а отчёты насыщены табличными данными. Если LibreOffice недоступен — поднимаем понятную
ошибку с инструкцией (`brew install --cask libreoffice`).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


# Кандидаты на бинарь LibreOffice: PATH и штатные места установки (macOS/Linux).
_SOFFICE_CANDIDATES = [
    "soffice",
    "libreoffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    "/usr/bin/soffice",
    "/usr/local/bin/soffice",
    "/opt/homebrew/bin/soffice",
]


def find_soffice() -> str | None:
    """Путь к soffice или None."""
    for c in _SOFFICE_CANDIDATES:
        p = shutil.which(c) if "/" not in c else (c if Path(c).exists() else None)
        if p:
            return p
    return None


class ConversionError(RuntimeError):
    pass


def convert_doc_to_docx(src: Path, dst: Path) -> Path:
    """Сконвертировать .doc → .docx через LibreOffice. Возвращает путь dst."""
    soffice = find_soffice()
    if not soffice:
        raise ConversionError(
            "LibreOffice не найден — не могу конвертировать .doc. "
            "Установите: `brew install --cask libreoffice` (или укажите soffice в PATH)."
        )
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        env = os.environ.copy()
        env.setdefault("SAL_USE_VCLPLUGIN", "svp")  # headless-рендер без X11
        env.setdefault("HOME", tmp)  # изолированный профиль LO
        proc = subprocess.run(
            [soffice, "--headless", "--convert-to", "docx", "--outdir", tmp, str(src)],
            env=env,
            capture_output=True,
            text=True,
            timeout=180,
        )
        out = sorted(Path(tmp).glob("*.docx"))
        if not out:
            raise ConversionError(
                f"LibreOffice не создал .docx из {src.name}: {proc.stderr or proc.stdout}"
            )
        shutil.move(str(out[0]), str(dst))
    return dst


def ensure_report_docx(original: Path, dst: Path, *, force: bool = False) -> Path:
    """Гарантировать наличие готового к парсингу .docx по адресу dst.

    .docx-оригинал копируется как есть; .doc — конвертируется. Кэш в data/reports/
    переиспользуется (по mtime), если не задан force.
    """
    if dst.exists() and not force and dst.stat().st_mtime >= original.stat().st_mtime:
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    if original.suffix.lower() == ".docx":
        shutil.copyfile(original, dst)
        return dst
    if original.suffix.lower() == ".doc":
        return convert_doc_to_docx(original, dst)
    raise ConversionError(f"неподдерживаемый формат отчёта: {original.suffix} ({original.name})")
