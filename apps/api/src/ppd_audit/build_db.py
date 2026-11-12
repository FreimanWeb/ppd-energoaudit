"""Собрать БД приложения из файлов проекта.

Запуск: ``python -m ppd_audit.build_db`` (путь БД — ``PPD_DATABASE_PATH`` или
``telemetry.sqlite`` в корне проекта). Ключ ``--rebuild`` удаляет файл БД и
собирает его заново.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .config import project_root
from .db import default_database_path
from .services.catalog import prepare_database


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Сборка БД энергоаудита ППД")
    parser.add_argument("--path", type=Path, default=None, help="файл SQLite")
    parser.add_argument("--rebuild", action="store_true", help="пересобрать с нуля")
    args = parser.parse_args(argv)

    path = args.path or default_database_path()
    if args.rebuild and path.exists():
        path.unlink()
    started = time.monotonic()
    path, seed, scada = prepare_database(project_root(), path)
    print(f"БД: {path}")
    print(
        f"Выгрузки АСУ ТП: файлов {scada.files_found}, записано строк {scada.stored}"
        + (f" ({scada.reason})" if scada.reason else "")
    )
    if scada.unreadable:
        print("  не прочитаны: " + ", ".join(scada.unreadable))
    print(f"Примеры телеметрии: файлов {seed.files_found}, записано строк {seed.stored}")
    print(f"Готово за {time.monotonic() - started:.0f} с")
    return 0


if __name__ == "__main__":
    sys.exit(main())
