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
 $params=@('-InstallDir',$dir,'-ExpectedExeSha',$sha,'-ExpectedReceiptSha',$rsha,'-ExpectedSourceSha',$source)
 function Check([string]$mode,[bool]$pass){
   $failed=$false
   try{ & $guard -Mode $mode @params 2>&1 | Out-Null }catch{ $failed=$true; Write-Host "B05_EXPECTED_OR_UNEXPECTED_HOLD mode=$mode reason=$($_.Exception.Message)" }
   if($pass -eq $failed){ throw "B05_TEST_UNEXPECTED_RESULT:$mode expected=$pass" }
 }
 Check 'PreInstall' $true
 New-Item -ItemType Directory -Force -Path $dir | Out-Null
 [IO.File]::WriteAllBytes((Join-Path $dir 'NOX.HELION.exe'),$bytes)
 [IO.File]::WriteAllBytes((Join-Path $dir 'BUILD_RECEIPT.json'),$rbytes)
 Check 'PostInstall' $true
 Check 'PreInstall' $false
 [IO.File]::WriteAllText((Join-Path $dir 'foreign.txt'),'FOREIGN')
 Check 'PostInstall' $false
 Remove-Item -LiteralPath (Join-Path $dir 'foreign.txt')
 [IO.File]::AppendAllText((Join-Path $dir 'NOX.HELION.exe'),'TAMPER')
 Check 'PostInstall' $false
 [IO.File]::WriteAllBytes((Join-Path $dir 'NOX.HELION.exe'),$bytes)
 [IO.File]::WriteAllText((Join-Path $dir 'Uninstall.exe'),'TEST_FIXTURE')
 Check 'PreUninstall' $true
 [IO.File]::WriteAllText((Join-Path $dir 'owner.sqlite3'),'FOREIGN_OWNER_DATA')
 Check 'PreUninstall' $false
 if(-not (Test-Path -LiteralPath (Join-Path $dir 'owner.sqlite3'))){ throw 'B05_TEST_LOST_FOREIGN_FILE' }
 Write-Host 'B05_GUARD_7_CASES_PASS_SOURCE_ONLY_RELEASE_HOLD'
}finally{
 $env:LOCALAPPDATA=$original
 if(Test-Path -LiteralPath $scratch){ Remove-Item -LiteralPath $scratch -Force -Recurse }
}
