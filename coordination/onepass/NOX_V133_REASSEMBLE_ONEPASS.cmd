@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0NOX_V133_REASSEMBLE_ONEPASS.ps1"
if errorlevel 1 (
  echo NOX V133: HOLD. See message above. No source files were deleted.
) else (
  echo NOX V133 full WEB source SHA-256 verified. Do not overwrite production without approval.
)
pause
endlocal
