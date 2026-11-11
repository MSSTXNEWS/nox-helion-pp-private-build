@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (py -3 -m engine.cli megablock1 --count 3 --seed 11 --output "output\v5_megablock1.json") else (python -m engine.cli megablock1 --count 3 --seed 11 --output "output\v5_megablock1.json")
if errorlevel 1 (
  echo [NOX OIE] MEGABLOCK 1 failed or output already exists. No files overwritten.
  exit /b 1
)
where py >nul 2>&1
if not errorlevel 1 (py -3 -m engine.cli megablock1-verify "output\v5_megablock1.json") else (python -m engine.cli megablock1-verify "output\v5_megablock1.json")
exit /b %errorlevel%
