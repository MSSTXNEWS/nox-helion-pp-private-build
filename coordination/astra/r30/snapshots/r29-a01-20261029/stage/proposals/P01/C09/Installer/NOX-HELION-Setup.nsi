; NOX V16 P01 C3. Stage->verify->rename with rollback; one-user scope, no hidden prerequisite downloads.
Unicode true
RequestExecutionLevel user
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "FileFunc.nsh"
!ifndef PAYLOAD_DIR
  !error "Supply PAYLOAD_DIR pointing at self-contained published app"
!endif
!ifndef VERIFY_SCRIPT
  !error "Supply VERIFY_SCRIPT"
!endif
!ifndef PREFLIGHT_SCRIPT
  !error "Supply PREFLIGHT_SCRIPT"
!endif
!ifndef REMOVE_SCRIPT
  !error "Supply REMOVE_SCRIPT"
!endif
!ifndef OUTPUT_SETUP
  !error "Supply OUTPUT_SETUP"
!endif
!ifndef APP_VERSION
  !define APP_VERSION "0.1.0"
!endif
!define APP_NAME "NOX HELION"
!define APP_ID "NOXHELION.P01"
Name "${APP_NAME}"
OutFile "${OUTPUT_SETUP}"
InstallDir "$LOCALAPPDATA\Programs\NOX HELION"
SetCompressor /SOLID lzma
ShowInstDetails show
ShowUninstDetails show
!define MUI_ABORTWARNING
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Var StageDir
Var BackupDir
Var RollbackRequested
Var ExitCode
Var CheckResult
Var PrevDir
Var TmpDir

Function .onInit
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\NOX HELION"
  StrCpy $StageDir "$INSTDIR.__p01_stage"
  StrCpy $BackupDir "$INSTDIR.__p01_previous"
  StrCpy $RollbackRequested "0"
  ${GetParameters} $0
  ${GetOptions} "$0" "/ROLLBACK" $1
  IfErrors +2 0
    StrCpy $RollbackRequested "1"
FunctionEnd

Section "NOX HELION application" SEC_MAIN
  ; The install location is fixed; user data outside it is never modified.
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\NOX HELION"
  StrCpy $StageDir "$INSTDIR.__p01_stage"
  StrCpy $BackupDir "$INSTDIR.__p01_previous"
  ${If} $RollbackRequested == "1"
    Call RestorePrevious
    Goto FinishInstall
  ${EndIf}
  IfFileExists "$StageDir\*.*" 0 +2
    Abort "Previous staging dir found; manual recovery required."
  IfFileExists "$StageDir" 0 +2
    Abort "Previous staging dir found; manual recovery required."
  ; Only replace a folder whose explicit ownership marker was created by this installer.
  IfFileExists "$INSTDIR" 0 CheckBackup
    IfFileExists "$INSTDIR\nox-p01-owned.txt" +2 0
      Abort "Install path contains an unowned application. Refusing overwrite."
  CheckBackup:
  IfFileExists "$BackupDir" 0 Preflight
    Abort "Previous version backup exists. Run /ROLLBACK or preserve it before another update."
  Preflight:
  InitPluginsDir
  File "/oname=$PLUGINSDIR\Preflight-InstallPath.ps1" "${PREFLIGHT_SCRIPT}"
  nsExec::ExecToStack 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\Preflight-InstallPath.ps1" -InstallRoot "$INSTDIR"'
  Pop $ExitCode
  Pop $CheckResult
  ${If} $ExitCode != "0"
    DetailPrint "$CheckResult"
    Abort "Path or WebView2 runtime preflight failed. No changes made."
  ${EndIf}
  StagePayload:
  SetOutPath "$StageDir"
  File /r "${PAYLOAD_DIR}\*.*"
  IfErrors 0 +2
    Abort "Failed extracting staged payload."
  File "/oname=$PLUGINSDIR\Verify-Payload.ps1" "${VERIFY_SCRIPT}"
  nsExec::ExecToStack 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\Verify-Payload.ps1" -Root "$StageDir" -Manifest "$StageDir\payload.sha256.json"'
  Pop $ExitCode
  Pop $CheckResult
  ${If} $ExitCode != "0"
    DetailPrint "$CheckResult"
    Abort "Payload SHA-256 verification FAILED. No application files activated."
  ${EndIf}
  ; Marker ownership is required by update, rollback and conservative uninstall.
  ; A failed write must never reach either activation rename.
  ClearErrors
  FileOpen $2 "$StageDir\nox-p01-owned.txt" w
  IfErrors MarkerOpenFailed
  FileWrite $2 "NOXHELION.P01 V16$\r$\n"
  IfErrors MarkerWriteFailed
  FileClose $2
  ; FileWrite success alone does not prove persisted exact marker contents.
  ; Reopen/read back before FIRST rename; never accept partial/empty metadata.
  ClearErrors
  FileOpen $2 "$StageDir\nox-p01-owned.txt" r
  IfErrors MarkerReadbackFailed
  ClearErrors
  FileRead $2 $3
  IfErrors MarkerReadFailed
  FileClose $2
  StrCmp $3 "NOXHELION.P01 V16$\r$\n" MarkerReady MarkerReadbackFailed
  MarkerReadFailed:
    FileClose $2
  MarkerReadbackFailed:
    SetErrorLevel 2
    Abort "Ownership marker readback failed; no application directories moved."
  MarkerWriteFailed:
    FileClose $2
  MarkerOpenFailed:
    SetErrorLevel 2
    Abort "Could not write ownership marker. No application directories moved."
  MarkerReady:
  SetOutPath "$TEMP" ; release current working directory before Rename
  ; Preserve one backup for explicit rollback. Failed activation restores original.
  IfFileExists "$INSTDIR\nox-p01-owned.txt" 0 ActivateNew
    Rename "$INSTDIR" "$BackupDir"
    IfErrors 0 +2
      Abort "Old application in use. Close NOX before updating."
  ActivateNew:
  Rename "$StageDir" "$INSTDIR"
  IfErrors 0 +4
    IfFileExists "$BackupDir\nox-p01-owned.txt" 0 +2
      Rename "$BackupDir" "$INSTDIR"
    Abort "Activation failed; previous version restored if present."
  ; Registry/shortcuts only after activation.
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "DisplayName" "${APP_NAME}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "DisplayVersion" "${APP_VERSION}"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "NoModify" 1
  SetOutPath "$INSTDIR"
  WriteUninstaller "$INSTDIR\Uninstall.exe"
  CreateDirectory "$SMPROGRAMS\NOX HELION"
  CreateShortcut "$SMPROGRAMS\NOX HELION\NOX HELION.lnk" "$INSTDIR\NOX.P01.Shell.exe"
  DetailPrint "NOX installed. Persistent state under LOCALAPPDATA is untouched."
  FinishInstall:
