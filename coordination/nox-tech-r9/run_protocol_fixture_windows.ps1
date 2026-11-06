param([Parameter(Mandatory=$true)][string]$Exe,
 [Parameter(Mandatory=$true)][string]$OutputRoot)
$ErrorActionPreference='Stop'
$exe=(Resolve-Path -LiteralPath $Exe).Path
$py=(Get-Command python.exe -ErrorAction Stop).Source
$server=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'ollama_protocol_fixture.py')).Path
$listener=Get-NetTCPConnection -LocalPort 11436 -State Listen -ErrorAction SilentlyContinue
if ($listener) { throw 'PORT_11436_OCCUPIED_NO_STOP_PERMITTED' }
$stdout=Join-Path $OutputRoot 'PROTOCOL_FIXTURE_STDOUT.log'
$stderr=Join-Path $OutputRoot 'PROTOCOL_FIXTURE_STDERR.log'
$fixture=Start-Process -FilePath $py -ArgumentList @('-u',('"'+$server+'"')) -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
try {
 $ready=$false
 for($i=0;$i -lt 50;$i++){
  $fixture.Refresh()
  if($fixture.HasExited){throw 'FIXTURE_EARLY_EXIT'}
  try{
   $tags=Invoke-RestMethod 'http://127.0.0.1:11436/api/tags' -TimeoutSec 2
   if(@($tags.models.name) -contains 'nox-qwen-clean:latest'){$ready=$true;break}
  }catch{Start-Sleep -Milliseconds 200}
 }
 if(!$ready){throw 'FIXTURE_NOT_READY'}
 $runId='NOX-PROTOCOL-FIXTURE-'+$env:GITHUB_RUN_ID
 $proc=Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe) -ArgumentList @('--nox-selftest','--nox-protocol-fixture',"--nox-runid=$runId") -PassThru
 try {
  Wait-Process -Id $proc.Id -Timeout 130 -ErrorAction Stop
  $proc.Refresh()
  $receipt=Join-Path $env:LOCALAPPDATA "NOX_HELION/native_selftest_$($proc.Id).json"
  if(!(Test-Path -LiteralPath $receipt -PathType Leaf)){throw 'PROTOCOL_RECEIPT_MISSING'}
  $o=Get-Content $receipt -Raw | ConvertFrom-Json
  $sha=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
  $checks=@('webview2_real_ui_route','sqlite_transaction_readback','real_ollama_model_registered','real_chat_from_webview_to_qwen_to_sqlite','real_webview_stop_cancel_no_partial_persistence')
  if($proc.ExitCode -ne 0 -or $o.schema -cne 'NOX_WPF_E2E_NATIVE_R5_V1' -or
     $o.runId -cne $runId -or $o.pid -ne $proc.Id -or
     $o.nativeProtocolAccepted -ne $true -or $o.nativeCoreAccepted -ne $false -or
     $o.providerEvidence -cne 'SYNTHETIC_LOOPBACK_FIXTURE' -or
     $o.fullV16Accepted -ne $false -or
     ![string]::Equals([string]$o.exeSha256,$sha,[System.StringComparison]::OrdinalIgnoreCase)){
     throw ('PROTOCOL_RECEIPT_REJECTED '+($o|ConvertTo-Json -Depth 6 -Compress))
  }
  foreach($key in $checks){if($o.checks.$key -cne 'PASS'){throw "PROTOCOL_CHECK_FAILED_$key"}}
  if(Test-Path (Join-Path $env:LOCALAPPDATA 'NOX_HELION/chat.sqlite3')){
   throw 'OWNER_DATABASE_MUST_NOT_BE_CREATED'
  }
  Copy-Item -LiteralPath $receipt -Destination (Join-Path $OutputRoot 'PROTOCOL_FIXTURE_RECEIPT.json') -Force
  $buildFile=Join-Path $OutputRoot 'TECH_BUILD_RECEIPT.json'
  $build=Get-Content $buildFile -Raw | ConvertFrom-Json
  $build|Add-Member -NotePropertyName synthetic_protocol_ipc_stop_sqlite -NotePropertyValue 'PASS' -Force
  $build|ConvertTo-Json -Depth 7|Set-Content $buildFile -Encoding UTF8
  Write-Host 'WPF_WEBVIEW2_STREAM_STOP_SQLITE_PROTOCOL_PASS (SYNTHETIC FIXTURE; REAL QWEN NOT TESTED)'
 } finally {
  $proc.Refresh()
  if(!$proc.HasExited){Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue}
 }
} finally {
 $fixture.Refresh()
 if(!$fixture.HasExited){Stop-Process -Id $fixture.Id -Force -ErrorAction SilentlyContinue}
}
