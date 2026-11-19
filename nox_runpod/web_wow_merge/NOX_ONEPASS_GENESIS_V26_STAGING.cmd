@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem NOX ONE SOURCE STAGING: combines EXISTING WEB V25.1 + CHAT V25/V24 + ONEPASS V2
rem plus evidence UI. Never touches live server, model, S03, old chat, checkpoints.
set "ROOT=C:\NOX"
set "SRC=%ROOT%\incoming"
set "OUT=%ROOT%\builds"
set "MERGED=%OUT%\NOX_WEB_WOW_V25_PC_SOURCE_ONLY"
set "FINAL=%OUT%\NOX_WEB_WOW_V25_GENESIS_SOURCE_ONLY"
set "MERGER=%~dp0merge_physical_web_v25.py"
set "STAGER=%~dp0stage_genesis_web.py"
set "JS=%~dp0nox_genesis_live_panel.mjs"
where py >nul 2>nul
if errorlevel 1 (
 echo NOX_HOLD Python 3 launcher missing. Nothing changed.
 exit /b 2
)
if not exist "%MERGER%" (
 echo NOX_HOLD merge_physical_web_v25.py missing
 exit /b 2
)
if not exist "%STAGER%" (
 echo NOX_HOLD stage_genesis_web.py missing
 exit /b 2
)
if not exist "%JS%" (
 echo NOX_HOLD nox_genesis_live_panel.mjs missing
 exit /b 2
)
if exist "%MERGED%" (
 echo NOX_HOLD source staging already exists. No overwrite: %MERGED%
 exit /b 2
)
if exist "%FINAL%" (
 echo NOX_HOLD Genesis staging already exists. No overwrite: %FINAL%
 exit /b 2
)
for %%F in (
 "NOX_HELION_WEB_V25_1_CANDIDATE_20261112.zip"
 "NOX_CHAT_V25_SOURCES_PC_20261112.zip"
 "NOX_CHAT_V24_SOURCES_20261112.zip"
 "NOX_HELION_ONEPASS_V2_HARDENED_20261112.zip"
) do if not exist "%SRC%\%%~F" (
 echo NOX_HOLD missing original source: %SRC%\%%~F
 exit /b 2
)
if not exist "%OUT%" mkdir "%OUT%"
py -3 "%MERGER%" --web-v25 "%SRC%\NOX_HELION_WEB_V25_1_CANDIDATE_20261112.zip" --chat-v25 "%SRC%\NOX_CHAT_V25_SOURCES_PC_20261112.zip" --chat-v24 "%SRC%\NOX_CHAT_V24_SOURCES_20261112.zip" --onepass-v2 "%SRC%\NOX_HELION_ONEPASS_V2_HARDENED_20261112.zip" --output "%MERGED%"
if errorlevel 1 (
 echo NOX_HOLD original source merge failed, no production write.
 exit /b 2
)
py -3 "%STAGER%" --merged-web "%MERGED%\NOX_WEB_WOW_V25_PC_UNIFIED_SOURCE_CANDIDATE.zip" --module "%JS%" --out "%FINAL%"
if errorlevel 1 (
 echo NOX_HOLD Genesis web source integration failed. Source in %MERGED% preserved.
 exit /b 2
)
echo NOX_SOURCE_STAGING_PASS: %FINAL%\NOX_WEB_WOW_V25_GENESIS_S03_SOURCE_CANDIDATE.zip
echo NOX_LIVE_ONEHOST_E07_HOLD. No production change, no GPU training performed.
exit /b 0
