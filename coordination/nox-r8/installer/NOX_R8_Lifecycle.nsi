; NOX R8 B03 NSIS lifecycle wrapper. Build ONLY after exact EXE SHA is accepted.
Unicode true
RequestExecutionLevel user
Name "NOX HELION R8"
!include "MUI2.nsh"
!ifndef NOX_EXE_PATH
  !error "NOX_EXE_PATH required"
!endif
!ifndef NOX_EXE_SHA256
  !error "NOX_EXE_SHA256 required"
!endif
OutFile "NOX.HELION.R8.Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\NOX_HELION"
ShowInstDetails show
ShowUninstDetails show
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "Russian"
Section "NOX HELION R8"
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  File /oname=NOX.HELION.exe "${NOX_EXE_PATH}"
  File /oname=NOX_R8_Lifecycle.ps1 "NOX_R8_Lifecycle.ps1"
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -File "$PLUGINSDIR\NOX_R8_Lifecycle.ps1" -Mode Install -Payload "$PLUGINSDIR\NOX.HELION.exe" -ExpectedSha256 "${NOX_EXE_SHA256}"'
  Pop $0
  Pop $1
  StrCmp $0 "0" accepted
  DetailPrint "NOX_INSTALL_HOLD: $0 $1"
  Abort "NOX install failed. Owner files were not deleted."
accepted:
  SetOutPath "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.NOX.HELION.exe"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NOX_HELION_R8" "DisplayName" "NOX HELION R8"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NOX_HELION_R8" "UninstallString" '$"$INSTDIR\Uninstall.NOX.HELION.exe$"'
SectionEnd
Section "Uninstall"
  InitPluginsDir
  SetOutPath "$PLUGINSDIR"
  File /oname=NOX_R8_Lifecycle.ps1 "NOX_R8_Lifecycle.ps1"
  nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -File "$PLUGINSDIR\NOX_R8_Lifecycle.ps1" -Mode Uninstall'
  Pop $0
  Pop $1
  StrCmp $0 "0" accepted_uninstall
  DetailPrint "NOX_UNINSTALL_HOLD: $0 $1"
  Abort "NOX uninstall refused to modify unmanaged owner data."
accepted_uninstall:
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\NOX_HELION_R8"
  Delete "$INSTDIR\Uninstall.NOX.HELION.exe"
  RMDir "$INSTDIR"
SectionEnd
