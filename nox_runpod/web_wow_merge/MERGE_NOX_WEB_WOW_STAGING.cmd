@echo off
setlocal EnableExtensions
set "ROOT=C:\NOX"
set "SRC=%ROOT%\incoming"
set "OUT=%ROOT%\builds\NOX_WEB_WOW_V25_STAGING"
set "MERGER=%~dp0merge_nox_web_wow.py"
if not exist "%ROOT%\builds" mkdir "%ROOT%\builds"
where py >nul 2>nul
if errorlevel 1 (
  echo NOX_HOLD: Python launcher py.exe not installed; no files changed.
  exit /b 2
)
if exist "%OUT%" (
  echo NOX_HOLD: staging already exists, no overwrite: %OUT%
  exit /b 2
)
for %%F in (
  "NOX_HELION_WEB_V25_1_CANDIDATE_20261112.zip"
  "NOX_CHAT_V25_SOURCES_PC_20261112.zip"
  "NOX_CHAT_V24_SOURCES_20261112.zip"
) do if not exist "%SRC%\%%~F" (
  echo NOX_HOLD: missing %SRC%\%%~F
  exit /b 2
)
py -3 "%MERGER%" --web-v25 "%SRC%\NOX_HELION_WEB_V25_1_CANDIDATE_20261112.zip" --chat-v25 "%SRC%\NOX_CHAT_V25_SOURCES_PC_20261112.zip" --chat-v24 "%SRC%\NOX_CHAT_V24_SOURCES_20261112.zip" --output "%OUT%"
if errorlevel 1 (
  echo NOX_HOLD: inspect %OUT%\NOX_MERGE_RECEIPT.json
  exit /b 2
)
echo SOURCE_MERGED_PHYSICAL_QA_HOLD: %OUT%\site
echo Existing 127.0.0.1:8766, Ollama, C:\NOX\helion and production were not touched.
exit /b 0
