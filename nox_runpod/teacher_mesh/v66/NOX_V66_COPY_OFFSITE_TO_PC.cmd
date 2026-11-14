@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows_offsite_receiver.ps1"
if errorlevel 1 (
 echo.
 echo NOX OFFSITE COPY ON PC: HOLD. Check signed-in Google Drive Desktop or rclone configuration.
) else (
 echo.
 echo NOX OFFSITE COPY ON PC: SHA-VERIFIED ENCRYPTED ZIP COPIES; owner-key restore not yet accepted.
)
pause
endlocal
