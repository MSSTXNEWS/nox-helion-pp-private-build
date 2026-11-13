@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem NOX HELION V29.2: offline rebuild from exact V28 original. No live writes.
set "ROOT=C:\NOX"
set "INPUT=%ROOT%\incoming\NOX_HELION_WEB_V28_V27_PC_GENESIS_UNIFIED_SOURCE_20261113.zip"
set "OUTPUT=%ROOT%\incoming\NOX_HELION_WEB_V29_2_REAL_PC_API_ROUTES_20261113.zip"
if not exist "%INPUT%" (
  echo NOX_V29_2_HOLD_MISSING_V28: %INPUT%
  exit /b 2
)
if exist "%OUTPUT%" (
  echo NOX_V29_2_HOLD_OUTPUT_EXISTS_NO_OVERWRITE: %OUTPUT%
  exit /b 2
)
where py >nul 2>nul
if errorlevel 1 (
  echo NOX_V29_2_HOLD_PYTHON3_LAUNCHER_MISSING
  exit /b 2
)
set "NOX_MERGE_DIR=%ROOT%\incoming"
set "NOX_V29_OUTPUT_ZIP=%OUTPUT%"
py -3 "%~dp0build_v29_from_v28.py"
if errorlevel 1 (
  echo NOX_V29_2_HOLD_REBUILD_FAILED_NO_PRODUCTION_WRITE
  exit /b 2
)
py -3 "%~dp0verify_rebuilt_v29.py" "%OUTPUT%"
if errorlevel 1 (
  echo NOX_V29_2_HOLD_VERIFY_FAILED_INSPECT_OUTPUT_DO_NOT_DEPLOY
  exit /b 2
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0NOX_V29_2_WINDOWS_STAGE.ps1" -Archive "%OUTPUT%" -Root "%ROOT%"
if errorlevel 1 (
  echo NOX_V29_2_SOURCE_VERIFIED_WINDOWS_STAGING_HOLD
  exit /b 2
)
echo NOX_V29_2_COMPLETE_STAGED_NO_PRODUCTION_CHANGE
echo NOX_LIVE_WINDOWS_WEBVIEW2_E07_VOICE_SAFE70_HOLD
exit /b 0
