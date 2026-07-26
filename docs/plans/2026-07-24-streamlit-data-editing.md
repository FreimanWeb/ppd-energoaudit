# Streamlit Data Editing Implementation Plan

**Goal:** Разрешить через Streamlit создавать и изменять паспорт агрегата и отдельные точки телеметрии в SQLite.

**Architecture:** Новый экран использует текущие объект и агрегат из `Ctx`, а запись выполняется только через `AuditDatabase`. Паспорт сохраняется как версия с датой действия; телеметрическая точка идемпотентно заменяется по ключу «объект, агрегат, время, metric».

**Tech Stack:** Python, SQLite, Streamlit, pytest, Streamlit `AppTest`.

---

### Task 1: Запись паспорта через repository

**Files:**
- Modify: `src/ppd_audit/db.py`
- Test: `tests/test_database.py`

1. Написать failing test, что сохранение формы обновляет паспорт с заданной датой действия.
2. Запустить `uv run pytest tests/test_database.py::<test> -q` и увидеть failure.
3. Добавить минимальный метод repository поверх существующего `add_passport`.
4. Повторно запустить test.

### Task 2: Редактирование одной точки телеметрии

**Files:**
- Modify: `src/ppd_audit/db.py`
- Test: `tests/test_database.py`

1. Написать failing test: повторная запись той же точки изменяет значение, а не создаёт дубликат.
2. Запустить test и увидеть failure, если нужен отдельный API.
3. Использовать существующий canonical-unit validation и unique key для upsert.
4. Повторно запустить test.

### Task 3: Экран Streamlit

**Files:**
- Create: `app/tabs/data_edit.py`
- Modify: `app/main.py`, `app/lib.py`
- Test: `tests/test_app.py`

1. Написать failing `AppTest` на наличие режима «Редактирование данных» в sidebar.
2. Создать две формы: паспорт агрегата и одна точка телеметрии.
3. После сохранения очищать кеш и перезапускать экран, чтобы расчёт читал новую SQLite-запись.
4. Повторно запустить `AppTest`.

### Task 4: Проверка

1. Выполнить `uv run pytest tests/test_database.py tests/test_app.py -q`.
2. Выполнить `uv run ruff check` для изменённых файлов и `git diff --check`.
