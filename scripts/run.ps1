# Запуск проекта «одной кнопкой» (Windows). Вызывается из START.cmd.
#
# 1. Проверяет Node.js и uv; uv ставит сам, Node.js — через winget, если он есть.
# 2. Ставит пакеты Python и фронтенда (только при первом запуске или обновлении).
# 3. Собирает БД из файлов проекта (при первом запуске около минуты).
# 4. Запускает API в отдельном окне и интерфейс в этом окне, открывает браузер.
# Закрытие этого окна (или Ctrl+C) останавливает и интерфейс, и API.
param([switch]$Test)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$ApiPort = if ($env:API_PORT) { $env:API_PORT } else { "8000" }
$WebPort = if ($env:WEB_PORT) { $env:WEB_PORT } else { "5173" }

function Step($Text) { Write-Host "`n==> $Text" -ForegroundColor Green }
function Stop-WithMessage($Text) {
    Write-Host "`n$Text" -ForegroundColor Red
    Read-Host "Нажмите Enter, чтобы закрыть окно"
    exit 1
}
function Check($What) { if ($LASTEXITCODE -ne 0) { Stop-WithMessage "Ошибка на шаге: $What (код $LASTEXITCODE)" } }
function Refresh-Path {
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
        [Environment]::GetEnvironmentVariable("Path", "User") + ";" + (Join-Path $HOME ".local\bin")
}
function Has($Name) { [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

Refresh-Path

Step "Проверка Node.js"
$NodeOk = $false
if (Has node) {
    $Version = (& node -v).TrimStart("v").Split(".")
    $NodeOk = ([int]$Version[0] -gt 22) -or ([int]$Version[0] -eq 22 -and [int]$Version[1] -ge 12)
}
if (-not $NodeOk) {
    if (Has winget) {
        Write-Host "Node.js 22.12+ не найден — устанавливаю через winget…"
        & winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements
        Refresh-Path
    }
    if (-not (Has node)) {
        Stop-WithMessage "Установите Node.js LTS с https://nodejs.org и запустите START.cmd снова."
    }
}
Write-Host "Node.js $(& node -v)"

Step "Проверка uv (менеджер Python)"
if (-not (Has uv)) {
    Write-Host "uv не найден — устанавливаю…"
    & powershell -NoProfile -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    Refresh-Path
    if (-not (Has uv)) { Stop-WithMessage "Не удалось установить uv. Установите вручную: https://docs.astral.sh/uv/" }
}
Write-Host (& uv --version)

Step "Пакеты Python"
& uv sync --frozen --all-packages
Check "uv sync"

Step "Пакеты фронтенда"
$Marker = Join-Path (Join-Path $Root "node_modules") ".package-lock.json"
$Lock = Join-Path $Root "package-lock.json"
$NeedInstall = $true
if (Test-Path -LiteralPath $Marker) {
    $NeedInstall = (Get-Item -LiteralPath $Lock -Force).LastWriteTime -gt (Get-Item -LiteralPath $Marker -Force).LastWriteTime
    if (-not $NeedInstall) {
        # Установка могла оборваться (например, кончилось место на диске).
        & npm ls --workspaces --include-workspace-root --depth=0 *> $null
        $NeedInstall = $LASTEXITCODE -ne 0
    }
}
if ($NeedInstall) {
    & npm ci
    Check "npm ci"
} else {
    Write-Host "Уже установлены."
}

Step "База данных (первый запуск — около минуты)"
& uv run --frozen --package ppd-audit python -m ppd_audit.build_db
Check "сборка БД"

if ($Test) {
    Step "Ruff"
    & uv run --frozen ruff check apps scripts conftest.py
    Check "ruff check"
    & uv run --frozen ruff format --check apps scripts conftest.py
    Check "ruff format"
    Step "Автотесты Python"
    & uv run --frozen --all-packages pytest -q -p no:warnings
    Check "pytest"
    Step "Фронтенд: типы, тесты, сборка"
    & npm run typecheck; Check "typecheck"
    & npm run test:frontend; Check "тесты фронтенда"
    & npm run build; Check "сборка фронтенда"
    Write-Host "`nВсе проверки пройдены." -ForegroundColor Green
    Read-Host "Нажмите Enter, чтобы закрыть окно"
    exit 0
}

Step "Запуск API на порту $ApiPort"
$Api = Start-Process uv -ArgumentList "run --frozen --package ppd-audit uvicorn ppd_audit.api.main:app --host 127.0.0.1 --port $ApiPort" `
    -WorkingDirectory $Root -PassThru -WindowStyle Minimized
try {
    $Ready = $false
    for ($i = 0; $i -lt 180; $i++) {
        if ($Api.HasExited) { break }
        try { Invoke-WebRequest "http://127.0.0.1:$ApiPort/health" -UseBasicParsing -TimeoutSec 2 | Out-Null; $Ready = $true; break }
        catch { Start-Sleep -Seconds 1 }
    }
    if (-not $Ready) { Stop-WithMessage "API не запустился. Возможно, порт $ApiPort занят другой программой." }

    Step "Интерфейс: http://127.0.0.1:$WebPort (браузер откроется сам). Остановка — закрыть окно или Ctrl+C"
    $env:VITE_API_PROXY_TARGET = "http://127.0.0.1:$ApiPort"
    & npm run dev --workspace @ppd/frontend -- --host 127.0.0.1 --port $WebPort --strictPort --open
} finally {
    if ($Api -and -not $Api.HasExited) {
        & taskkill /PID $Api.Id /T /F | Out-Null
    }
}
