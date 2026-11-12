@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if exist "%~dp0NOX_STOP" (
  echo NOX_STOP exists. Remove it ONLY when you want to start a new QA session.
  exit /b 130
)
where node >nul 2>nul
if errorlevel 1 (
  echo BLOCKED: Node.js 22+ required; install official Node.js and rerun.
  exit /b 20
)
:run
node "%~dp0NOX_ONEPASS.mjs"
set code=%ERRORLEVEL%
if "%code%"=="0" (
  echo Completed execution. See NOX_QA_RESULTS\FULL_ACCEPTANCE.json
  exit /b 0
)
if "%code%"=="20" (
  echo BLOCKED safely: no dangerous restart. See NOX_QA_RESULTS\fatal.json
  exit /b 20
)
if "%code%"=="130" exit /b 130
if exist "%~dp0NOX_STOP" exit /b 130
echo QA runner exited with %code%, restarting ONLY QA after 30 sec, retaining state.
timeout /t 30 /nobreak >nul
goto run