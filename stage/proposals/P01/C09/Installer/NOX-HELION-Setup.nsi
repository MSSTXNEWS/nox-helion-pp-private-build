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
Var PrevRegVersion
Var HadPrevRegVersion

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
  ; Prevent stale $OUTDIR extraction if stage mkdir / SetOutPath fails.
  ClearErrors
  CreateDirectory "$StageDir"
  IfErrors 0 +3
    SetErrorLevel 2
    Abort "Unable to create staged directory; no payload extracted."
  ClearErrors
  SetOutPath "$StageDir"
  IfErrors 0 +3
    SetErrorLevel 2
    Abort "Unable to select staged output directory; no payload extracted."
  StrCmp $OUTDIR "$StageDir" +3 0
    SetErrorLevel 2
    Abort "Staged output path mismatch; no payload extracted."
  ClearErrors
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
  ; Prepare and SHA-attest the generated uninstaller in STAGING, before moving
  ; either live application tree. Keep the independently generated plugin copy
  ; as provenance for an after-activation integrity check.
  SetOutPath "$TEMP" ; release current working directory before Rename
  ClearErrors
  WriteUninstaller "$PLUGINSDIR\Uninstall.exe"
  IfErrors InstallUninstallerPreparationFailed
  IfFileExists "$PLUGINSDIR\Uninstall.exe" 0 InstallUninstallerPreparationFailed
  ClearErrors
  CopyFiles /SILENT "$PLUGINSDIR\Uninstall.exe" "$StageDir"
  IfErrors InstallUninstallerPreparationFailed
  nsExec::ExecToStack 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\Verify-Payload.ps1" -Root "$StageDir" -Manifest "$StageDir\payload.sha256.json" -AllowInstalledMetadata -TrustedUninstaller "$PLUGINSDIR\Uninstall.exe"'
  Pop $ExitCode
  Pop $CheckResult
  ${If} $ExitCode != "0"
    DetailPrint "$CheckResult"
    SetErrorLevel 2
    Abort "Staged uninstaller or payload SHA-256 verification failed; no application directories moved."
  ${EndIf}
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
  ; Re-hash the live activated directory BEFORE changing the registry.
  ; No success metadata may point to a missing, altered or untrusted Uninstall.exe.
  nsExec::ExecToStack 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\Verify-Payload.ps1" -Root "$INSTDIR" -Manifest "$INSTDIR\payload.sha256.json" -AllowInstalledMetadata -TrustedUninstaller "$PLUGINSDIR\Uninstall.exe"'
  Pop $ExitCode
  Pop $CheckResult
  ${If} $ExitCode != "0"
    DetailPrint "$CheckResult"
    Goto InstallPostActivationRecovery
  ${EndIf}
  ; Registry/shortcuts only after activation and exact live attestation.
  ; Capture prior version before changing HKCU; do not claim install success on failure.
  StrCpy $HadPrevRegVersion "0"
  StrCpy $PrevRegVersion ""
  ClearErrors
  ReadRegStr $PrevRegVersion HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "DisplayVersion"
  IfErrors +2 0
    StrCpy $HadPrevRegVersion "1"
  ClearErrors
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "DisplayName" "${APP_NAME}"
  IfErrors InstallRegistrationFailed
  ClearErrors
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "DisplayVersion" "${APP_VERSION}"
  IfErrors InstallRegistrationFailed
  ClearErrors
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "InstallLocation" "$INSTDIR"
  IfErrors InstallRegistrationFailed
  ClearErrors
  WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "UninstallString" '"$INSTDIR\Uninstall.exe"'
  IfErrors InstallRegistrationFailed
  ClearErrors
  WriteRegDWORD HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "NoModify" 1
  IfErrors InstallRegistrationFailed
  SetOutPath "$INSTDIR"
  CreateDirectory "$SMPROGRAMS\NOX HELION"
  ClearErrors
  CreateShortcut "$SMPROGRAMS\NOX HELION\NOX HELION.lnk" "$INSTDIR\NOX.P01.Shell.exe"
  IfErrors InstallRegistrationFailed
  DetailPrint "NOX installed. Persistent state under LOCALAPPDATA is untouched."
  Goto FinishInstall
  InstallUninstallerPreparationFailed:
    SetErrorLevel 2
    Abort "Could not prepare a trusted uninstaller; no application directories moved."
  InstallRegistrationFailed:
    ; Failed HKCU/shortcut finalization: preserve both program trees and all user data.
    ; Restore prior DisplayVersion best-effort, never delete unknown registry keys.
    ${If} $HadPrevRegVersion == "1"
      ClearErrors
      WriteRegStr HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "DisplayVersion" "$PrevRegVersion"
      IfErrors 0 +2
        DetailPrint "Prior DisplayVersion restoration failed; manual registry recovery needed."
    ${Else}
      ; Fresh-install failure must not leave phantom app entries in HKCU.
      ; If an owned previous tree exists, keep its values for manual recovery.
      IfFileExists "$BackupDir\nox-p01-owned.txt" 0 FreshInstallRegCleanup
        DetailPrint "Previous installer-owned registry data preserved for manual recovery."
        Goto FreshInstallRegDone
      FreshInstallRegCleanup:
        ; Only values written by THIS installer; never delete the whole key.
        ClearErrors
        DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "DisplayName"
        DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "DisplayVersion"
        DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "InstallLocation"
        DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "UninstallString"
        DeleteRegValue HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_ID}" "NoModify"
        IfErrors 0 +2
          DetailPrint "Registry cleanup incomplete; operator recovery required."
        DetailPrint "Fresh-install metadata cleanup attempted; unknown HKCU values retained."
      FreshInstallRegDone:
    ${EndIf}
    Goto InstallPostActivationRecovery
  InstallPostActivationRecovery:
    ; Fail closed: preserve the suspect new tree as staging, and restore
    ; the prior app if it was moved. Never delete/recurse user data.
    SetOutPath "$TEMP"
    ClearErrors
    Rename "$INSTDIR" "$StageDir"
    IfErrors InstallRecoveryHold
    IfFileExists "$BackupDir\nox-p01-owned.txt" 0 InstallRecoveryDone
      ClearErrors
      Rename "$BackupDir" "$INSTDIR"
      IfErrors InstallRecoveryHold
  InstallRecoveryDone:
    SetErrorLevel 2
    Abort "Activated payload attestation failed; previous app restored if present, failed stage retained."
  InstallRecoveryHold:
    SetErrorLevel 2
    Abort "Activated payload attestation failed; operator recovery needed, both app trees retained."
  FinishInstall:
