@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0NOX_V134_REASSEMBLE_ONEPASS.ps1"
if errorlevel 1 (
  echo NOX V134: HOLD. See message above. No source files were deleted.
) else (
  echo NOX V134 full WEB source SHA-256 verified. Do not overwrite production without approval.
)
pause
endlocal
