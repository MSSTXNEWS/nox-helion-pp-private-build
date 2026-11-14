@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0windows_offsite_receiver.ps1"
if errorlevel 1 (
 echo NOX V69: HOLD - check local Google Drive Desktop or configured rclone.
) else (
 echo NOX V69: ENCRYPTED ZIP COPIES VERIFIED BY SHA. Owner decryption still requires private key.
)
pause
endlocal
