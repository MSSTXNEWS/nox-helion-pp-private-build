@echo off
setlocal
cd /d "%~dp0"
echo NOX HELION ONEPASS - proverka paketa i lokalnogo podklyucheniya (bez ustanovki)
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0NOX_ONEPASS_VERIFY_WINDOWS.ps1"
set RESULT=%ERRORLEVEL%
echo.
if not "%RESULT%"=="0" (echo HOLD: package or source mismatch. See receipt.) else (echo SOURCE PACKAGE VERIFIED. Native release acceptance is separate.)
pause
exit /b %RESULT%
