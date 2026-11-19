@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0NOX_V70_PC_ALL_ONEPASS.ps1"
if errorlevel 1 (
  echo.
  echo NOX V70 ONEPASS PC: HOLD. Check Google Drive Desktop/rclone or insufficient disk.
) else (
  echo.
  echo NOX V70 ONEPASS PC: ALL ENCRYPTED ARCHIVES COPIED AND SHA-VERIFIED.
  echo Actual owner private key decryption is NOT claimed by this utility.
)
pause
endlocal