SectionEnd

Function RestorePrevious
  SetOutPath "$TEMP"
  ; Reuse install path/ownership checks, including parents above the backup root.
  ; Recovery must not require an available WebView2 runtime.
  InitPluginsDir
  File "/oname=$PLUGINSDIR\Preflight-InstallPath.ps1" "${PREFLIGHT_SCRIPT}"
  nsExec::ExecToStack 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\Preflight-InstallPath.ps1" -InstallRoot "$INSTDIR" -PathOnly'
  Pop $ExitCode
  Pop $CheckResult
  ${If} $ExitCode != "0"
    DetailPrint "$CheckResult"
    SetErrorLevel 2
    Abort "Rollback path or ownership preflight failed. No application directories moved."
  ${EndIf}
  IfFileExists "$BackupDir\nox-p01-owned.txt" 0 NoPrevious
  IfFileExists "$INSTDIR\nox-p01-owned.txt" 0 NoCurrent
  IfFileExists "$StageDir" 0 +2
    Abort "Pending stage detected; resolve it first."
  StrCpy $TmpDir "$INSTDIR.__p01_rollback_saved"
  IfFileExists "$TmpDir" 0 +2
    Abort "Rollback-save exists; resolve it first."
  ; Verify every previous payload hash BEFORE moving either app directory.
  ; A mere ownership marker is not evidence of unmodified program files.
  InitPluginsDir
  File "/oname=$PLUGINSDIR\Verify-Payload.ps1" "${VERIFY_SCRIPT}"
  nsExec::ExecToStack 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\Verify-Payload.ps1" -Root "$BackupDir" -Manifest "$BackupDir\payload.sha256.json" -AllowInstalledMetadata -ReportVersion'
  Pop $ExitCode
  Pop $CheckResult
  ${If} $ExitCode != "0"
    DetailPrint "$CheckResult"
    SetErrorLevel 2
    Abort "Backup payload SHA-256 mismatch; rollback refused without moving application directories."
  ${EndIf}
  Rename "$INSTDIR" "$TmpDir"
  IfErrors 0 +2
    Abort "Cannot move current app. Close NOX first."
  Rename "$BackupDir" "$INSTDIR"
  IfErrors 0 +3
    Rename "$TmpDir" "$INSTDIR"
    Abort "Rollback activation failed; attempted restoration."
  ; Leave newer version saved for operator recovery, NEVER delete it.
  ; The backup verifier returned its validated version without a trailing newline.
  ; Register it only after BOTH directory renames succeeded.
  ClearErrors
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "DisplayVersion" "$CheckResult"
  IfErrors 0 +3
    SetErrorLevel 2
    Abort "Previous files restored, but Windows version registration failed. Recovery copies retained."
  DetailPrint "Previous version restored; superseded app retained at $TmpDir."
  Return
  NoPrevious:
    Abort "No installer-owned previous version available for rollback."
  NoCurrent:
    Abort "Current install not owned by P01; refusing rollback."
FunctionEnd

Section "Uninstall"
  StrCpy $INSTDIR "$LOCALAPPDATA\Programs\NOX HELION"
  IfFileExists "$INSTDIR\nox-p01-owned.txt" 0 DoneUninstall
  ; Critical guard: user-provided install directories and arbitrary roots are forbidden.
  StrCmp $INSTDIR "$LOCALAPPDATA\Programs\NOX HELION" 0 DoneUninstall
  ; Remove only manifest-listed, SHA-matching program files. Modified/unknown files survive.
  InitPluginsDir
  File "/oname=$PLUGINSDIR\Remove-InstalledPayload.ps1" "${REMOVE_SCRIPT}"
  nsExec::ExecToStack 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\Remove-InstalledPayload.ps1" -InstallRoot "$INSTDIR"'
  Pop $ExitCode
  Pop $CheckResult
  ${If} $ExitCode != "0"
    DetailPrint "$CheckResult"
    Abort "Conservative uninstall incomplete: modified files retained. No recursive removal."
  ${EndIf}
  Delete "$SMPROGRAMS\NOX HELION\NOX HELION.lnk"
  RMDir "$SMPROGRAMS\NOX HELION"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}"
  SetOutPath "$TEMP"
  Delete "$INSTDIR\payload.sha256.json"
  Delete "$INSTDIR\nox-p01-owned.txt"
  Delete "$INSTDIR\Uninstall.exe"
  RMDir "$INSTDIR"
  ; Do not touch __p01_previous or __p01_rollback_saved: recovery must be explicit.
  DoneUninstall:
SectionEnd
