# NOX HELION V16 / GitLab Free Windows 2022 single-owner diagnostic builder.
# Replays the existing pinned four Azure PowerShell stages with no second packager.
# This is NOT a Windows E07 release or a generic security bypass.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Require-Exit([string]$name) {
    if ($LASTEXITCODE -ne 0) { throw "GITLAB_EXEC_FAILED:${name}:$LASTEXITCODE" }
}
function Find-Python31210 {
    $commands = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        try {
            $candidate = (& py -3.12 -c 'import sys; print(sys.executable)') | Select-Object -Last 1
            if ($LASTEXITCODE -eq 0 -and $candidate) { $commands += [string]$candidate }
        } catch {}
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $commands += (Get-Command python).Source
    }
    $commands += @('C:\Python312\python.exe', 'C:\Program Files\Python312\python.exe')
    foreach ($candidate in $commands | Select-Object -Unique) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        try {
            & $candidate -c 'import sys; assert sys.version_info[:3] == (3, 12, 10)'
            if ($LASTEXITCODE -eq 0) { return $candidate }
        } catch {}
    }
    return $null
}

$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path
if (-not $env:CI_PROJECT_DIR -or
    [IO.Path]::GetFullPath($env:CI_PROJECT_DIR).TrimEnd('\') -ine
    [IO.Path]::GetFullPath($repo).TrimEnd('\')) {
    throw 'GITLAB_CHECKOUT_ROOT_MISMATCH'
}
if ($env:NOX_FROZEN_SOURCE_SHA -cnotmatch '^[0-9a-f]{40}
    $env:NOX_APPROVE_WINDOWS_BUILD -cne 'YES' -or
    $env:CI_PIPELINE_SOURCE -notin @('web','api')) {
    throw 'GITLAB_EXPLICIT_PRIVATE_MIGRATION_BRANCH_CONSENT_REQUIRED'
}
Set-Location -LiteralPath $repo
if ($env:CI_COMMIT_SHA -cnotmatch '^[0-9a-f]{40}$' -or
    $env:CI_PIPELINE_ID -notmatch '^[0-9]+$') {
    throw 'GITLAB_PINNED_SHA_OR_RUNID_MISSING'
}
$head=(& git -C $repo rev-parse HEAD | Out-String).Trim().ToLowerInvariant()
Require-Exit 'GIT_HEAD'
if ($head -cne $env:CI_COMMIT_SHA.ToLowerInvariant() -or
    $head -cne $env:NOX_FROZEN_SOURCE_SHA.ToLowerInvariant()) {
    throw 'GITLAB_FROZEN_SOURCE_SHA_MISMATCH'
}
# GitLab protected file-type CI variable is a separately produced T08/T10 seal.
$receiptFile=$env:NOX_T10_SOURCE_READY_RECEIPT_FILE
if ([string]::IsNullOrWhiteSpace($receiptFile) -or
    -not (Test-Path -LiteralPath $receiptFile -PathType Leaf)) {
    throw 'GITLAB_T10_SOURCE_READY_RECEIPT_REQUIRED'
}
$item=Get-Item -LiteralPath $receiptFile -Force
if (($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
    $item.Length -lt 2 -or $item.Length -gt 65536) {
    throw 'GITLAB_T10_RECEIPT_NOT_BOUNDED_REGULAR_FILE'
}
$claimedDigest=$env:NOX_T10_RECEIPT_SHA256
if ($claimedDigest -cnotmatch '^[0-9a-f]{64}

$logroot=Join-Path $repo 'work/gitlab-artifacts'
$destination=Join-Path $logroot 'nox-v16-diagnostic'
$staging=Join-Path $repo 'work/gitlab-tmp'
New-Item -ItemType Directory -Path $logroot,$staging -Force | Out-Null
$report=Join-Path $logroot 'GITLAB_NOX_WINDOWS_RUN_RECEIPT.json'
$started=[DateTime]::UtcNow.ToString('o')
$state='HOLD'
$reason='UNVERIFIED'
$blocksCompleted=0
try {
    # GitLab source admission before optional network installs or costly Windows builds.
    # A release BuildID must not be derived from a malformed/repeated E07 script.
    $handoff=Join-Path $repo 'coordination/e06/Emit-E07ImmutableHandoff.ps1'
    if (-not (Test-Path -LiteralPath $handoff -PathType Leaf)) {
        throw 'GITLAB_E07_HANDOFF_SOURCE_MISSING'
    }
    $parseTokens=$null
    $parseErrors=$null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $handoff,[ref]$parseTokens,[ref]$parseErrors) | Out-Null
    if ($parseErrors.Count -ne 0) { throw 'GITLAB_E07_HANDOFF_POWERSHELL_SYNTAX_HOLD' }
    $handoffText=Get-Content -LiteralPath $handoff -Raw -Encoding UTF8
    if ([regex]::Matches($handoffText,'Write-Host "E07_BUILDID_SEALED').Count -ne 1 -or
        [regex]::Matches($handoffText,'foreach \(\$expected in @\(\$source.parts\)\)').Count -ne 1 -or
        -not $handoffText.Contains('([string]$matching[0].sha256).ToLowerInvariant() -cne ([string]$expected.sha256).ToLowerInvariant()') -or
        -not $handoffText.Contains('([string]$matching[0].gitBlobSha1).ToLowerInvariant() -cne ([string]$expected.git_blob_sha1).ToLowerInvariant()') -or
        -not $handoffText.Contains('release_accepted=$false')) {
        throw 'GITLAB_E07_SINGLE_SEAL_PART_PARITY_HOLD'
    }
    Write-Host 'GITLAB_E07_SOURCE_PREFLIGHT_PASS_NOT_NATIVE_ACCEPTANCE'
    # The GitLab hosted runner has Chocolatey; own runners may install prerequisites
    # themselves. No network credential or token is printed or persisted.
    $python=Find-Python31210
    if (-not $python) {
        if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
            throw 'GITLAB_PYTHON_3_12_10_REQUIRED_NO_INSTALLER'
        }
        & choco install python312 --version=3.12.10 --yes --no-progress --limit-output
        Require-Exit 'PYTHON31210_INSTALL'
        $python=Find-Python31210
    }
    if (-not $python) { throw 'GITLAB_EXACT_PYTHON_3_12_10_MISSING' }
    $env:PATH=(Split-Path -Parent $python) + ';' + $env:PATH
    & python -c 'import sys; assert sys.version_info[:3] == (3,12,10)'
    Require-Exit 'PYTHON_VERSION_RECHECK'
    & python -m unittest discover -s tests/e06 -p 'test_gitlab_free_source_gate.py' -v
    Require-Exit 'GITLAB_MIGRATION_SOURCE_GATE'

    $sdk=@()
    if (Get-Command dotnet -ErrorAction SilentlyContinue) {
        try { $sdk=@(& dotnet --list-sdks 2>$null) } catch { $sdk=@() }
    }
    if (-not @($sdk | Where-Object { $_ -match '^8\.' }).Count) {
        if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
            throw 'GITLAB_DOTNET8_REQUIRED_NO_INSTALLER'
        }
        & choco install dotnet-8.0-sdk --yes --no-progress --limit-output
        Require-Exit 'DOTNET8_INSTALL'
        $env:PATH=(Join-Path $env:ProgramFiles 'dotnet') + ';' + $env:PATH
    }
    $sdk=@(& dotnet --list-sdks)
    Require-Exit 'DOTNET_SDK'
    if (-not @($sdk | Where-Object { $_ -match '^8\.' }).Count) {
        throw 'GITLAB_DOTNET8_SDK_MISSING'
    }
    if (-not (Get-Command makensis -ErrorAction SilentlyContinue) -and
        -not (Test-Path 'C:\Program Files (x86)\NSIS\makensis.exe')) {
        if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
            throw 'GITLAB_NSIS_REQUIRED_NO_INSTALLER'
        }
        & choco install nsis --yes --no-progress --limit-output
        Require-Exit 'NSIS_INSTALL'
    }
    $env:GITHUB_SHA=$head
    $env:GITHUB_RUN_ID='GITLAB-' + $env:CI_PIPELINE_ID

    $azure=Join-Path $repo 'azure-pipelines-nox-v16.yml'
    if (-not (Test-Path -LiteralPath $azure -PathType Leaf)) {
        throw 'GITLAB_CANONICAL_AZURE_SOURCE_MISSING'
    }
    $lines=[IO.File]::ReadAllLines($azure)
    $blocks=[Collections.Generic.List[string]]::new()
    $current=[Collections.Generic.List[string]]::new()
    $inside=$false
    foreach ($line in $lines) {
        if ($line -ceq '  - pwsh: |') {
            if ($inside) { throw 'GITLAB_AZURE_NESTED_STAGE' }
            $inside=$true
            $current.Clear()
            continue
        }
        if (-not $inside) { continue }
        if ($line.StartsWith('      ')) {
            $current.Add($line.Substring(6))
        } elseif ($line.Trim().Length -eq 0) {
            $current.Add('')
        } else {
            $blocks.Add(($current -join [Environment]::NewLine))
            $current.Clear()
            $inside=$false
        }
    }
    if ($inside) { $blocks.Add(($current -join [Environment]::NewLine)) }
    if ($blocks.Count -ne 4) { throw "GITLAB_EXPECTED_FOUR_CANONICAL_STAGES:$($blocks.Count)" }
    $required=@(
        'verify_original_729_source.py',
        'private_build.ps1',
        'build_onehost_installer.ps1',
        'PUBLISHED_PRIVATE_PAYLOAD_SHA256.json'
    )
    for ($i=0; $i -lt 4; $i++) {
        if (-not $blocks[$i].Contains($required[$i])) {
            throw "GITLAB_CANONICAL_STAGE_OWNER_DRIFT:$i"
        }
    }
    # The four original stages are intentionally executed as separate pwsh
    # processes exactly as Azure does: no cross-stage PowerShell local leakage.
    $replace=[ordered]@{
        '$(Build.SourceVersion)'=$head
        '$(Build.BuildId)'=$env:CI_PIPELINE_ID
        '$(Agent.TempDirectory)'=$staging
        '$(Build.ArtifactStagingDirectory)'=$logroot
    }
    $shell=Get-Command pwsh -ErrorAction SilentlyContinue
    if (-not $shell -and (Get-Command choco -ErrorAction SilentlyContinue)) {
        & choco install powershell-core --yes --no-progress --limit-output
        Require-Exit 'POWERSHELL7_INSTALL'
        $env:PATH=(Join-Path $env:ProgramFiles 'PowerShell\7') + ';' + $env:PATH
        $shell=Get-Command pwsh -ErrorAction SilentlyContinue
    }
    if (-not $shell) { throw 'GITLAB_POWERSHELL7_REQUIRED' }
    for ($i=0; $i -lt $blocks.Count; $i++) {
        $code=$blocks[$i]
        foreach ($token in $replace.Keys) { $code=$code.Replace($token,$replace[$token]) }
        # No Azure macro syntax may survive, and no script is evaluated inline.
        if ([regex]::IsMatch($code, '\$\([A-Za-z][A-Za-z0-9.]+\)')) {
            throw "GITLAB_UNMAPPED_AZURE_MACRO:$i"
        }
        $stage=Join-Path $staging ("stage-{0}.ps1" -f $i)
        [IO.File]::WriteAllText($stage,$code,[Text.UTF8Encoding]::new($false))
        Write-Host "GITLAB_CANONICAL_STAGE_START $i SOURCE=$head"
        & $shell.Source -NoProfile -NonInteractive -File $stage
        Require-Exit ("CANONICAL_STAGE_"+$i)
        $blocksCompleted++
        Write-Host "GITLAB_CANONICAL_STAGE_PASS $i"
    }
    $e07=Join-Path $repo 'work/e06/azure-onehost-diagnostic/E07_BUILT_HANDOFF.json'
    if (-not (Test-Path -LiteralPath $e07 -PathType Leaf)) {
        throw 'GITLAB_E07_BUILT_RECEIPT_MISSING'
    }
    $built=Get-Content -LiteralPath $e07 -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($built.phase -cne 'BUILT' -or $built.release_accepted -ne $false -or
        $built.source_commit_sha1 -cne $head) {
        throw 'GITLAB_E07_BUILT_SHA_OR_SOURCE_DRIFT'
    }
    $state='BUILT_DIAGNOSTIC_NOT_E07_RELEASE'
    $reason='E07_INSTALLED_E2E_NOT_RUN'
} catch {
    $state='HOLD'
    $reason=$_.Exception.Message
    Write-Host ("GITLAB_DIAGNOSTIC_HOLD " + $reason)
    throw
} finally {
    $receipt=[ordered]@{
        schema='NOX_V16_GITLAB_FREE_WINDOWS_RUN_V1'
        original_repository='MSSTXNEWS/nox-helion-pp-private-build'
        source_git_sha=$head
        source_branch=$env:CI_COMMIT_REF_NAME
        gitlab_pipeline_id=$env:CI_PIPELINE_ID
        start_utc=$started
        end_utc=[DateTime]::UtcNow.ToString('o')
        canonical_azure_stages_completed=$blocksCompleted
        state=$state
        reason=$reason
        independent_e07_installed_cases=0
        release_accepted=$false
    }
    [IO.File]::WriteAllText($report,($receipt | ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
}
 -or
    $env:NOX_FROZEN_SOURCE_REF -cnotmatch '^[A-Za-z0-9._/-]{3,128}
    $env:NOX_APPROVE_WINDOWS_BUILD -cne 'YES' -or
    $env:CI_PIPELINE_SOURCE -notin @('web','api')) {
    throw 'GITLAB_EXPLICIT_PRIVATE_MIGRATION_BRANCH_CONSENT_REQUIRED'
}
Set-Location -LiteralPath $repo
if ($env:CI_COMMIT_SHA -cnotmatch '^[0-9a-f]{40}$' -or
    $env:CI_PIPELINE_ID -notmatch '^[0-9]+$') {
    throw 'GITLAB_PINNED_SHA_OR_RUNID_MISSING'
}
$head=(& git -C $repo rev-parse HEAD | Out-String).Trim().ToLowerInvariant()
Require-Exit 'GIT_HEAD'
if ($head -cne $env:CI_COMMIT_SHA.ToLowerInvariant()) { throw 'GITLAB_CHECKOUT_SHA_DRIFT' }

$logroot=Join-Path $repo 'work/gitlab-artifacts'
$destination=Join-Path $logroot 'nox-v16-diagnostic'
$staging=Join-Path $repo 'work/gitlab-tmp'
New-Item -ItemType Directory -Path $logroot,$staging -Force | Out-Null
$report=Join-Path $logroot 'GITLAB_NOX_WINDOWS_RUN_RECEIPT.json'
$started=[DateTime]::UtcNow.ToString('o')
$state='HOLD'
$reason='UNVERIFIED'
$blocksCompleted=0
try {
    # GitLab source admission before optional network installs or costly Windows builds.
    # A release BuildID must not be derived from a malformed/repeated E07 script.
    $handoff=Join-Path $repo 'coordination/e06/Emit-E07ImmutableHandoff.ps1'
    if (-not (Test-Path -LiteralPath $handoff -PathType Leaf)) {
        throw 'GITLAB_E07_HANDOFF_SOURCE_MISSING'
    }
    $parseTokens=$null
    $parseErrors=$null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $handoff,[ref]$parseTokens,[ref]$parseErrors) | Out-Null
    if ($parseErrors.Count -ne 0) { throw 'GITLAB_E07_HANDOFF_POWERSHELL_SYNTAX_HOLD' }
    $handoffText=Get-Content -LiteralPath $handoff -Raw -Encoding UTF8
    if ([regex]::Matches($handoffText,'Write-Host "E07_BUILDID_SEALED').Count -ne 1 -or
        [regex]::Matches($handoffText,'foreach \(\$expected in @\(\$source.parts\)\)').Count -ne 1 -or
        -not $handoffText.Contains('([string]$matching[0].sha256).ToLowerInvariant() -cne ([string]$expected.sha256).ToLowerInvariant()') -or
        -not $handoffText.Contains('([string]$matching[0].gitBlobSha1).ToLowerInvariant() -cne ([string]$expected.git_blob_sha1).ToLowerInvariant()') -or
        -not $handoffText.Contains('release_accepted=$false')) {
        throw 'GITLAB_E07_SINGLE_SEAL_PART_PARITY_HOLD'
    }
    Write-Host 'GITLAB_E07_SOURCE_PREFLIGHT_PASS_NOT_NATIVE_ACCEPTANCE'
    # The GitLab hosted runner has Chocolatey; own runners may install prerequisites
    # themselves. No network credential or token is printed or persisted.
    $python=Find-Python31210
    if (-not $python) {
        if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
            throw 'GITLAB_PYTHON_3_12_10_REQUIRED_NO_INSTALLER'
        }
        & choco install python312 --version=3.12.10 --yes --no-progress --limit-output
        Require-Exit 'PYTHON31210_INSTALL'
        $python=Find-Python31210
    }
    if (-not $python) { throw 'GITLAB_EXACT_PYTHON_3_12_10_MISSING' }
    $env:PATH=(Split-Path -Parent $python) + ';' + $env:PATH
    & python -c 'import sys; assert sys.version_info[:3] == (3,12,10)'
    Require-Exit 'PYTHON_VERSION_RECHECK'
    & python -m unittest discover -s tests/e06 -p 'test_gitlab_free_source_gate.py' -v
    Require-Exit 'GITLAB_MIGRATION_SOURCE_GATE'

    $sdk=@()
    if (Get-Command dotnet -ErrorAction SilentlyContinue) {
        try { $sdk=@(& dotnet --list-sdks 2>$null) } catch { $sdk=@() }
    }
    if (-not @($sdk | Where-Object { $_ -match '^8\.' }).Count) {
        if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
            throw 'GITLAB_DOTNET8_REQUIRED_NO_INSTALLER'
        }
        & choco install dotnet-8.0-sdk --yes --no-progress --limit-output
        Require-Exit 'DOTNET8_INSTALL'
        $env:PATH=(Join-Path $env:ProgramFiles 'dotnet') + ';' + $env:PATH
    }
    $sdk=@(& dotnet --list-sdks)
    Require-Exit 'DOTNET_SDK'
    if (-not @($sdk | Where-Object { $_ -match '^8\.' }).Count) {
        throw 'GITLAB_DOTNET8_SDK_MISSING'
    }
    if (-not (Get-Command makensis -ErrorAction SilentlyContinue) -and
        -not (Test-Path 'C:\Program Files (x86)\NSIS\makensis.exe')) {
        if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
            throw 'GITLAB_NSIS_REQUIRED_NO_INSTALLER'
        }
        & choco install nsis --yes --no-progress --limit-output
        Require-Exit 'NSIS_INSTALL'
    }
    $env:GITHUB_SHA=$head
    $env:GITHUB_RUN_ID='GITLAB-' + $env:CI_PIPELINE_ID

    $azure=Join-Path $repo 'azure-pipelines-nox-v16.yml'
    if (-not (Test-Path -LiteralPath $azure -PathType Leaf)) {
        throw 'GITLAB_CANONICAL_AZURE_SOURCE_MISSING'
    }
    $lines=[IO.File]::ReadAllLines($azure)
    $blocks=[Collections.Generic.List[string]]::new()
    $current=[Collections.Generic.List[string]]::new()
    $inside=$false
    foreach ($line in $lines) {
        if ($line -ceq '  - pwsh: |') {
            if ($inside) { throw 'GITLAB_AZURE_NESTED_STAGE' }
            $inside=$true
            $current.Clear()
            continue
        }
        if (-not $inside) { continue }
        if ($line.StartsWith('      ')) {
            $current.Add($line.Substring(6))
        } elseif ($line.Trim().Length -eq 0) {
            $current.Add('')
        } else {
            $blocks.Add(($current -join [Environment]::NewLine))
            $current.Clear()
            $inside=$false
        }
    }
    if ($inside) { $blocks.Add(($current -join [Environment]::NewLine)) }
    if ($blocks.Count -ne 4) { throw "GITLAB_EXPECTED_FOUR_CANONICAL_STAGES:$($blocks.Count)" }
    $required=@(
        'verify_original_729_source.py',
        'private_build.ps1',
        'build_onehost_installer.ps1',
        'PUBLISHED_PRIVATE_PAYLOAD_SHA256.json'
    )
    for ($i=0; $i -lt 4; $i++) {
        if (-not $blocks[$i].Contains($required[$i])) {
            throw "GITLAB_CANONICAL_STAGE_OWNER_DRIFT:$i"
        }
    }
    # The four original stages are intentionally executed as separate pwsh
    # processes exactly as Azure does: no cross-stage PowerShell local leakage.
    $replace=[ordered]@{
        '$(Build.SourceVersion)'=$head
        '$(Build.BuildId)'=$env:CI_PIPELINE_ID
        '$(Agent.TempDirectory)'=$staging
        '$(Build.ArtifactStagingDirectory)'=$logroot
    }
    $shell=Get-Command pwsh -ErrorAction SilentlyContinue
    if (-not $shell -and (Get-Command choco -ErrorAction SilentlyContinue)) {
        & choco install powershell-core --yes --no-progress --limit-output
        Require-Exit 'POWERSHELL7_INSTALL'
        $env:PATH=(Join-Path $env:ProgramFiles 'PowerShell\7') + ';' + $env:PATH
        $shell=Get-Command pwsh -ErrorAction SilentlyContinue
    }
    if (-not $shell) { throw 'GITLAB_POWERSHELL7_REQUIRED' }
    for ($i=0; $i -lt $blocks.Count; $i++) {
        $code=$blocks[$i]
        foreach ($token in $replace.Keys) { $code=$code.Replace($token,$replace[$token]) }
        # No Azure macro syntax may survive, and no script is evaluated inline.
        if ([regex]::IsMatch($code, '\$\([A-Za-z][A-Za-z0-9.]+\)')) {
            throw "GITLAB_UNMAPPED_AZURE_MACRO:$i"
        }
        $stage=Join-Path $staging ("stage-{0}.ps1" -f $i)
        [IO.File]::WriteAllText($stage,$code,[Text.UTF8Encoding]::new($false))
        Write-Host "GITLAB_CANONICAL_STAGE_START $i SOURCE=$head"
        & $shell.Source -NoProfile -NonInteractive -File $stage
        Require-Exit ("CANONICAL_STAGE_"+$i)
        $blocksCompleted++
        Write-Host "GITLAB_CANONICAL_STAGE_PASS $i"
    }
    $e07=Join-Path $repo 'work/e06/azure-onehost-diagnostic/E07_BUILT_HANDOFF.json'
    if (-not (Test-Path -LiteralPath $e07 -PathType Leaf)) {
        throw 'GITLAB_E07_BUILT_RECEIPT_MISSING'
    }
    $built=Get-Content -LiteralPath $e07 -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($built.phase -cne 'BUILT' -or $built.release_accepted -ne $false -or
        $built.source_commit_sha1 -cne $head) {
        throw 'GITLAB_E07_BUILT_SHA_OR_SOURCE_DRIFT'
    }
    $state='BUILT_DIAGNOSTIC_NOT_E07_RELEASE'
    $reason='E07_INSTALLED_E2E_NOT_RUN'
} catch {
    $state='HOLD'
    $reason=$_.Exception.Message
    Write-Host ("GITLAB_DIAGNOSTIC_HOLD " + $reason)
    throw
} finally {
    $receipt=[ordered]@{
        schema='NOX_V16_GITLAB_FREE_WINDOWS_RUN_V1'
        original_repository='MSSTXNEWS/nox-helion-pp-private-build'
        source_git_sha=$head
        source_branch=$env:CI_COMMIT_REF_NAME
        gitlab_pipeline_id=$env:CI_PIPELINE_ID
        start_utc=$started
        end_utc=[DateTime]::UtcNow.ToString('o')
        canonical_azure_stages_completed=$blocksCompleted
        state=$state
        reason=$reason
        independent_e07_installed_cases=0
        release_accepted=$false
    }
    [IO.File]::WriteAllText($report,($receipt | ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
}
 -or
    $env:CI_COMMIT_REF_NAME -cne $env:NOX_FROZEN_SOURCE_REF -or
    $env:NOX_APPROVE_WINDOWS_BUILD -cne 'YES' -or
    $env:CI_PIPELINE_SOURCE -notin @('web','api')) {
    throw 'GITLAB_EXPLICIT_PRIVATE_MIGRATION_BRANCH_CONSENT_REQUIRED'
}
Set-Location -LiteralPath $repo
if ($env:CI_COMMIT_SHA -cnotmatch '^[0-9a-f]{40}$' -or
    $env:CI_PIPELINE_ID -notmatch '^[0-9]+$') {
    throw 'GITLAB_PINNED_SHA_OR_RUNID_MISSING'
}
$head=(& git -C $repo rev-parse HEAD | Out-String).Trim().ToLowerInvariant()
Require-Exit 'GIT_HEAD'
if ($head -cne $env:CI_COMMIT_SHA.ToLowerInvariant()) { throw 'GITLAB_CHECKOUT_SHA_DRIFT' }

$logroot=Join-Path $repo 'work/gitlab-artifacts'
$destination=Join-Path $logroot 'nox-v16-diagnostic'
$staging=Join-Path $repo 'work/gitlab-tmp'
New-Item -ItemType Directory -Path $logroot,$staging -Force | Out-Null
$report=Join-Path $logroot 'GITLAB_NOX_WINDOWS_RUN_RECEIPT.json'
$started=[DateTime]::UtcNow.ToString('o')
$state='HOLD'
$reason='UNVERIFIED'
$blocksCompleted=0
try {
    # GitLab source admission before optional network installs or costly Windows builds.
    # A release BuildID must not be derived from a malformed/repeated E07 script.
    $handoff=Join-Path $repo 'coordination/e06/Emit-E07ImmutableHandoff.ps1'
    if (-not (Test-Path -LiteralPath $handoff -PathType Leaf)) {
        throw 'GITLAB_E07_HANDOFF_SOURCE_MISSING'
    }
    $parseTokens=$null
    $parseErrors=$null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $handoff,[ref]$parseTokens,[ref]$parseErrors) | Out-Null
    if ($parseErrors.Count -ne 0) { throw 'GITLAB_E07_HANDOFF_POWERSHELL_SYNTAX_HOLD' }
    $handoffText=Get-Content -LiteralPath $handoff -Raw -Encoding UTF8
    if ([regex]::Matches($handoffText,'Write-Host "E07_BUILDID_SEALED').Count -ne 1 -or
        [regex]::Matches($handoffText,'foreach \(\$expected in @\(\$source.parts\)\)').Count -ne 1 -or
        -not $handoffText.Contains('([string]$matching[0].sha256).ToLowerInvariant() -cne ([string]$expected.sha256).ToLowerInvariant()') -or
        -not $handoffText.Contains('([string]$matching[0].gitBlobSha1).ToLowerInvariant() -cne ([string]$expected.git_blob_sha1).ToLowerInvariant()') -or
        -not $handoffText.Contains('release_accepted=$false')) {
        throw 'GITLAB_E07_SINGLE_SEAL_PART_PARITY_HOLD'
    }
    Write-Host 'GITLAB_E07_SOURCE_PREFLIGHT_PASS_NOT_NATIVE_ACCEPTANCE'
    # The GitLab hosted runner has Chocolatey; own runners may install prerequisites
    # themselves. No network credential or token is printed or persisted.
    $python=Find-Python31210
    if (-not $python) {
        if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
            throw 'GITLAB_PYTHON_3_12_10_REQUIRED_NO_INSTALLER'
        }
        & choco install python312 --version=3.12.10 --yes --no-progress --limit-output
        Require-Exit 'PYTHON31210_INSTALL'
        $python=Find-Python31210
    }
    if (-not $python) { throw 'GITLAB_EXACT_PYTHON_3_12_10_MISSING' }
    $env:PATH=(Split-Path -Parent $python) + ';' + $env:PATH
    & python -c 'import sys; assert sys.version_info[:3] == (3,12,10)'
    Require-Exit 'PYTHON_VERSION_RECHECK'
    & python -m unittest discover -s tests/e06 -p 'test_gitlab_free_source_gate.py' -v
    Require-Exit 'GITLAB_MIGRATION_SOURCE_GATE'

    $sdk=@()
    if (Get-Command dotnet -ErrorAction SilentlyContinue) {
        try { $sdk=@(& dotnet --list-sdks 2>$null) } catch { $sdk=@() }
    }
    if (-not @($sdk | Where-Object { $_ -match '^8\.' }).Count) {
        if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
            throw 'GITLAB_DOTNET8_REQUIRED_NO_INSTALLER'
        }
        & choco install dotnet-8.0-sdk --yes --no-progress --limit-output
        Require-Exit 'DOTNET8_INSTALL'
        $env:PATH=(Join-Path $env:ProgramFiles 'dotnet') + ';' + $env:PATH
    }
    $sdk=@(& dotnet --list-sdks)
    Require-Exit 'DOTNET_SDK'
    if (-not @($sdk | Where-Object { $_ -match '^8\.' }).Count) {
        throw 'GITLAB_DOTNET8_SDK_MISSING'
    }
    if (-not (Get-Command makensis -ErrorAction SilentlyContinue) -and
        -not (Test-Path 'C:\Program Files (x86)\NSIS\makensis.exe')) {
        if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
            throw 'GITLAB_NSIS_REQUIRED_NO_INSTALLER'
        }
        & choco install nsis --yes --no-progress --limit-output
        Require-Exit 'NSIS_INSTALL'
    }
    $env:GITHUB_SHA=$head
    $env:GITHUB_RUN_ID='GITLAB-' + $env:CI_PIPELINE_ID

    $azure=Join-Path $repo 'azure-pipelines-nox-v16.yml'
    if (-not (Test-Path -LiteralPath $azure -PathType Leaf)) {
        throw 'GITLAB_CANONICAL_AZURE_SOURCE_MISSING'
    }
    $lines=[IO.File]::ReadAllLines($azure)
    $blocks=[Collections.Generic.List[string]]::new()
    $current=[Collections.Generic.List[string]]::new()
    $inside=$false
    foreach ($line in $lines) {
        if ($line -ceq '  - pwsh: |') {
            if ($inside) { throw 'GITLAB_AZURE_NESTED_STAGE' }
            $inside=$true
            $current.Clear()
            continue
        }
        if (-not $inside) { continue }
        if ($line.StartsWith('      ')) {
            $current.Add($line.Substring(6))
        } elseif ($line.Trim().Length -eq 0) {
            $current.Add('')
        } else {
            $blocks.Add(($current -join [Environment]::NewLine))
            $current.Clear()
            $inside=$false
        }
    }
    if ($inside) { $blocks.Add(($current -join [Environment]::NewLine)) }
    if ($blocks.Count -ne 4) { throw "GITLAB_EXPECTED_FOUR_CANONICAL_STAGES:$($blocks.Count)" }
    $required=@(
        'verify_original_729_source.py',
        'private_build.ps1',
        'build_onehost_installer.ps1',
        'PUBLISHED_PRIVATE_PAYLOAD_SHA256.json'
    )
    for ($i=0; $i -lt 4; $i++) {
        if (-not $blocks[$i].Contains($required[$i])) {
            throw "GITLAB_CANONICAL_STAGE_OWNER_DRIFT:$i"
        }
    }
    # The four original stages are intentionally executed as separate pwsh
    # processes exactly as Azure does: no cross-stage PowerShell local leakage.
    $replace=[ordered]@{
        '$(Build.SourceVersion)'=$head
        '$(Build.BuildId)'=$env:CI_PIPELINE_ID
        '$(Agent.TempDirectory)'=$staging
        '$(Build.ArtifactStagingDirectory)'=$logroot
    }
    $shell=Get-Command pwsh -ErrorAction SilentlyContinue
    if (-not $shell -and (Get-Command choco -ErrorAction SilentlyContinue)) {
        & choco install powershell-core --yes --no-progress --limit-output
        Require-Exit 'POWERSHELL7_INSTALL'
        $env:PATH=(Join-Path $env:ProgramFiles 'PowerShell\7') + ';' + $env:PATH
        $shell=Get-Command pwsh -ErrorAction SilentlyContinue
    }
    if (-not $shell) { throw 'GITLAB_POWERSHELL7_REQUIRED' }
    for ($i=0; $i -lt $blocks.Count; $i++) {
        $code=$blocks[$i]
        foreach ($token in $replace.Keys) { $code=$code.Replace($token,$replace[$token]) }
        # No Azure macro syntax may survive, and no script is evaluated inline.
        if ([regex]::IsMatch($code, '\$\([A-Za-z][A-Za-z0-9.]+\)')) {
            throw "GITLAB_UNMAPPED_AZURE_MACRO:$i"
        }
        $stage=Join-Path $staging ("stage-{0}.ps1" -f $i)
        [IO.File]::WriteAllText($stage,$code,[Text.UTF8Encoding]::new($false))
        Write-Host "GITLAB_CANONICAL_STAGE_START $i SOURCE=$head"
        & $shell.Source -NoProfile -NonInteractive -File $stage
        Require-Exit ("CANONICAL_STAGE_"+$i)
        $blocksCompleted++
        Write-Host "GITLAB_CANONICAL_STAGE_PASS $i"
    }
    $e07=Join-Path $repo 'work/e06/azure-onehost-diagnostic/E07_BUILT_HANDOFF.json'
    if (-not (Test-Path -LiteralPath $e07 -PathType Leaf)) {
        throw 'GITLAB_E07_BUILT_RECEIPT_MISSING'
    }
    $built=Get-Content -LiteralPath $e07 -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($built.phase -cne 'BUILT' -or $built.release_accepted -ne $false -or
        $built.source_commit_sha1 -cne $head) {
        throw 'GITLAB_E07_BUILT_SHA_OR_SOURCE_DRIFT'
    }
    $state='BUILT_DIAGNOSTIC_NOT_E07_RELEASE'
    $reason='E07_INSTALLED_E2E_NOT_RUN'
} catch {
    $state='HOLD'
    $reason=$_.Exception.Message
    Write-Host ("GITLAB_DIAGNOSTIC_HOLD " + $reason)
    throw
} finally {
    $receipt=[ordered]@{
        schema='NOX_V16_GITLAB_FREE_WINDOWS_RUN_V1'
        original_repository='MSSTXNEWS/nox-helion-pp-private-build'
        source_git_sha=$head
        source_branch=$env:CI_COMMIT_REF_NAME
        gitlab_pipeline_id=$env:CI_PIPELINE_ID
        start_utc=$started
        end_utc=[DateTime]::UtcNow.ToString('o')
        canonical_azure_stages_completed=$blocksCompleted
        state=$state
        reason=$reason
        independent_e07_installed_cases=0
        release_accepted=$false
    }
    [IO.File]::WriteAllText($report,($receipt | ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
}
 -or
    (Get-FileHash -LiteralPath $receiptFile -Algorithm SHA256).Hash.ToLowerInvariant() -cne $claimedDigest) {
    throw 'GITLAB_T10_RECEIPT_SHA256_MISMATCH'
}
$accepted=Get-Content -LiteralPath $receiptFile -Raw -Encoding UTF8 | ConvertFrom-Json
$actualTree=(& git -C $repo rev-parse 'HEAD^{tree}' | Out-String).Trim().ToLowerInvariant()
Require-Exit 'GIT_TREE'
if ($accepted.source_head -cne $head -or $accepted.source_tree -cne $actualTree -or
    $accepted.status -cne 'SOURCE_READY' -or $accepted.independent_t08_accepted -ne $true -or
    $accepted.no_loss_verified -ne $true -or $accepted.t10_accepted -ne $true) {
    throw 'GITLAB_T08_T10_SAME_SHA_SOURCE_READY_REQUIRED'
}
Write-Host 'GITLAB_T08_T10_SOURCE_READY_PINNED'


$logroot=Join-Path $repo 'work/gitlab-artifacts'
$destination=Join-Path $logroot 'nox-v16-diagnostic'
$staging=Join-Path $repo 'work/gitlab-tmp'
New-Item -ItemType Directory -Path $logroot,$staging -Force | Out-Null
$report=Join-Path $logroot 'GITLAB_NOX_WINDOWS_RUN_RECEIPT.json'
$started=[DateTime]::UtcNow.ToString('o')
$state='HOLD'
$reason='UNVERIFIED'
$blocksCompleted=0
try {
    # GitLab source admission before optional network installs or costly Windows builds.
    # A release BuildID must not be derived from a malformed/repeated E07 script.
    $handoff=Join-Path $repo 'coordination/e06/Emit-E07ImmutableHandoff.ps1'
    if (-not (Test-Path -LiteralPath $handoff -PathType Leaf)) {
        throw 'GITLAB_E07_HANDOFF_SOURCE_MISSING'
    }
    $parseTokens=$null
    $parseErrors=$null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $handoff,[ref]$parseTokens,[ref]$parseErrors) | Out-Null
    if ($parseErrors.Count -ne 0) { throw 'GITLAB_E07_HANDOFF_POWERSHELL_SYNTAX_HOLD' }
    $handoffText=Get-Content -LiteralPath $handoff -Raw -Encoding UTF8
    if ([regex]::Matches($handoffText,'Write-Host "E07_BUILDID_SEALED').Count -ne 1 -or
        [regex]::Matches($handoffText,'foreach \(\$expected in @\(\$source.parts\)\)').Count -ne 1 -or
        -not $handoffText.Contains('([string]$matching[0].sha256).ToLowerInvariant() -cne ([string]$expected.sha256).ToLowerInvariant()') -or
        -not $handoffText.Contains('([string]$matching[0].gitBlobSha1).ToLowerInvariant() -cne ([string]$expected.git_blob_sha1).ToLowerInvariant()') -or
        -not $handoffText.Contains('release_accepted=$false')) {
        throw 'GITLAB_E07_SINGLE_SEAL_PART_PARITY_HOLD'
    }
    Write-Host 'GITLAB_E07_SOURCE_PREFLIGHT_PASS_NOT_NATIVE_ACCEPTANCE'
    # The GitLab hosted runner has Chocolatey; own runners may install prerequisites
    # themselves. No network credential or token is printed or persisted.
    $python=Find-Python31210
    if (-not $python) {
        if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
            throw 'GITLAB_PYTHON_3_12_10_REQUIRED_NO_INSTALLER'
        }
        & choco install python312 --version=3.12.10 --yes --no-progress --limit-output
        Require-Exit 'PYTHON31210_INSTALL'
        $python=Find-Python31210
    }
    if (-not $python) { throw 'GITLAB_EXACT_PYTHON_3_12_10_MISSING' }
    $env:PATH=(Split-Path -Parent $python) + ';' + $env:PATH
    & python -c 'import sys; assert sys.version_info[:3] == (3,12,10)'
    Require-Exit 'PYTHON_VERSION_RECHECK'
    & python -m unittest discover -s tests/e06 -p 'test_gitlab_free_source_gate.py' -v
    Require-Exit 'GITLAB_MIGRATION_SOURCE_GATE'

    $sdk=@()
    if (Get-Command dotnet -ErrorAction SilentlyContinue) {
        try { $sdk=@(& dotnet --list-sdks 2>$null) } catch { $sdk=@() }
    }
    if (-not @($sdk | Where-Object { $_ -match '^8\.' }).Count) {
        if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
            throw 'GITLAB_DOTNET8_REQUIRED_NO_INSTALLER'
        }
        & choco install dotnet-8.0-sdk --yes --no-progress --limit-output
        Require-Exit 'DOTNET8_INSTALL'
        $env:PATH=(Join-Path $env:ProgramFiles 'dotnet') + ';' + $env:PATH
    }
    $sdk=@(& dotnet --list-sdks)
    Require-Exit 'DOTNET_SDK'
    if (-not @($sdk | Where-Object { $_ -match '^8\.' }).Count) {
        throw 'GITLAB_DOTNET8_SDK_MISSING'
    }
    if (-not (Get-Command makensis -ErrorAction SilentlyContinue) -and
        -not (Test-Path 'C:\Program Files (x86)\NSIS\makensis.exe')) {
        if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
            throw 'GITLAB_NSIS_REQUIRED_NO_INSTALLER'
        }
        & choco install nsis --yes --no-progress --limit-output
        Require-Exit 'NSIS_INSTALL'
    }
    $env:GITHUB_SHA=$head
    $env:GITHUB_RUN_ID='GITLAB-' + $env:CI_PIPELINE_ID

    $azure=Join-Path $repo 'azure-pipelines-nox-v16.yml'
    if (-not (Test-Path -LiteralPath $azure -PathType Leaf)) {
        throw 'GITLAB_CANONICAL_AZURE_SOURCE_MISSING'
    }
    $lines=[IO.File]::ReadAllLines($azure)
    $blocks=[Collections.Generic.List[string]]::new()
    $current=[Collections.Generic.List[string]]::new()
    $inside=$false
    foreach ($line in $lines) {
        if ($line -ceq '  - pwsh: |') {
            if ($inside) { throw 'GITLAB_AZURE_NESTED_STAGE' }
            $inside=$true
            $current.Clear()
            continue
        }
        if (-not $inside) { continue }
        if ($line.StartsWith('      ')) {
            $current.Add($line.Substring(6))
        } elseif ($line.Trim().Length -eq 0) {
            $current.Add('')
        } else {
            $blocks.Add(($current -join [Environment]::NewLine))
            $current.Clear()
            $inside=$false
        }
    }
    if ($inside) { $blocks.Add(($current -join [Environment]::NewLine)) }
    if ($blocks.Count -ne 4) { throw "GITLAB_EXPECTED_FOUR_CANONICAL_STAGES:$($blocks.Count)" }
    $required=@(
        'verify_original_729_source.py',
        'private_build.ps1',
        'build_onehost_installer.ps1',
        'PUBLISHED_PRIVATE_PAYLOAD_SHA256.json'
    )
    for ($i=0; $i -lt 4; $i++) {
        if (-not $blocks[$i].Contains($required[$i])) {
            throw "GITLAB_CANONICAL_STAGE_OWNER_DRIFT:$i"
        }
    }
    # The four original stages are intentionally executed as separate pwsh
    # processes exactly as Azure does: no cross-stage PowerShell local leakage.
    $replace=[ordered]@{
        '$(Build.SourceVersion)'=$head
        '$(Build.BuildId)'=$env:CI_PIPELINE_ID
        '$(Agent.TempDirectory)'=$staging
        '$(Build.ArtifactStagingDirectory)'=$logroot
    }
    $shell=Get-Command pwsh -ErrorAction SilentlyContinue
    if (-not $shell -and (Get-Command choco -ErrorAction SilentlyContinue)) {
        & choco install powershell-core --yes --no-progress --limit-output
        Require-Exit 'POWERSHELL7_INSTALL'
        $env:PATH=(Join-Path $env:ProgramFiles 'PowerShell\7') + ';' + $env:PATH
        $shell=Get-Command pwsh -ErrorAction SilentlyContinue
    }
    if (-not $shell) { throw 'GITLAB_POWERSHELL7_REQUIRED' }
    for ($i=0; $i -lt $blocks.Count; $i++) {
        $code=$blocks[$i]
        foreach ($token in $replace.Keys) { $code=$code.Replace($token,$replace[$token]) }
        # No Azure macro syntax may survive, and no script is evaluated inline.
        if ([regex]::IsMatch($code, '\$\([A-Za-z][A-Za-z0-9.]+\)')) {
            throw "GITLAB_UNMAPPED_AZURE_MACRO:$i"
        }
        $stage=Join-Path $staging ("stage-{0}.ps1" -f $i)
        [IO.File]::WriteAllText($stage,$code,[Text.UTF8Encoding]::new($false))
        Write-Host "GITLAB_CANONICAL_STAGE_START $i SOURCE=$head"
        & $shell.Source -NoProfile -NonInteractive -File $stage
        Require-Exit ("CANONICAL_STAGE_"+$i)
        $blocksCompleted++
        Write-Host "GITLAB_CANONICAL_STAGE_PASS $i"
    }
    $e07=Join-Path $repo 'work/e06/azure-onehost-diagnostic/E07_BUILT_HANDOFF.json'
    if (-not (Test-Path -LiteralPath $e07 -PathType Leaf)) {
        throw 'GITLAB_E07_BUILT_RECEIPT_MISSING'
    }
    $built=Get-Content -LiteralPath $e07 -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($built.phase -cne 'BUILT' -or $built.release_accepted -ne $false -or
        $built.source_commit_sha1 -cne $head) {
        throw 'GITLAB_E07_BUILT_SHA_OR_SOURCE_DRIFT'
    }
    $state='BUILT_DIAGNOSTIC_NOT_E07_RELEASE'
    $reason='E07_INSTALLED_E2E_NOT_RUN'
} catch {
    $state='HOLD'
    $reason=$_.Exception.Message
    Write-Host ("GITLAB_DIAGNOSTIC_HOLD " + $reason)
    throw
} finally {
    $receipt=[ordered]@{
        schema='NOX_V16_GITLAB_FREE_WINDOWS_RUN_V1'
        original_repository='MSSTXNEWS/nox-helion-pp-private-build'
        source_git_sha=$head
        source_branch=$env:CI_COMMIT_REF_NAME
        gitlab_pipeline_id=$env:CI_PIPELINE_ID
        start_utc=$started
        end_utc=[DateTime]::UtcNow.ToString('o')
        canonical_azure_stages_completed=$blocksCompleted
        state=$state
        reason=$reason
        independent_e07_installed_cases=0
        release_accepted=$false
    }
    [IO.File]::WriteAllText($report,($receipt | ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
}
 -or
    $env:NOX_FROZEN_SOURCE_REF -cnotmatch '^[A-Za-z0-9._/-]{3,128}
    $env:NOX_APPROVE_WINDOWS_BUILD -cne 'YES' -or
    $env:CI_PIPELINE_SOURCE -notin @('web','api')) {
    throw 'GITLAB_EXPLICIT_PRIVATE_MIGRATION_BRANCH_CONSENT_REQUIRED'
}
Set-Location -LiteralPath $repo
if ($env:CI_COMMIT_SHA -cnotmatch '^[0-9a-f]{40}$' -or
    $env:CI_PIPELINE_ID -notmatch '^[0-9]+$') {
    throw 'GITLAB_PINNED_SHA_OR_RUNID_MISSING'
}
$head=(& git -C $repo rev-parse HEAD | Out-String).Trim().ToLowerInvariant()
Require-Exit 'GIT_HEAD'
if ($head -cne $env:CI_COMMIT_SHA.ToLowerInvariant()) { throw 'GITLAB_CHECKOUT_SHA_DRIFT' }

$logroot=Join-Path $repo 'work/gitlab-artifacts'
$destination=Join-Path $logroot 'nox-v16-diagnostic'
$staging=Join-Path $repo 'work/gitlab-tmp'
New-Item -ItemType Directory -Path $logroot,$staging -Force | Out-Null
$report=Join-Path $logroot 'GITLAB_NOX_WINDOWS_RUN_RECEIPT.json'
$started=[DateTime]::UtcNow.ToString('o')
$state='HOLD'
$reason='UNVERIFIED'
$blocksCompleted=0
try {
    # GitLab source admission before optional network installs or costly Windows builds.
    # A release BuildID must not be derived from a malformed/repeated E07 script.
    $handoff=Join-Path $repo 'coordination/e06/Emit-E07ImmutableHandoff.ps1'
    if (-not (Test-Path -LiteralPath $handoff -PathType Leaf)) {
        throw 'GITLAB_E07_HANDOFF_SOURCE_MISSING'
    }
    $parseTokens=$null
    $parseErrors=$null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $handoff,[ref]$parseTokens,[ref]$parseErrors) | Out-Null
    if ($parseErrors.Count -ne 0) { throw 'GITLAB_E07_HANDOFF_POWERSHELL_SYNTAX_HOLD' }
    $handoffText=Get-Content -LiteralPath $handoff -Raw -Encoding UTF8
    if ([regex]::Matches($handoffText,'Write-Host "E07_BUILDID_SEALED').Count -ne 1 -or
        [regex]::Matches($handoffText,'foreach \(\$expected in @\(\$source.parts\)\)').Count -ne 1 -or
        -not $handoffText.Contains('([string]$matching[0].sha256).ToLowerInvariant() -cne ([string]$expected.sha256).ToLowerInvariant()') -or
        -not $handoffText.Contains('([string]$matching[0].gitBlobSha1).ToLowerInvariant() -cne ([string]$expected.git_blob_sha1).ToLowerInvariant()') -or
        -not $handoffText.Contains('release_accepted=$false')) {
        throw 'GITLAB_E07_SINGLE_SEAL_PART_PARITY_HOLD'
    }
    Write-Host 'GITLAB_E07_SOURCE_PREFLIGHT_PASS_NOT_NATIVE_ACCEPTANCE'
    # The GitLab hosted runner has Chocolatey; own runners may install prerequisites
    # themselves. No network credential or token is printed or persisted.
    $python=Find-Python31210
    if (-not $python) {
        if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
            throw 'GITLAB_PYTHON_3_12_10_REQUIRED_NO_INSTALLER'
        }
        & choco install python312 --version=3.12.10 --yes --no-progress --limit-output
        Require-Exit 'PYTHON31210_INSTALL'
        $python=Find-Python31210
    }
    if (-not $python) { throw 'GITLAB_EXACT_PYTHON_3_12_10_MISSING' }
    $env:PATH=(Split-Path -Parent $python) + ';' + $env:PATH
    & python -c 'import sys; assert sys.version_info[:3] == (3,12,10)'
    Require-Exit 'PYTHON_VERSION_RECHECK'
    & python -m unittest discover -s tests/e06 -p 'test_gitlab_free_source_gate.py' -v
    Require-Exit 'GITLAB_MIGRATION_SOURCE_GATE'

    $sdk=@()
    if (Get-Command dotnet -ErrorAction SilentlyContinue) {
        try { $sdk=@(& dotnet --list-sdks 2>$null) } catch { $sdk=@() }
    }
    if (-not @($sdk | Where-Object { $_ -match '^8\.' }).Count) {
        if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
            throw 'GITLAB_DOTNET8_REQUIRED_NO_INSTALLER'
        }
        & choco install dotnet-8.0-sdk --yes --no-progress --limit-output
        Require-Exit 'DOTNET8_INSTALL'
        $env:PATH=(Join-Path $env:ProgramFiles 'dotnet') + ';' + $env:PATH
    }
    $sdk=@(& dotnet --list-sdks)
    Require-Exit 'DOTNET_SDK'
    if (-not @($sdk | Where-Object { $_ -match '^8\.' }).Count) {
        throw 'GITLAB_DOTNET8_SDK_MISSING'
    }
    if (-not (Get-Command makensis -ErrorAction SilentlyContinue) -and
        -not (Test-Path 'C:\Program Files (x86)\NSIS\makensis.exe')) {
        if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
            throw 'GITLAB_NSIS_REQUIRED_NO_INSTALLER'
        }
        & choco install nsis --yes --no-progress --limit-output
        Require-Exit 'NSIS_INSTALL'
    }
    $env:GITHUB_SHA=$head
    $env:GITHUB_RUN_ID='GITLAB-' + $env:CI_PIPELINE_ID

    $azure=Join-Path $repo 'azure-pipelines-nox-v16.yml'
    if (-not (Test-Path -LiteralPath $azure -PathType Leaf)) {
        throw 'GITLAB_CANONICAL_AZURE_SOURCE_MISSING'
    }
    $lines=[IO.File]::ReadAllLines($azure)
    $blocks=[Collections.Generic.List[string]]::new()
    $current=[Collections.Generic.List[string]]::new()
    $inside=$false
    foreach ($line in $lines) {
        if ($line -ceq '  - pwsh: |') {
            if ($inside) { throw 'GITLAB_AZURE_NESTED_STAGE' }
            $inside=$true
            $current.Clear()
            continue
        }
        if (-not $inside) { continue }
        if ($line.StartsWith('      ')) {
            $current.Add($line.Substring(6))
        } elseif ($line.Trim().Length -eq 0) {
            $current.Add('')
        } else {
            $blocks.Add(($current -join [Environment]::NewLine))
            $current.Clear()
            $inside=$false
        }
    }
    if ($inside) { $blocks.Add(($current -join [Environment]::NewLine)) }
    if ($blocks.Count -ne 4) { throw "GITLAB_EXPECTED_FOUR_CANONICAL_STAGES:$($blocks.Count)" }
    $required=@(
        'verify_original_729_source.py',
        'private_build.ps1',
        'build_onehost_installer.ps1',
        'PUBLISHED_PRIVATE_PAYLOAD_SHA256.json'
    )
    for ($i=0; $i -lt 4; $i++) {
        if (-not $blocks[$i].Contains($required[$i])) {
            throw "GITLAB_CANONICAL_STAGE_OWNER_DRIFT:$i"
        }
    }
    # The four original stages are intentionally executed as separate pwsh
    # processes exactly as Azure does: no cross-stage PowerShell local leakage.
    $replace=[ordered]@{
        '$(Build.SourceVersion)'=$head
        '$(Build.BuildId)'=$env:CI_PIPELINE_ID
        '$(Agent.TempDirectory)'=$staging
        '$(Build.ArtifactStagingDirectory)'=$logroot
    }
    $shell=Get-Command pwsh -ErrorAction SilentlyContinue
    if (-not $shell -and (Get-Command choco -ErrorAction SilentlyContinue)) {
        & choco install powershell-core --yes --no-progress --limit-output
        Require-Exit 'POWERSHELL7_INSTALL'
        $env:PATH=(Join-Path $env:ProgramFiles 'PowerShell\7') + ';' + $env:PATH
        $shell=Get-Command pwsh -ErrorAction SilentlyContinue
    }
    if (-not $shell) { throw 'GITLAB_POWERSHELL7_REQUIRED' }
    for ($i=0; $i -lt $blocks.Count; $i++) {
        $code=$blocks[$i]
        foreach ($token in $replace.Keys) { $code=$code.Replace($token,$replace[$token]) }
        # No Azure macro syntax may survive, and no script is evaluated inline.
        if ([regex]::IsMatch($code, '\$\([A-Za-z][A-Za-z0-9.]+\)')) {
            throw "GITLAB_UNMAPPED_AZURE_MACRO:$i"
        }
        $stage=Join-Path $staging ("stage-{0}.ps1" -f $i)
        [IO.File]::WriteAllText($stage,$code,[Text.UTF8Encoding]::new($false))
        Write-Host "GITLAB_CANONICAL_STAGE_START $i SOURCE=$head"
        & $shell.Source -NoProfile -NonInteractive -File $stage
        Require-Exit ("CANONICAL_STAGE_"+$i)
        $blocksCompleted++
        Write-Host "GITLAB_CANONICAL_STAGE_PASS $i"
    }
    $e07=Join-Path $repo 'work/e06/azure-onehost-diagnostic/E07_BUILT_HANDOFF.json'
    if (-not (Test-Path -LiteralPath $e07 -PathType Leaf)) {
        throw 'GITLAB_E07_BUILT_RECEIPT_MISSING'
    }
    $built=Get-Content -LiteralPath $e07 -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($built.phase -cne 'BUILT' -or $built.release_accepted -ne $false -or
        $built.source_commit_sha1 -cne $head) {
        throw 'GITLAB_E07_BUILT_SHA_OR_SOURCE_DRIFT'
    }
    $state='BUILT_DIAGNOSTIC_NOT_E07_RELEASE'
    $reason='E07_INSTALLED_E2E_NOT_RUN'
} catch {
    $state='HOLD'
    $reason=$_.Exception.Message
    Write-Host ("GITLAB_DIAGNOSTIC_HOLD " + $reason)
    throw
} finally {
    $receipt=[ordered]@{
        schema='NOX_V16_GITLAB_FREE_WINDOWS_RUN_V1'
        original_repository='MSSTXNEWS/nox-helion-pp-private-build'
        source_git_sha=$head
        source_branch=$env:CI_COMMIT_REF_NAME
        gitlab_pipeline_id=$env:CI_PIPELINE_ID
        start_utc=$started
        end_utc=[DateTime]::UtcNow.ToString('o')
        canonical_azure_stages_completed=$blocksCompleted
        state=$state
        reason=$reason
        independent_e07_installed_cases=0
        release_accepted=$false
    }
    [IO.File]::WriteAllText($report,($receipt | ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
}
 -or
    $env:CI_COMMIT_REF_NAME -cne $env:NOX_FROZEN_SOURCE_REF -or
    $env:NOX_APPROVE_WINDOWS_BUILD -cne 'YES' -or
    $env:CI_PIPELINE_SOURCE -notin @('web','api')) {
    throw 'GITLAB_EXPLICIT_PRIVATE_MIGRATION_BRANCH_CONSENT_REQUIRED'
}
Set-Location -LiteralPath $repo
if ($env:CI_COMMIT_SHA -cnotmatch '^[0-9a-f]{40}$' -or
    $env:CI_PIPELINE_ID -notmatch '^[0-9]+$') {
    throw 'GITLAB_PINNED_SHA_OR_RUNID_MISSING'
}
$head=(& git -C $repo rev-parse HEAD | Out-String).Trim().ToLowerInvariant()
Require-Exit 'GIT_HEAD'
if ($head -cne $env:CI_COMMIT_SHA.ToLowerInvariant()) { throw 'GITLAB_CHECKOUT_SHA_DRIFT' }

$logroot=Join-Path $repo 'work/gitlab-artifacts'
$destination=Join-Path $logroot 'nox-v16-diagnostic'
$staging=Join-Path $repo 'work/gitlab-tmp'
New-Item -ItemType Directory -Path $logroot,$staging -Force | Out-Null
$report=Join-Path $logroot 'GITLAB_NOX_WINDOWS_RUN_RECEIPT.json'
$started=[DateTime]::UtcNow.ToString('o')
$state='HOLD'
$reason='UNVERIFIED'
$blocksCompleted=0
try {
    # GitLab source admission before optional network installs or costly Windows builds.
    # A release BuildID must not be derived from a malformed/repeated E07 script.
    $handoff=Join-Path $repo 'coordination/e06/Emit-E07ImmutableHandoff.ps1'
    if (-not (Test-Path -LiteralPath $handoff -PathType Leaf)) {
        throw 'GITLAB_E07_HANDOFF_SOURCE_MISSING'
    }
    $parseTokens=$null
    $parseErrors=$null
    [System.Management.Automation.Language.Parser]::ParseFile(
        $handoff,[ref]$parseTokens,[ref]$parseErrors) | Out-Null
    if ($parseErrors.Count -ne 0) { throw 'GITLAB_E07_HANDOFF_POWERSHELL_SYNTAX_HOLD' }
    $handoffText=Get-Content -LiteralPath $handoff -Raw -Encoding UTF8
    if ([regex]::Matches($handoffText,'Write-Host "E07_BUILDID_SEALED').Count -ne 1 -or
        [regex]::Matches($handoffText,'foreach \(\$expected in @\(\$source.parts\)\)').Count -ne 1 -or
        -not $handoffText.Contains('([string]$matching[0].sha256).ToLowerInvariant() -cne ([string]$expected.sha256).ToLowerInvariant()') -or
        -not $handoffText.Contains('([string]$matching[0].gitBlobSha1).ToLowerInvariant() -cne ([string]$expected.git_blob_sha1).ToLowerInvariant()') -or
        -not $handoffText.Contains('release_accepted=$false')) {
        throw 'GITLAB_E07_SINGLE_SEAL_PART_PARITY_HOLD'
    }
    Write-Host 'GITLAB_E07_SOURCE_PREFLIGHT_PASS_NOT_NATIVE_ACCEPTANCE'
    # The GitLab hosted runner has Chocolatey; own runners may install prerequisites
    # themselves. No network credential or token is printed or persisted.
    $python=Find-Python31210
    if (-not $python) {
        if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
            throw 'GITLAB_PYTHON_3_12_10_REQUIRED_NO_INSTALLER'
        }
        & choco install python312 --version=3.12.10 --yes --no-progress --limit-output
        Require-Exit 'PYTHON31210_INSTALL'
        $python=Find-Python31210
    }
    if (-not $python) { throw 'GITLAB_EXACT_PYTHON_3_12_10_MISSING' }
    $env:PATH=(Split-Path -Parent $python) + ';' + $env:PATH
    & python -c 'import sys; assert sys.version_info[:3] == (3,12,10)'
    Require-Exit 'PYTHON_VERSION_RECHECK'
    & python -m unittest discover -s tests/e06 -p 'test_gitlab_free_source_gate.py' -v
    Require-Exit 'GITLAB_MIGRATION_SOURCE_GATE'

    $sdk=@()
    if (Get-Command dotnet -ErrorAction SilentlyContinue) {
        try { $sdk=@(& dotnet --list-sdks 2>$null) } catch { $sdk=@() }
    }
    if (-not @($sdk | Where-Object { $_ -match '^8\.' }).Count) {
        if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
            throw 'GITLAB_DOTNET8_REQUIRED_NO_INSTALLER'
        }
        & choco install dotnet-8.0-sdk --yes --no-progress --limit-output
        Require-Exit 'DOTNET8_INSTALL'
        $env:PATH=(Join-Path $env:ProgramFiles 'dotnet') + ';' + $env:PATH
    }
    $sdk=@(& dotnet --list-sdks)
    Require-Exit 'DOTNET_SDK'
    if (-not @($sdk | Where-Object { $_ -match '^8\.' }).Count) {
        throw 'GITLAB_DOTNET8_SDK_MISSING'
    }
    if (-not (Get-Command makensis -ErrorAction SilentlyContinue) -and
        -not (Test-Path 'C:\Program Files (x86)\NSIS\makensis.exe')) {
        if (-not (Get-Command choco -ErrorAction SilentlyContinue)) {
            throw 'GITLAB_NSIS_REQUIRED_NO_INSTALLER'
        }
        & choco install nsis --yes --no-progress --limit-output
        Require-Exit 'NSIS_INSTALL'
    }
    $env:GITHUB_SHA=$head
    $env:GITHUB_RUN_ID='GITLAB-' + $env:CI_PIPELINE_ID

    $azure=Join-Path $repo 'azure-pipelines-nox-v16.yml'
    if (-not (Test-Path -LiteralPath $azure -PathType Leaf)) {
        throw 'GITLAB_CANONICAL_AZURE_SOURCE_MISSING'
    }
    $lines=[IO.File]::ReadAllLines($azure)
    $blocks=[Collections.Generic.List[string]]::new()
    $current=[Collections.Generic.List[string]]::new()
    $inside=$false
    foreach ($line in $lines) {
        if ($line -ceq '  - pwsh: |') {
            if ($inside) { throw 'GITLAB_AZURE_NESTED_STAGE' }
            $inside=$true
            $current.Clear()
            continue
        }
        if (-not $inside) { continue }
        if ($line.StartsWith('      ')) {
            $current.Add($line.Substring(6))
        } elseif ($line.Trim().Length -eq 0) {
            $current.Add('')
        } else {
            $blocks.Add(($current -join [Environment]::NewLine))
            $current.Clear()
            $inside=$false
        }
    }
    if ($inside) { $blocks.Add(($current -join [Environment]::NewLine)) }
    if ($blocks.Count -ne 4) { throw "GITLAB_EXPECTED_FOUR_CANONICAL_STAGES:$($blocks.Count)" }
    $required=@(
        'verify_original_729_source.py',
        'private_build.ps1',
        'build_onehost_installer.ps1',
        'PUBLISHED_PRIVATE_PAYLOAD_SHA256.json'
    )
    for ($i=0; $i -lt 4; $i++) {
        if (-not $blocks[$i].Contains($required[$i])) {
            throw "GITLAB_CANONICAL_STAGE_OWNER_DRIFT:$i"
        }
    }
    # The four original stages are intentionally executed as separate pwsh
    # processes exactly as Azure does: no cross-stage PowerShell local leakage.
    $replace=[ordered]@{
        '$(Build.SourceVersion)'=$head
        '$(Build.BuildId)'=$env:CI_PIPELINE_ID
        '$(Agent.TempDirectory)'=$staging
        '$(Build.ArtifactStagingDirectory)'=$logroot
    }
    $shell=Get-Command pwsh -ErrorAction SilentlyContinue
    if (-not $shell -and (Get-Command choco -ErrorAction SilentlyContinue)) {
        & choco install powershell-core --yes --no-progress --limit-output
        Require-Exit 'POWERSHELL7_INSTALL'
        $env:PATH=(Join-Path $env:ProgramFiles 'PowerShell\7') + ';' + $env:PATH
        $shell=Get-Command pwsh -ErrorAction SilentlyContinue
    }
    if (-not $shell) { throw 'GITLAB_POWERSHELL7_REQUIRED' }
    for ($i=0; $i -lt $blocks.Count; $i++) {
        $code=$blocks[$i]
        foreach ($token in $replace.Keys) { $code=$code.Replace($token,$replace[$token]) }
        # No Azure macro syntax may survive, and no script is evaluated inline.
        if ([regex]::IsMatch($code, '\$\([A-Za-z][A-Za-z0-9.]+\)')) {
            throw "GITLAB_UNMAPPED_AZURE_MACRO:$i"
        }
        $stage=Join-Path $staging ("stage-{0}.ps1" -f $i)
        [IO.File]::WriteAllText($stage,$code,[Text.UTF8Encoding]::new($false))
        Write-Host "GITLAB_CANONICAL_STAGE_START $i SOURCE=$head"
        & $shell.Source -NoProfile -NonInteractive -File $stage
        Require-Exit ("CANONICAL_STAGE_"+$i)
        $blocksCompleted++
        Write-Host "GITLAB_CANONICAL_STAGE_PASS $i"
    }
    $e07=Join-Path $repo 'work/e06/azure-onehost-diagnostic/E07_BUILT_HANDOFF.json'
    if (-not (Test-Path -LiteralPath $e07 -PathType Leaf)) {
        throw 'GITLAB_E07_BUILT_RECEIPT_MISSING'
    }
    $built=Get-Content -LiteralPath $e07 -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($built.phase -cne 'BUILT' -or $built.release_accepted -ne $false -or
        $built.source_commit_sha1 -cne $head) {
        throw 'GITLAB_E07_BUILT_SHA_OR_SOURCE_DRIFT'
    }
    $state='BUILT_DIAGNOSTIC_NOT_E07_RELEASE'
    $reason='E07_INSTALLED_E2E_NOT_RUN'
} catch {
    $state='HOLD'
    $reason=$_.Exception.Message
    Write-Host ("GITLAB_DIAGNOSTIC_HOLD " + $reason)
    throw
} finally {
    $receipt=[ordered]@{
        schema='NOX_V16_GITLAB_FREE_WINDOWS_RUN_V1'
        original_repository='MSSTXNEWS/nox-helion-pp-private-build'
        source_git_sha=$head
        source_branch=$env:CI_COMMIT_REF_NAME
        gitlab_pipeline_id=$env:CI_PIPELINE_ID
        start_utc=$started
        end_utc=[DateTime]::UtcNow.ToString('o')
        canonical_azure_stages_completed=$blocksCompleted
        state=$state
        reason=$reason
        independent_e07_installed_cases=0
        release_accepted=$false
    }
    [IO.File]::WriteAllText($report,($receipt | ConvertTo-Json -Depth 6),[Text.UTF8Encoding]::new($false))
}