SectionEnd

Function RestorePrevious
  SetOutPath "$TEMP"
  ; Reuse install path/ownership checks, including parents above the backup root.
  ; Existing preflight checks WebView2 too; missing runtime fails closed before moves.
  InitPluginsDir
  File "/oname=$PLUGINSDIR\Preflight-InstallPath.ps1" "${PREFLIGHT_SCRIPT}"
  nsExec::ExecToStack 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\Preflight-InstallPath.ps1" -InstallRoot "$INSTDIR"'
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
  ; The backup's generated Uninstall.exe is not SHA-attested by payload.sha256.json.
  ; Generate a trusted replacement from THIS setup before moving either app tree.
  ClearErrors
  WriteUninstaller "$PLUGINSDIR\Uninstall.exe"
  IfErrors 0 RollbackUninstallerPrepared
    SetErrorLevel 2
    Abort "Cannot prepare rollback uninstaller; both app versions remain untouched."
  RollbackUninstallerPrepared:
  IfFileExists "$PLUGINSDIR\Uninstall.exe" 0 RollbackUninstallerMissing
    Goto RollbackUninstallerReady
  RollbackUninstallerMissing:
    SetErrorLevel 2
    Abort "Generated rollback uninstaller missing; both app versions remain untouched."
  RollbackUninstallerReady:
  Rename "$INSTDIR" "$TmpDir"
  IfErrors 0 +2
    Abort "Cannot move current app. Close NOX first."
  Rename "$BackupDir" "$INSTDIR"
  IfErrors 0 +3
    Rename "$TmpDir" "$INSTDIR"
    Abort "Rollback activation failed; attempted restoration."
  ; Never reactivate the prior, merely size-checked Uninstall.exe as executable.
  ; Copy a fresh one from the trusted setup and verify exact SHA before registry writes.
  ClearErrors
  CopyFiles /SILENT "$PLUGINSDIR\Uninstall.exe" "$INSTDIR"
  IfErrors RollbackUninstallerRecovery
  nsExec::ExecToStack 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "$PLUGINSDIR\Verify-Payload.ps1" -Root "$INSTDIR" -Manifest "$INSTDIR\payload.sha256.json" -AllowInstalledMetadata -TrustedUninstaller "$PLUGINSDIR\Uninstall.exe" -ReportVersion'
  Pop $ExitCode
  Pop $CheckResult
  ${If} $ExitCode != "0"
    DetailPrint "$CheckResult"
    Goto RollbackUninstallerRecovery
  ${EndIf}
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
  RollbackUninstallerRecovery:
    ; Never report success after installer executable integrity fails.
    ; Preserve both app trees and attempt restoration of the original install.
    SetOutPath "$TEMP"
    ClearErrors
    Rename "$INSTDIR" "$BackupDir"
    IfErrors RollbackRecoveryFailed
    Rename "$TmpDir" "$INSTDIR"
    IfErrors RollbackRecoveryFailed
    SetErrorLevel 2
    Abort "Rollback uninstaller verification failed; current install restored, backup retained."
  RollbackRecoveryFailed:
    SetErrorLevel 2
    Abort "Rollback uninstaller integrity failed; operator recovery needed, app trees retained."
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
