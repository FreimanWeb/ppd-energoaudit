#!/usr/bin/env bash
# Запуск проекта одной командой (Linux, macOS, Windows Git Bash): ./run.sh
# Тесты: ./run.sh test
set -euo pipefail
cd "$(dirname "$0")"
bash scripts/dev.sh setup
bash scripts/dev.sh data
if [ "${1:-}" = "test" ]; then bash scripts/dev.sh test; else bash scripts/dev.sh start; fi
