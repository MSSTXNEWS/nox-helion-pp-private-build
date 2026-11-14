$ErrorActionPreference='Stop'
$root=Join-Path ([IO.Path]::GetTempPath()) ('NOX-CLEANUP-'+[Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root -Force | Out-Null
try {
 $master=Join-Path $root 'NOX_CURRENT.exe'
 $dup=Join-Path $root 'NOX_OLD_EXACT.exe'
 $different=Join-Path $root 'NOX_OLDER_UNIQUE.exe'
 $models=Join-Path $root 'models'
 New-Item -ItemType Directory -Path $models | Out-Null
 [IO.File]::WriteAllBytes($master,[byte[]](1,2,3,4,5))
 [IO.File]::WriteAllBytes($dup,[byte[]](1,2,3,4,5))
 [IO.File]::WriteAllBytes($different,[byte[]](1,2,3,4,6))
 [IO.File]::WriteAllBytes((Join-Path $models 'model.exe'),[byte[]](1,2,3,4,5))
 $sha=(Get-FileHash $master -Algorithm SHA256).Hash
 $script=Join-Path $PSScriptRoot 'Invoke-NoxExactDuplicateCleanup.ps1'
 $plan = & $script -Root $root -CanonicalFile $master -CanonicalSha256 $sha | ConvertFrom-Json
 if ($plan.mode -ne 'DRY_RUN' -or $plan.matched_exact_duplicates -ne 1 -or $plan.deleted -ne 0 -or !(Test-Path $dup)) { throw 'NOX_CLEANUP_DRY_RUN_FAILED' }
 $applied = & $script -Root $root -CanonicalFile $master -CanonicalSha256 $sha -Apply | ConvertFrom-Json
 if ($applied.deleted -ne 1 -or (Test-Path $dup) -or !(Test-Path $master) -or
     !(Test-Path $different) -or !(Test-Path (Join-Path $models 'model.exe'))) { throw 'NOX_CLEANUP_NOLOSS_FAILED' }
 $bad=('0'*64)
 $rejected=$false
 try { & $script -Root $root -CanonicalFile $master -CanonicalSha256 $bad -Apply | Out-Null } catch { $rejected=$true }
 if (!$rejected) { throw 'NOX_CLEANUP_HASH_GUARD_FAILED' }
 Write-Host 'NOX_EXACT_DUPLICATE_NOLOSS_PASS 3/3'
} finally { Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue }
