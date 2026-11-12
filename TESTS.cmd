@echo off
rem PPD Energoaudit: double-click to run
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run.ps1" -Test
if errorlevel 1 pause
