param([int]$MaxFiles = 300, [switch]$SkipSetup)
$ErrorActionPreference='Stop'
$HostName='69.30.85.188'; $Port='22199'
$Identity=Join-Path $env:USERPROFILE '.ssh\nox_runpod_ed25519'
$Root='C:\NOX_HELION\NOX_NEW\RUNPOD_BACKUP'
$Script='C:\NOX_HELION\NOX_NEW\scripts\nox_runpod_backup_5min.ps1'
$Log=Join-Path $Root 'backup_events.log'
$Ssh='ssh.exe';$Scp='scp.exe'
New-Item -Type Directory -Force -Path $Root,(Split-Path $Script) | Out-Null
if(-not (Test-Path -LiteralPath $Identity)){throw 'NOX_SSH_PRIVATE_KEY_NOT_FOUND'}
$mutex=New-Object System.Threading.Mutex($false,'Global\NOX_RunpodBackup5Min')
$locked=$false
try {
  $locked=$mutex.WaitOne(0)
  if(-not $locked){Write-Host 'NOX_BACKUP_ALREADY_RUNNING';exit 0}
  function Log([string]$msg){
    $s="[$(Get-Date -Format o)] $msg"
    Add-Content -LiteralPath $Log -Value $s -Encoding UTF8
    Write-Host $s
  }
  function Remote([string]$cmd){
    $output=& $Ssh -o BatchMode=yes -o ConnectTimeout=12 -i $Identity -p $Port ("root@"+$HostName) $cmd 2>&1
    if($LASTEXITCODE -ne 0){throw ("SSH_FAIL "+(($output|Out-String).Trim()))}
    return ($output|Out-String).Trim()
  }
  $remoteAgent='/workspace/nox/tools/nox_backup_agent.py'
  $agentUrl='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/4421c4f3adfaa9fb0babbf43affe2f6e729436f8/nox_runpod/stage0/nox_backup_agent.py'
  Log 'NOX_BACKUP_SESSION_START'
  Remote ("mkdir -p /workspace/nox/tools; curl -fLsS --retry 3 '"+$agentUrl+"' -o "+$remoteAgent+".new && python3 -m py_compile "+$remoteAgent+".new && mv -f "+$remoteAgent+".new "+$remoteAgent) | Out-Null
  if(-not $SkipSetup){
    # Register a user-level 5-minute task; backups occur only while Windows is on.
    $tr='powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "'+$Script+'" -SkipSetup'
    $response=& schtasks.exe /Create /TN 'NOX-RunPod-Backup-5min' /SC MINUTE /MO 5 /TR $tr /F 2>&1
    if($LASTEXITCODE -ne 0){Log ("SCHEDULE_WARNING "+($response|Out-String))}
    else {Log 'NOX_BACKUP_5MIN_SCHEDULE_REGISTERED'}
  }
  $inv=Remote ('python3 '+$remoteAgent+' inventory') | ConvertFrom-Json
  $count=0;$verified=0;$pruned=0;$failed=0;$bytes=[long]0
  foreach($item in $inv.entries){
    if($count -ge $MaxFiles){break}
    $rel=[string]$item.path
    if($rel -notmatch '^[A-Za-z0-9_./-]+$' -or $rel -match '(^|/)\.\.(/|$)'){continue}
    # Initial local PC already holds inherited teacher shards; don't redownload original 19 GB.
    if($rel -like 'models/NOX_PRIME_9B_INHERITED/*'){continue}
    if($rel -like 'models/NOX_9B_UNIFIED_WRITING/*'){continue}
    $local=Join-Path $Root ($rel.Replace('/','\'))
    $parent=Split-Path -Parent $local
    New-Item -Type Directory -Force -Path $parent|Out-Null
    $count++
    try {
      $remoteMetadata=Remote ("python3 "+$remoteAgent+" hash --path '"+$rel+"'")|ConvertFrom-Json
      $expected=[string]$remoteMetadata.sha256
      $ok=$false
      if((Test-Path -LiteralPath $local) -and (Get-Item -LiteralPath $local).Length -eq [long]$remoteMetadata.bytes){
        $ok=(((Get-FileHash -LiteralPath $local -Algorithm SHA256).Hash.ToLowerInvariant()) -eq $expected)
      }
      if(-not $ok){
        $tmp=$local+'.noxpart'
        $source='root@'+$HostName+':/workspace/nox/'+$rel
        & $Scp -q -o BatchMode=yes -o ConnectTimeout=12 -i $Identity -P $Port $source $tmp
        if($LASTEXITCODE -ne 0){throw ('SCP_TRANSFER_FAILED '+$rel)}
        $actual=(Get-FileHash -LiteralPath $tmp -Algorithm SHA256).Hash.ToLowerInvariant()
        if($actual -ne $expected){throw ('SHA256_MISMATCH '+$rel)}
        Move-Item -LiteralPath $tmp -Destination $local -Force
      }
      # Confirm file stayed unchanged on RunPod during transfer.
      $after=Remote ("python3 "+$remoteAgent+" hash --path '"+$rel+"'")|ConvertFrom-Json
      if($after.sha256 -ne $expected -or [long]$after.bytes -ne [long]$remoteMetadata.bytes){
        throw ('CHANGED_DURING_BACKUP '+$rel)
      }
      $verified++;$bytes += [long]$after.bytes
      Log ("VERIFIED "+$rel+" "+$expected)
      # Nothing under checkpoints/models/memory can be deleted by this policy.
      if($rel -match '^logs/[A-Za-z0-9_.-]+\.(log\.\d+|log\.gz|old\.log|bak)$'){
        try {
          $v=Remote ("python3 "+$remoteAgent+" prune --path '"+$rel+"' --sha256 '"+$expected+"'")
          if($v -match '"deleted"'){$pruned++;Log ("REMOTE_ROTATED_LOG_PRUNED "+$rel)}
        } catch {Log ("PRUNE_SKIPPED "+$rel+" "+$_.Exception.Message)}
      }
    } catch {$failed++;Log ("BACKUP_ERROR "+$rel+" "+$_.Exception.Message)}
  }
  Log ("BACKUP_ROUND_FINISHED scanned=$count verified=$verified failures=$failed bytes_verified=$bytes rotated_logs_pruned=$pruned")
  $clean=Remote ('python3 '+$remoteAgent+' cleanup-cache')
  Log ("SAFE_CACHE_CLEANUP "+$clean)
  $df=Remote "df -h /workspace | tail -n 1"
  Log ("WORKSPACE_DISK "+$df)
  $download='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/a7ab4aa15071bb2700517e84b3fdb9ecd9c37e5c/nox_runpod/stage0/start_verified_qwen35_27b_download.sh'
  # Safe idempotent: if disk guard does not pass, download aborts and NOX training is preserved.
  $res=Remote ("curl -fLsS '"+$download+"' | bash")
  Log ("TEACHER_QUEUE "+$res)
  $dispatcher='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/54c49c688d7b34ebcf1b957cd149e40f4203ce2c/nox_runpod/stage0/nox_teacher_27b_dispatcher.py'
  $start=("mkdir -p /workspace/nox/tools /workspace/nox/logs; "+
    "curl -fLsS '"+$dispatcher+"' -o /workspace/nox/tools/nox_teacher_27b_dispatcher.py.new && "+
    "python3 -m py_compile /workspace/nox/tools/nox_teacher_27b_dispatcher.py.new && "+
    "mv -f /workspace/nox/tools/nox_teacher_27b_dispatcher.py.new /workspace/nox/tools/nox_teacher_27b_dispatcher.py && "+
    "if pgrep -f '[p]ython.*nox_teacher_27b_dispatcher.py' >/dev/null; then echo NOX_TEACHER_DISPATCHER_ALREADY_RUNNING; "+
    "else nohup setsid /workspace/nox/prime9b-venv/bin/python -u /workspace/nox/tools/nox_teacher_27b_dispatcher.py "+
    "</dev/null >>/workspace/nox/logs/NOX_27B_TEACHER_DISPATCH.log 2>&1 & echo NOX_TEACHER_DISPATCHER_DETACHED; fi")
  $result=Remote $start
  Log ("DISPATCHER "+$result)
  Log 'NOX_SEQUENCE_END: knowledge dataset will only be generated when 27B is downloaded and GPU free; adapter merge NOT automatic'
} finally {
 if($locked){$mutex.ReleaseMutex()}
 $mutex.Dispose()
}
