"""Подготовка кэша текстовых отчётов перед тестами.

Кэш data/reports/<id>.docx генерируется из манифеста (бинарные .doc → LibreOffice).
Сам кэш в git не хранится (крупные .docx с картинками) — здесь он пересобирается.
Если нет ни кэша, ни конвертера/исходников — тесты отчётов пропускаются.
"""

import pytest
import yaml

from ppd_audit.config import project_root
from ppd_audit.ingest.convert import ConversionError, ensure_report_docx, find_soffice


@pytest.fixture(scope="session", autouse=True)
def _ensure_report_cache():
    root = project_root()
    man = yaml.safe_load((root / "config" / "verification.yaml").read_text(encoding="utf-8"))
    base = root / man["base_dir"]
    out = root / "data" / "reports"
    for obj in man["objects"]:
        if "report" not in obj:
            continue
        dst = out / f"{obj['id']}.docx"
        if dst.exists():
            continue
        src = base / obj["report"]
        if not src.exists():
            pytest.skip(f"нет исходного отчёта {src} (нужна папка «НТУ цифровая платформа»)")
        if src.suffix.lower() == ".doc" and not find_soffice():
            pytest.skip("нет LibreOffice (soffice) для конвертации .doc — см. README")
        try:
            ensure_report_docx(src, dst)
        except ConversionError as e:
            pytest.skip(str(e))
