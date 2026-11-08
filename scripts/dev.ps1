# Локальный запуск и проверка проекта в Windows PowerShell.
#
#   .\scripts\dev.ps1 setup   — пакеты Python (uv workspace) и фронтенда (npm workspace)
#   .\scripts\dev.ps1 data    — собрать БД из файлов проекта (≈1 мин при первом запуске)
#   .\scripts\dev.ps1 start   — API (8000) + интерфейс (5173); закройте окно API, чтобы остановить
#   .\scripts\dev.ps1 test    — Ruff, pytest, типы и тесты фронтенда, сборка
#   .\scripts\dev.ps1 all     — setup, data, test
#
# Нужны uv и Node.js 22.12+. Если PowerShell запрещает скрипты:
#   powershell -ExecutionPolicy Bypass -File .\scripts\dev.ps1 start
param([string]$Command = "help")
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$ApiPort = if ($env:API_PORT) { $env:API_PORT } else { "8000" }
$WebPort = if ($env:WEB_PORT) { $env:WEB_PORT } else { "5173" }

function Log($Text) { Write-Host "`n==> $Text" -ForegroundColor Green }
function Check() { if ($LASTEXITCODE -ne 0) { throw "Команда завершилась с ошибкой ($LASTEXITCODE)" } }
function Need() {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw "Нужен uv: https://docs.astral.sh/uv/" }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) { throw "Нужен Node.js 22.12+ (https://nodejs.org)" }
}

function Invoke-Setup {
    Need
    Log "Python: uv sync"; & uv sync --frozen --all-packages; Check
    Log "Фронтенд: npm ci"; & npm ci; Check
}

function Invoke-Data {
    Log "Сборка БД"
    & uv run --frozen --package ppd-audit python -m ppd_audit.build_db; Check
}

function Invoke-Start {
    Log "API: http://127.0.0.1:$ApiPort  ·  интерфейс: http://127.0.0.1:$WebPort"
    $Api = Start-Process uv -ArgumentList "run --frozen --package ppd-audit uvicorn ppd_audit.api.main:app --host 127.0.0.1 --port $ApiPort" -PassThru
    try {
        for ($i = 0; $i -lt 180; $i++) {
            try { Invoke-WebRequest "http://127.0.0.1:$ApiPort/health" -UseBasicParsing | Out-Null; break } catch { Start-Sleep 1 }
        }
        $env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$ApiPort"
        & npm run dev --workspace @ppd/frontend -- --host 127.0.0.1 --port $WebPort --strictPort --open
    } finally {
        if (-not $Api.HasExited) { & taskkill /PID $Api.Id /T /F | Out-Null }
    }
}

function Invoke-Test {
    Log "Ruff"
    & uv run --frozen ruff check apps scripts conftest.py; Check
    & uv run --frozen ruff format --check apps scripts conftest.py; Check
    Log "pytest"; & uv run --frozen --all-packages pytest -q -p no:warnings; Check
    Log "Фронтенд: типы, тесты, сборка"
    & npm run typecheck; Check
    & npm run test:frontend; Check
    & npm run build; Check
    Log "Все проверки пройдены"
}

switch ($Command) {
    "setup" { Invoke-Setup }
    "data" { Invoke-Data }
    "start" { Invoke-Start }
    "test" { Invoke-Test }
    "all" { Invoke-Setup; Invoke-Data; Invoke-Test }
    default { Get-Content $PSCommandPath -TotalCount 10 | ForEach-Object { $_ -replace '^# ?', '' } }
}
