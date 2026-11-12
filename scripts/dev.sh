#!/usr/bin/env bash
# Локальный запуск и проверка проекта (Linux, macOS, Windows Git Bash).
#
#   scripts/dev.sh setup   — пакеты Python (uv workspace) и фронтенда (npm workspace)
#   scripts/dev.sh data    — собрать БД из файлов проекта (≈1 мин при первом запуске)
#   scripts/dev.sh start   — API (8000) + интерфейс (5173); Ctrl+C останавливает оба
#   scripts/dev.sh test    — Ruff, pytest, типы и тесты фронтенда, сборка
#   scripts/dev.sh all     — setup → data → test
#
# Нужны uv (https://docs.astral.sh/uv/) и Node.js 22.12+.
# Переменные: PPD_DATABASE_PATH (файл БД), PPD_APP_PASSWORD (пароль входа),
# API_PORT (8000), WEB_PORT (5173).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-5173}"

log() { printf '\n\033[1;32m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[1;31m%s\033[0m\n' "$*" >&2; exit 1; }

need() {
  command -v uv >/dev/null 2>&1 || fail "Нужен uv: https://docs.astral.sh/uv/getting-started/installation/"
  command -v node >/dev/null 2>&1 || fail "Нужен Node.js 22.12+ (https://nodejs.org)"
}

setup() {
  need
  log "Python: uv sync"
  uv sync --frozen --all-packages
  log "Фронтенд: npm ci"
  npm ci
}

data() {
  log "Сборка БД: паспорта, выгрузки ТИ/ТС, годовые выгрузки «Измерения»"
  uv run --frozen --package ppd-audit python -m ppd_audit.build_db "$@"
}

start() {
  log "API: http://127.0.0.1:${API_PORT}  ·  интерфейс: http://127.0.0.1:${WEB_PORT}"
  uv run --frozen --package ppd-audit uvicorn ppd_audit.api.main:app --host 127.0.0.1 --port "$API_PORT" &
  local api=$!
  trap 'kill $api 2>/dev/null || true' EXIT INT TERM
  for _ in $(seq 1 180); do
    if curl -fs "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then break; fi
    kill -0 "$api" 2>/dev/null || fail "API не запустился"
    sleep 1
  done
  VITE_API_PROXY_TARGET="http://127.0.0.1:${API_PORT}" \
    npm run dev --workspace @ppd/frontend -- --host 127.0.0.1 --port "$WEB_PORT" --strictPort --open
}

test_all() {
  log "Ruff"
  uv run --frozen ruff check apps scripts conftest.py
  uv run --frozen ruff format --check apps scripts conftest.py
  log "pytest"
  uv run --frozen --all-packages pytest -q -p no:warnings
  log "Фронтенд: типы, тесты, сборка"
  npm run typecheck
  npm run test:frontend
  npm run build
  log "Все проверки пройдены"
}

case "${1:-help}" in
  setup) setup ;;
  data) shift; data "$@" ;;
  start) start ;;
  test) test_all ;;
  all) setup; data; test_all ;;
  *) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//' ;;
esac
