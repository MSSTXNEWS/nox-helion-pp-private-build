# Disposable Windows runner fixture, NOT a Qwen or release test.
$ErrorActionPreference='Stop'
$guard=Join-Path $PSScriptRoot 'NoLossGuard.ps1'
$original=$env:LOCALAPPDATA
$scratch=Join-Path ([IO.Path]::GetTempPath()) ('b05-'+[Guid]::NewGuid().ToString('N'))
$env:LOCALAPPDATA=Join-Path $scratch 'AppData'
try{
 New-Item -Path $env:LOCALAPPDATA -ItemType Directory -Force | Out-Null
 $bytes=[Text.Encoding]::UTF8.GetBytes('CI_ONLY_NOT_A_NOX_EXE')
 $sha=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($bytes)).ToLowerInvariant()
 $source=('a'*40)
 $dir=Join-Path $env:LOCALAPPDATA "Programs\NOX-HELION-R8\$sha"
 $json=(@{schema='NOX_R8_NATIVE_SINGLE_EXE_V1';source_git_sha=$source;exe_sha256=$sha;accepted_full_release=$false} | ConvertTo-Json -Compress)
 $rbytes=[Text.Encoding]::UTF8.GetBytes($json)
 $rsha=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($rbytes)).ToLowerInvariant()
 $payload=Join-Path $scratch 'staged-payload'
 New-Item -ItemType Directory -Force -Path $payload | Out-Null
 [IO.File]::WriteAllBytes((Join-Path $payload 'NOX.HELION.exe'),$bytes)
 [IO.File]::WriteAllBytes((Join-Path $payload 'BUILD_RECEIPT.json'),$rbytes)
 $invokeParams=@{InstallDir=$dir;ExpectedExeSha=$sha;ExpectedReceiptSha=$rsha;ExpectedSourceSha=$source;PayloadDir=$payload}
 function Check([string]$mode,[bool]$pass){
   $failed=$false
   try{ & $guard -Mode $mode @invokeParams 2>&1 | Out-Null }catch{ $failed=$true; Write-Host "B05_EXPECTED_OR_UNEXPECTED_HOLD mode=$mode reason=$($_.Exception.Message)" }
   if($pass -eq $failed){ throw "B05_TEST_UNEXPECTED_RESULT:$mode expected=$pass" }
 }
 Check 'PreInstall' $true
 # Valid checksum, invalid receipt schema: reject before creating target.
 $badJson=[Text.Encoding]::UTF8.GetBytes('{ "schema": "NOT_NOX_R8", "source_git_sha": "'+$source+'", "exe_sha256": "'+$sha+'" }')
 $badSha=[Convert]::ToHexString([Security.Cryptography.SHA256]::HashData($badJson)).ToLowerInvariant()
 try {
   [IO.File]::WriteAllBytes((Join-Path $payload 'BUILD_RECEIPT.json'),$badJson)
   $invokeParams.ExpectedReceiptSha=$badSha
   Check 'PreInstall' $false
   if(Test-Path -LiteralPath $dir){ throw 'B05_INVALID_RECEIPT_CREATED_TARGET' }
 } finally {
   $invokeParams.ExpectedReceiptSha=$rsha
   [IO.File]::WriteAllBytes((Join-Path $payload 'BUILD_RECEIPT.json'),$rbytes)
 }
 try {
   [IO.File]::WriteAllText((Join-Path $payload 'NOX.HELION.exe'),'TAMPERED_STAGED_PAYLOAD')
   Check 'PreInstall' $false
   if(Test-Path -LiteralPath $dir){ throw 'B05_BAD_PAYLOAD_CREATED_TARGET' }
 } finally { [IO.File]::WriteAllBytes((Join-Path $payload 'NOX.HELION.exe'),$bytes) }
 Check 'PreInstall' $true
 # Pre-install must reject an extra owner file BEFORE moving the payload.
 $foreignPayload=Join-Path $payload 'owner.sqlite3'
 try {
   [IO.File]::WriteAllText($foreignPayload,'FOREIGN_MUST_NOT_MOVE')
   Check 'PreInstall' $false
   if(Test-Path -LiteralPath $dir){ throw 'B05_FOREIGN_PAYLOAD_CREATED_TARGET' }
   if([IO.File]::ReadAllText($foreignPayload) -cne 'FOREIGN_MUST_NOT_MOVE'){ throw 'B05_FOREIGN_PAYLOAD_MODIFIED' }
 } finally { Remove-Item -LiteralPath $foreignPayload -Force -ErrorAction SilentlyContinue }
 # A directory can also hide unrelated files under an otherwise valid pair.
 $foreignDir=Join-Path $payload 'extra-subdir'
 try {
   New-Item -ItemType Directory -Path $foreignDir | Out-Null
   Check 'PreInstall' $false
   if(Test-Path -LiteralPath $dir){ throw 'B05_FOREIGN_SUBDIR_CREATED_TARGET' }
 } finally { Remove-Item -LiteralPath $foreignDir -Force -Recurse -ErrorAction SilentlyContinue }
 Check 'PreInstall' $true
 New-Item -ItemType Directory -Force -Path $dir | Out-Null
 [IO.File]::WriteAllBytes((Join-Path $dir 'NOX.HELION.exe'),$bytes)
 [IO.File]::WriteAllBytes((Join-Path $dir 'BUILD_RECEIPT.json'),$rbytes)
 # No promoted install may PASS before an uninstaller has been staged.
 Check 'PostInstall' $false
 [IO.File]::WriteAllText((Join-Path $dir 'Uninstall.exe'),'TEST_FIXTURE')
 Check 'PostInstall' $true
 Check 'PreInstall' $false
 [IO.File]::WriteAllText((Join-Path $dir 'foreign.txt'),'FOREIGN')
 Check 'PostInstall' $false
 Remove-Item -LiteralPath (Join-Path $dir 'foreign.txt')
 [IO.File]::AppendAllText((Join-Path $dir 'NOX.HELION.exe'),'TAMPER')
 Check 'PostInstall' $false
 [IO.File]::WriteAllBytes((Join-Path $dir 'NOX.HELION.exe'),$bytes)
 Check 'PreUninstall' $true
 # An EXE with an active shared-read handle must HOLD before any uninstall deletion.
 $held=[IO.File]::Open((Join-Path $dir 'NOX.HELION.exe'),[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
 try { Check 'PreUninstall' $false } finally { $held.Dispose() }
 Check 'PreUninstall' $true
 # A held receipt must stop uninstall BEFORE NSIS deletes the EXE.
 $receipt=Join-Path $dir 'BUILD_RECEIPT.json'
 $heldReceipt=[IO.File]::Open($receipt,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
 try { Check 'PreUninstall' $false } finally { $heldReceipt.Dispose() }
 Check 'PreUninstall' $true
 # A read-only owned file could also cause a partial NSIS delete.
 try {
   [IO.File]::SetAttributes($receipt,[IO.FileAttributes]::ReadOnly)
   Check 'PreUninstall' $false
 } finally { [IO.File]::SetAttributes($receipt,[IO.FileAttributes]::Normal) }
 Check 'PreUninstall' $true
 [IO.File]::WriteAllText((Join-Path $dir 'owner.sqlite3'),'FOREIGN_OWNER_DATA')
 Check 'PreUninstall' $false
 if(-not (Test-Path -LiteralPath (Join-Path $dir 'owner.sqlite3'))){ throw 'B05_TEST_LOST_FOREIGN_FILE' }
 Write-Host 'B05_GUARD_18_CHECKS_PASS_FIXTURE_ONLY_RELEASE_HOLD'
}finally{
 $env:LOCALAPPDATA=$original
 if(Test-Path -LiteralPath $scratch){ Remove-Item -LiteralPath $scratch -Force -Recurse }
}
