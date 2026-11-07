; B05 staged NSIS install of one existing EXE; never overwrite owner NOX_NEW.
; All input SHAs required. No new backend, service, models or data migration.
!include "LogicLib.nsh"
!ifndef NOX_EXE_PATH
 !error "NOX_EXE_PATH required"
!endif
!ifndef NOX_RECEIPT_PATH
 !error "NOX_RECEIPT_PATH required"
!endif
!ifndef NOX_GUARD_PATH
 !error "NOX_GUARD_PATH required"
!endif
!ifndef NOX_EXE_SHA256
 !error "NOX_EXE_SHA256 required"
!endif
!ifndef NOX_RECEIPT_SHA256
 !error "NOX_RECEIPT_SHA256 required"
!endif
!ifndef NOX_SOURCE_GIT_SHA
 !error "NOX_SOURCE_GIT_SHA required"
!endif
!ifndef NOX_SETUP_OUT
 !error "NOX_SETUP_OUT required"
!endif
Unicode true
Name "NOX HELION R8 per-user immutable installer"
OutFile "${NOX_SETUP_OUT}"
RequestExecutionLevel user
InstallDir "$LOCALAPPDATA\Programs\NOX-HELION-R8\${NOX_EXE_SHA256}"
Page instfiles
UninstPage instfiles
ShowInstDetails show
ShowUninstDetails show

!macro CheckMode MODE
 nsExec::ExecToStack '"$SYSDIR\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\NoLossGuard.ps1" -Mode ${MODE} -InstallDir "$INSTDIR" -ExpectedExeSha "${NOX_EXE_SHA256}" -ExpectedReceiptSha "${NOX_RECEIPT_SHA256}" -ExpectedSourceSha "${NOX_SOURCE_GIT_SHA}" -PayloadDir "$8"
 Pop $0
 Pop $1
 ${If} $0 != "0"
   !ifdef NOX_B05_FIXTURE_TRACE
    FileOpen $9 "$TEMP\NOX_B05_NSIS_FIXTURE_TRACE.txt" w
    FileWrite $9 "MODE=${MODE}; EXIT=$0; OUTPUT=$1; INSTDIR=$INSTDIR; PLUGINSDIR=$PLUGINSDIR"
    FileClose $9
   !endif
   DetailPrint "B05_NOLOSS_HOLD ${MODE} $1"
   MessageBox MB_OK|MB_ICONSTOP "NOX install boundary refused. Existing owner data untouched." /SD IDOK
   Abort
 ${EndIf}
!macroend

Function .onInit
 StrCpy $INSTDIR "$LOCALAPPDATA\Programs\NOX-HELION-R8\${NOX_EXE_SHA256}"
 InitPluginsDir
 StrCpy $8 "$PLUGINSDIR\payload"
 CreateDirectory "$8"
 File "/oname=$PLUGINSDIR\NoLossGuard.ps1" "${NOX_GUARD_PATH}"
 ; Validate bundled EXE and receipt before creating the per-user target.
 File "/oname=$PLUGINSDIR\payload\NOX.HELION.exe" "${NOX_EXE_PATH}"
 File "/oname=$PLUGINSDIR\payload\BUILD_RECEIPT.json" "${NOX_RECEIPT_PATH}"
 !insertmacro CheckMode PreInstall
FunctionEnd

Section "Install immutable NOX R8"
 ; Only create the dedicated parent; do not create the immutable target here.
 SetOutPath "$LOCALAPPDATA\Programs\NOX-HELION-R8"
 ; One same-volume directory rename promotes BOTH prevalidated files together.
 ; A cross-volume or denied rename must fail CLOSED without a partial target.
 ClearErrors
 Rename "$PLUGINSDIR\payload" "$INSTDIR"
 IfErrors 0 +3
   DetailPrint "B05_NOLOSS_HOLD:ATOMIC_PAYLOAD_PROMOTION_FAILED"
   Abort
 !insertmacro CheckMode PostInstall
 WriteUninstaller "$INSTDIR\Uninstall.exe"
 ; Do NOT launch or modify existing local models, settings, SQLite or Ollama.
SectionEnd

Function un.onInit
 InitPluginsDir
 StrCpy $8 "$PLUGINSDIR\payload"
 File "/oname=$PLUGINSDIR\NoLossGuard.ps1" "${NOX_GUARD_PATH}"
 !insertmacro CheckMode PreUninstall
FunctionEnd

Section "Uninstall"
 ; Only these three SHA-verified/installer-owned paths. Never RMDir /r.
 Delete "$INSTDIR\NOX.HELION.exe"
 Delete "$INSTDIR\BUILD_RECEIPT.json"
 Delete "$INSTDIR\Uninstall.exe"
 RMDir "$INSTDIR"
SectionEnd
