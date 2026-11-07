# B06 R8: owner-Windows one-SHA real Qwen+STOP+isolated SQLite gate, NOT a full release.
# This script never installs, downloads weights or alters owner's live SQLite.
[CmdletBinding()]
param(
  [string]$ExePath='C:\NOX_HELION\NOX_NEW\release\NOX.HELION.exe',
  [Parameter(Mandatory=$true)][ValidatePattern('^[0-9a-fA-F]{64}$')][string]$ExpectedSha256,
  [ValidateRange(30,900)][int]$TimeoutSeconds=360
)
Set-StrictMode -Version Latest
$ErrorActionPreference='Stop'
function Snapshot([string]$folder) {
  $r=[ordered]@{}
  foreach($name in @('chat.sqlite3','chat.sqlite3-wal','chat.sqlite3-shm')) {
    $p=Join-Path $folder $name
    $r[$name]=if(Test-Path -LiteralPath $p -PathType Leaf) {
      (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()
    } else { 'ABSENT' }
  }
  return $r
}
$id='B06-'+[guid]::NewGuid().ToString('N')
$started=[DateTimeOffset]::UtcNow
$dataDir=Join-Path $env:LOCALAPPDATA 'NOX_HELION'
$r=[ordered]@{
  schema='NOX_R8_B06_OWNER_SAMESHA_E2E_V1'; runId=$id; startedAt=$started.ToString('O')
  expectedSha256=$ExpectedSha256.ToLowerInvariant(); exe=$ExePath
  exeShaBefore=$null; exeShaAfter=$null; sourceGitSha='NOT_VERIFIED'
  provider='http://127.0.0.1:11436'; model='nox-qwen-clean:latest'
  providerVerified=$false; modelDigest=$null; providerRuntimeVerified=$false; nativePid=$null; nativeExit=$null
  nativeReceiptVerified=$false; nativeChecks=@{}; ownerSqliteUnchanged=$false
  uiSmokeAccepted=$false; uiSmokePid=$null; uiSmokeChecks=@{}
  uiSettingsRestartVerified=$false; uiRestartPid=$null; uiRestartChecks=@{}
  physicalScopeAccepted=$false; releaseAccepted=$false; fullV16Accepted=$false
  canonicalD02='NOT_TESTED'; installerNoLoss='NOT_TESTED'
  ownerHistoryRestart='NOT_TESTED'; nativeTokenChunkCount='NOT_OBSERVED'
  status='HOLD'; error=$null
}
$baseline=$null; $p=$null
try {
  $exe=[IO.Path]::GetFullPath($ExePath)
  $r.exe=$exe
  if(!(Test-Path -LiteralPath $exe -PathType Leaf)){throw 'EXE_NOT_FOUND_HOLD'}
  $hash=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
  $r.exeShaBefore=$hash
  if($hash -cne $r.expectedSha256){throw 'IMMUTABLE_EXE_SHA_MISMATCH_HOLD'}
  # Exact R8 identity is not established by a caller-supplied EXE digest alone.
  # A missing/stale build manifest is HOLD, not a partially accepted local release.
  $buildPath=Join-Path (Split-Path -Parent $exe) 'BUILD_RECEIPT.json'
  if(!(Test-Path -LiteralPath $buildPath -PathType Leaf)){
    throw 'R8_BUILD_RECEIPT_MISSING_HOLD'
  }
  $build=Get-Content -LiteralPath $buildPath -Raw -Encoding UTF8 | ConvertFrom-Json
  if([string]$build.schema -cne 'NOX_R8_NATIVE_SINGLE_EXE_V1'){
    throw 'R8_BUILD_RECEIPT_SCHEMA_HOLD'
  }
  if(![string]::Equals([string]$build.exe_sha256,$hash,[StringComparison]::OrdinalIgnoreCase)){
    throw 'BUILD_RECEIPT_EXE_SHA_MISMATCH_HOLD'
  }
  if([string]$build.source_git_sha -cnotmatch '^[0-9a-fA-F]{40}
  $baseline=Snapshot $dataDir
  $tags=Invoke-RestMethod -Uri 'http://127.0.0.1:11436/api/tags' -TimeoutSec 8 -Method Get
  # Verify installed model identity, not just tag presence. No model download.
  $registered=@($tags.models | Where-Object { [string]$_.name -ceq $r.model })
  if($registered.Count -ne 1){throw 'REAL_LOCAL_QWEN_MODEL_NOT_VISIBLE_HOLD'}
  $registeredDigest=[string]$registered[0].digest
  if($registeredDigest -cnotmatch '^[0-9a-fA-F]{64}$'){throw 'MODEL_DIGEST_MISSING_HOLD'}
  $r.modelDigest=$registeredDigest.ToLowerInvariant()
  $r.providerVerified=$true
  # Only a new native --nox-selftest child, never any preexisting app process.
  $p=Start-Process -FilePath $exe -WorkingDirectory (Split-Path -Parent $exe) -ArgumentList @('--nox-selftest',"--nox-runid=$id") -PassThru
  $r.nativePid=$p.Id
  if(!$p.WaitForExit($TimeoutSeconds*1000)){throw 'NATIVE_REAL_QWEN_TIMEOUT_HOLD'}
  $p.Refresh();$r.nativeExit=$p.ExitCode
  $nativePath=Join-Path $dataDir ("native_selftest_{0}.json" -f $p.Id)
  if(!(Test-Path -LiteralPath $nativePath -PathType Leaf)){throw 'NATIVE_RECEIPT_MISSING_HOLD'}
  $n=Get-Content -LiteralPath $nativePath -Raw -Encoding UTF8 | ConvertFrom-Json
  if($p.ExitCode -ne 0 -or $n.schema -cne 'NOX_WPF_E2E_NATIVE_R5_V1' -or
      [int]$n.pid -ne $p.Id -or [string]$n.runId -cne $id -or
      !$n.nativeCoreAccepted -or $n.fullV16Accepted -or
      ![string]::Equals([string]$n.exeSha256,$hash,[StringComparison]::OrdinalIgnoreCase) -or
      ![string]::Equals([IO.Path]::GetFullPath([string]$n.exe),$exe,[StringComparison]::OrdinalIgnoreCase)){
    throw 'NATIVE_RECEIPT_IDENTITY_OR_SHA_HOLD'
  }
  $when=[DateTimeOffset]::Parse([string]$n.checkedAt)
  if($when -lt $started -or $when -gt [DateTimeOffset]::UtcNow.AddMinutes(2)){
    throw 'NATIVE_RECEIPT_TIME_HOLD'
  }
  foreach($name in @('webview2_real_ui_route','sqlite_transaction_readback',
      'real_ollama_model_registered','real_chat_from_webview_to_qwen_to_sqlite',
      'real_webview_stop_cancel_no_partial_persistence')){
    $value=[string]$n.checks.$name
    $r.nativeChecks[$name]=$value
    if($value -cne 'PASS'){throw "NATIVE_CHECK_$($name)_HOLD"}
  }
  $r.nativeReceiptVerified=$true

  # /api/ps reports loaded models; /api/tags reports only installed models.
  # After the native Qwen chat, require the same digest to be resident.
  $running=Invoke-RestMethod -Uri 'http://127.0.0.1:11436/api/ps' -TimeoutSec 8 -Method Get
  $activeModels=@($running.models | Where-Object { [string]$_.name -ceq $r.model })
  if($activeModels.Count -ne 1){throw 'REAL_QWEN_NOT_RUNNING_AFTER_CHAT_HOLD'}
  $runtimeDigest=[string]$activeModels[0].digest
  if($runtimeDigest -cnotmatch '^[0-9a-fA-F]{64}$' -or
      ![string]::Equals($runtimeDigest,$r.modelDigest,[StringComparison]::OrdinalIgnoreCase)){
    throw 'REAL_QWEN_LOADED_DIGEST_MISMATCH_HOLD'
  }
  $r.providerRuntimeVerified=$true

  # Second real Windows WPF/WebView2 process: native eight-route, accessibility
  # and isolated SQLite/settings validation. It never touches chat.sqlite3.
  function Check-UiProcess([bool]$Restart) {
    $uiStarted=[DateTimeOffset]::UtcNow
    $uiArgs=if($Restart) {
      @('--nox-ui-smoke','--nox-settings-restart-readback',"--nox-runid=$id")
    } else { @('--nox-ui-smoke',"--nox-runid=$id") }
    $uiProcess=$null
    try {
      $uiProcess=Start-Process -FilePath $exe -WorkingDirectory (Split-Path -Parent $exe) -ArgumentList $uiArgs -PassThru
      if(!$uiProcess.WaitForExit($TimeoutSeconds*1000)) { throw 'NATIVE_UI_PROCESS_TIMEOUT_HOLD' }
      $uiProcess.Refresh()
      $uiPath=Join-Path $dataDir ("ui_selftest_{0}.json" -f $uiProcess.Id)
      if(!(Test-Path -LiteralPath $uiPath -PathType Leaf)){throw 'NATIVE_UI_RECEIPT_MISSING_HOLD'}
      $u=Get-Content -LiteralPath $uiPath -Raw -Encoding UTF8 | ConvertFrom-Json
      $uiStamp=[DateTimeOffset]::Parse([string]$u.checkedAt)
      if($uiProcess.ExitCode -ne 0 -or $u.schema -cne 'NOX_WPF_UI_SMOKE_R7_V1' -or
          [int]$u.pid -ne $uiProcess.Id -or [string]$u.runId -cne $id -or
          !$u.wpfWebView2Accepted -or
          $uiStamp -lt $uiStarted -or $uiStamp -gt [DateTimeOffset]::UtcNow.AddMinutes(2) -or
          ![string]::Equals([string]$u.exeSha256,$hash,[StringComparison]::OrdinalIgnoreCase) -or
          ![string]::Equals([IO.Path]::GetFullPath([string]$u.exe),$exe,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'NATIVE_UI_IDENTITY_TIMESTAMP_OR_SHA_HOLD'
      }
      $mustPass=if($Restart) {
        @('isolated_sqlite_path','settings_wpf_owner_restart_readback')
      } else {
        @('real_webview2_eight_routes','real_webview2_keyboard_routes',
          'd01_five_quick_native_routes','d01_five_quick_windows_uia',
          'd01_five_quick_compact_320_390_800',
          'settings_windows_uia_host','settings_webview2_accessible_controls',
          'settings_wpf_owner_sqlite_readback','settings_wpf_motion_sqlite_readback',
          'settings_foreign_key_denial','sqlite_native_backup_no_loss',
          'isolated_sqlite_path','native_wpf_webview2_renderer')
      }
      $observed=[ordered]@{}
      foreach($key in $mustPass) {
        $value=[string]$u.checks.$key
        $observed[$key]=$value
        if($value -cne 'PASS') { throw "NATIVE_UI_CHECK_$($key)_HOLD" }
      }
      return @{pid=$uiProcess.Id;checks=$observed;sha=$hash;restart=$Restart}
    }
    finally {
      if($null -ne $uiProcess) {
        $uiProcess.Refresh()
        if(!$uiProcess.HasExited) {
          $uiProcess.Kill() # Only the process created by this gate.
          $uiProcess.WaitForExit(10000) | Out-Null
        }
      }
    }
  }
  $ui=Check-UiProcess $false
  $r.uiSmokePid=$ui.pid
  $r.uiSmokeChecks=$ui.checks
  $r.uiSmokeAccepted=$true
  # Same run ID: a second process must read settings committed by the first.
  $uiRestart=Check-UiProcess $true
  $r.uiRestartPid=$uiRestart.pid
  $r.uiRestartChecks=$uiRestart.checks
  $r.uiSettingsRestartVerified=$true
} catch {
  $r.error=$_.Exception.Message
} finally {
  if($null -ne $p) {
    try {
      $p.Refresh()
      if(!$p.HasExited){
        $p.Kill()  # Only acceptance-owned PID, never another NOX or Ollama.
        $p.WaitForExit(10000) | Out-Null
      }
      if($null -eq $r.nativeExit -and $p.HasExited){$r.nativeExit=$p.ExitCode}
    } catch {$r.error=([string]$r.error+' CHILD_CLEANUP_HOLD: '+$_.Exception.Message).Trim()}
  }
  try {
    if(Test-Path -LiteralPath $r.exe -PathType Leaf){
      $r.exeShaAfter=(Get-FileHash -LiteralPath $r.exe -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    if($null -ne $baseline) {
      $after=Snapshot $dataDir
      $r.ownerSqliteUnchanged=(ConvertTo-Json -InputObject $baseline -Compress) -ceq
                              (ConvertTo-Json -InputObject $after -Compress)
    }
    if($r.exeShaBefore -cne $r.expectedSha256 -or $r.exeShaAfter -cne $r.expectedSha256){
      throw 'SAME_SHA_PRE_POST_HOLD'
    }
    if(!$r.ownerSqliteUnchanged){throw 'OWNER_SQLITE_CHANGED_DURING_ACCEPTANCE_HOLD'}
    if($r.nativeReceiptVerified -and $r.providerVerified -and $r.providerRuntimeVerified -and $r.uiSmokeAccepted -and $r.uiSettingsRestartVerified -and !$r.error){
      $r.physicalScopeAccepted=$true
      $r.status='NATIVE_QWEN_STOP_UI_SETTINGS_SCOPE_PASS_RELEASE_HOLD'
    }
  } catch {$r.error=([string]$r.error+' '+$_.Exception.Message).Trim()}
  $r['finishedAt']=[DateTimeOffset]::UtcNow.ToString('O')
  # No D02/full-V16/owner restart/installer confirmation in this scoped gate.
  $r.releaseAccepted=$false
  $dest=Join-Path $dataDir 'acceptance'
  New-Item -ItemType Directory -Path $dest -Force | Out-Null
  $out=Join-Path $dest ("B06_E2E_{0}.json" -f $id)
  $tmp=$out+'.tmp'
  [IO.File]::WriteAllText($tmp,(ConvertTo-Json -InputObject $r -Depth 8),[Text.UTF8Encoding]::new($false))
  Move-Item -LiteralPath $tmp -Destination $out
  Write-Output ("B06_STATUS={0} RELEASE=HOLD RECEIPT={1}" -f $r.status,$out)
}
if(!$r.physicalScopeAccepted){exit 2}
exit 0
){
    throw 'R8_BUILD_SOURCE_GIT_SHA_INVALID_HOLD'
  }
  $r.sourceGitSha=([string]$build.source_git_sha).ToLowerInvariant()
  $baseline=Snapshot $dataDir
  $tags=Invoke-RestMethod -Uri 'http://127.0.0.1:11436/api/tags' -TimeoutSec 8 -Method Get
  # Verify installed model identity, not just tag presence. No model download.
  $registered=@($tags.models | Where-Object { [string]$_.name -ceq $r.model })
  if($registered.Count -ne 1){throw 'REAL_LOCAL_QWEN_MODEL_NOT_VISIBLE_HOLD'}
  $registeredDigest=[string]$registered[0].digest
  if($registeredDigest -cnotmatch '^[0-9a-fA-F]{64}$'){throw 'MODEL_DIGEST_MISSING_HOLD'}
  $r.modelDigest=$registeredDigest.ToLowerInvariant()
  $r.providerVerified=$true
  # Only a new native --nox-selftest child, never any preexisting app process.
  $p=Start-Process -FilePath $exe -WorkingDirectory (Split-Path -Parent $exe) -ArgumentList @('--nox-selftest',"--nox-runid=$id") -PassThru
  $r.nativePid=$p.Id
  if(!$p.WaitForExit($TimeoutSeconds*1000)){throw 'NATIVE_REAL_QWEN_TIMEOUT_HOLD'}
  $p.Refresh();$r.nativeExit=$p.ExitCode
  $nativePath=Join-Path $dataDir ("native_selftest_{0}.json" -f $p.Id)
  if(!(Test-Path -LiteralPath $nativePath -PathType Leaf)){throw 'NATIVE_RECEIPT_MISSING_HOLD'}
  $n=Get-Content -LiteralPath $nativePath -Raw -Encoding UTF8 | ConvertFrom-Json
  if($p.ExitCode -ne 0 -or $n.schema -cne 'NOX_WPF_E2E_NATIVE_R5_V1' -or
      [int]$n.pid -ne $p.Id -or [string]$n.runId -cne $id -or
      !$n.nativeCoreAccepted -or $n.fullV16Accepted -or
      ![string]::Equals([string]$n.exeSha256,$hash,[StringComparison]::OrdinalIgnoreCase) -or
      ![string]::Equals([IO.Path]::GetFullPath([string]$n.exe),$exe,[StringComparison]::OrdinalIgnoreCase)){
    throw 'NATIVE_RECEIPT_IDENTITY_OR_SHA_HOLD'
  }
  $when=[DateTimeOffset]::Parse([string]$n.checkedAt)
  if($when -lt $started -or $when -gt [DateTimeOffset]::UtcNow.AddMinutes(2)){
    throw 'NATIVE_RECEIPT_TIME_HOLD'
  }
  foreach($name in @('webview2_real_ui_route','sqlite_transaction_readback',
      'real_ollama_model_registered','real_chat_from_webview_to_qwen_to_sqlite',
      'real_webview_stop_cancel_no_partial_persistence')){
    $value=[string]$n.checks.$name
    $r.nativeChecks[$name]=$value
    if($value -cne 'PASS'){throw "NATIVE_CHECK_$($name)_HOLD"}
  }
  $r.nativeReceiptVerified=$true

  # /api/ps reports loaded models; /api/tags reports only installed models.
  # After the native Qwen chat, require the same digest to be resident.
  $running=Invoke-RestMethod -Uri 'http://127.0.0.1:11436/api/ps' -TimeoutSec 8 -Method Get
  $activeModels=@($running.models | Where-Object { [string]$_.name -ceq $r.model })
  if($activeModels.Count -ne 1){throw 'REAL_QWEN_NOT_RUNNING_AFTER_CHAT_HOLD'}
  $runtimeDigest=[string]$activeModels[0].digest
  if($runtimeDigest -cnotmatch '^[0-9a-fA-F]{64}$' -or
      ![string]::Equals($runtimeDigest,$r.modelDigest,[StringComparison]::OrdinalIgnoreCase)){
    throw 'REAL_QWEN_LOADED_DIGEST_MISMATCH_HOLD'
  }
  $r.providerRuntimeVerified=$true

  # Second real Windows WPF/WebView2 process: native eight-route, accessibility
  # and isolated SQLite/settings validation. It never touches chat.sqlite3.
  function Check-UiProcess([bool]$Restart) {
    $uiStarted=[DateTimeOffset]::UtcNow
    $uiArgs=if($Restart) {
      @('--nox-ui-smoke','--nox-settings-restart-readback',"--nox-runid=$id")
    } else { @('--nox-ui-smoke',"--nox-runid=$id") }
    $uiProcess=$null
    try {
      $uiProcess=Start-Process -FilePath $exe -WorkingDirectory (Split-Path -Parent $exe) -ArgumentList $uiArgs -PassThru
      if(!$uiProcess.WaitForExit($TimeoutSeconds*1000)) { throw 'NATIVE_UI_PROCESS_TIMEOUT_HOLD' }
      $uiProcess.Refresh()
      $uiPath=Join-Path $dataDir ("ui_selftest_{0}.json" -f $uiProcess.Id)
      if(!(Test-Path -LiteralPath $uiPath -PathType Leaf)){throw 'NATIVE_UI_RECEIPT_MISSING_HOLD'}
      $u=Get-Content -LiteralPath $uiPath -Raw -Encoding UTF8 | ConvertFrom-Json
      $uiStamp=[DateTimeOffset]::Parse([string]$u.checkedAt)
      if($uiProcess.ExitCode -ne 0 -or $u.schema -cne 'NOX_WPF_UI_SMOKE_R7_V1' -or
          [int]$u.pid -ne $uiProcess.Id -or [string]$u.runId -cne $id -or
          !$u.wpfWebView2Accepted -or
          $uiStamp -lt $uiStarted -or $uiStamp -gt [DateTimeOffset]::UtcNow.AddMinutes(2) -or
          ![string]::Equals([string]$u.exeSha256,$hash,[StringComparison]::OrdinalIgnoreCase) -or
          ![string]::Equals([IO.Path]::GetFullPath([string]$u.exe),$exe,[StringComparison]::OrdinalIgnoreCase)) {
        throw 'NATIVE_UI_IDENTITY_TIMESTAMP_OR_SHA_HOLD'
      }
      $mustPass=if($Restart) {
        @('isolated_sqlite_path','settings_wpf_owner_restart_readback')
      } else {
        @('real_webview2_eight_routes','real_webview2_keyboard_routes',
          'd01_five_quick_native_routes','d01_five_quick_windows_uia',
          'd01_five_quick_compact_320_390_800',
          'settings_windows_uia_host','settings_webview2_accessible_controls',
          'settings_wpf_owner_sqlite_readback','settings_wpf_motion_sqlite_readback',
          'settings_foreign_key_denial','sqlite_native_backup_no_loss',
          'isolated_sqlite_path','native_wpf_webview2_renderer')
      }
      $observed=[ordered]@{}
      foreach($key in $mustPass) {
        $value=[string]$u.checks.$key
        $observed[$key]=$value
        if($value -cne 'PASS') { throw "NATIVE_UI_CHECK_$($key)_HOLD" }
      }
      return @{pid=$uiProcess.Id;checks=$observed;sha=$hash;restart=$Restart}
    }
    finally {
      if($null -ne $uiProcess) {
        $uiProcess.Refresh()
        if(!$uiProcess.HasExited) {
          $uiProcess.Kill() # Only the process created by this gate.
          $uiProcess.WaitForExit(10000) | Out-Null
        }
      }
    }
  }
  $ui=Check-UiProcess $false
  $r.uiSmokePid=$ui.pid
  $r.uiSmokeChecks=$ui.checks
  $r.uiSmokeAccepted=$true
  # Same run ID: a second process must read settings committed by the first.
  $uiRestart=Check-UiProcess $true
  $r.uiRestartPid=$uiRestart.pid
  $r.uiRestartChecks=$uiRestart.checks
  $r.uiSettingsRestartVerified=$true
} catch {
  $r.error=$_.Exception.Message
} finally {
  if($null -ne $p) {
    try {
      $p.Refresh()
      if(!$p.HasExited){
        $p.Kill()  # Only acceptance-owned PID, never another NOX or Ollama.
        $p.WaitForExit(10000) | Out-Null
      }
      if($null -eq $r.nativeExit -and $p.HasExited){$r.nativeExit=$p.ExitCode}
    } catch {$r.error=([string]$r.error+' CHILD_CLEANUP_HOLD: '+$_.Exception.Message).Trim()}
  }
  try {
    if(Test-Path -LiteralPath $r.exe -PathType Leaf){
      $r.exeShaAfter=(Get-FileHash -LiteralPath $r.exe -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    if($null -ne $baseline) {
      $after=Snapshot $dataDir
      $r.ownerSqliteUnchanged=(ConvertTo-Json -InputObject $baseline -Compress) -ceq
                              (ConvertTo-Json -InputObject $after -Compress)
    }
    if($r.exeShaBefore -cne $r.expectedSha256 -or $r.exeShaAfter -cne $r.expectedSha256){
      throw 'SAME_SHA_PRE_POST_HOLD'
    }
    if(!$r.ownerSqliteUnchanged){throw 'OWNER_SQLITE_CHANGED_DURING_ACCEPTANCE_HOLD'}
    if($r.nativeReceiptVerified -and $r.providerVerified -and $r.providerRuntimeVerified -and $r.uiSmokeAccepted -and $r.uiSettingsRestartVerified -and !$r.error){
      $r.physicalScopeAccepted=$true
      $r.status='NATIVE_QWEN_STOP_UI_SETTINGS_SCOPE_PASS_RELEASE_HOLD'
    }
  } catch {$r.error=([string]$r.error+' '+$_.Exception.Message).Trim()}
  $r['finishedAt']=[DateTimeOffset]::UtcNow.ToString('O')
  # No D02/full-V16/owner restart/installer confirmation in this scoped gate.
  $r.releaseAccepted=$false
  $dest=Join-Path $dataDir 'acceptance'
  New-Item -ItemType Directory -Path $dest -Force | Out-Null
  $out=Join-Path $dest ("B06_E2E_{0}.json" -f $id)
  $tmp=$out+'.tmp'
  [IO.File]::WriteAllText($tmp,(ConvertTo-Json -InputObject $r -Depth 8),[Text.UTF8Encoding]::new($false))
  Move-Item -LiteralPath $tmp -Destination $out
  Write-Output ("B06_STATUS={0} RELEASE=HOLD RECEIPT={1}" -f $r.status,$out)
}
if(!$r.physicalScopeAccepted){exit 2}
exit 0
