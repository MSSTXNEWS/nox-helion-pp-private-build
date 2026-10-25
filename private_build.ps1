$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$root = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$evidence = Join-Path $root 'ci-evidence'
$work = Join-Path $root 'work'
$source = Join-Path $work 'source'
$deps = Join-Path $work 'dependencies'
$output = Join-Path $work 'candidate'
$sourceZip = Join-Path $work 'NOX_PP_SOURCE.zip'
$sourceExpectedBytes = 60364346
$sourceExpectedSha = 'ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a'
$baseTreeExpected = '1454257c66d5107b12091b8e81706e51b0cfb672'
$patchedTreeExpected = 'd16663f9fd26aa0eab90270fff1bb65bc3f805e6'
$patchZip = Join-Path $root 'NOX_A04_BUILD_PATCH.zip'
$patchZipExpected = '37078f0105f42ff9964a533399a9a71769d0517e8f0e3f49e3e7266ae28eb4eb'
$patchExpected = 'cc799cde9b99c37be113950da2fcef53491873ccd417ca426cacbced47a83996'
$wheelZip = Join-Path $work 'NOX_PP_BUILD_WHEELHOUSE_18.zip'
$wheelExpected = '2b6291a45f7c03c583e2073d069f6a1de5832d3bc54b33150f940b4aa53598ff'
$started = [DateTime]::UtcNow
$failure = $null
$baseTree = $null
$patchedTree = $null
$exeRecords = @()

New-Item -ItemType Directory -Path $evidence -Force | Out-Null
New-Item -ItemType Directory -Path $work -Force | Out-Null
Start-Transcript -LiteralPath (Join-Path $evidence 'windows-build-transcript.txt') -Force | Out-Null

function Assert-Sha256([string]$Path, [string]$Expected, [string]$Label) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { throw "$Label is missing: $Path" }
    $actual = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actual -cne $Expected) { throw "$Label SHA256 mismatch: expected=$Expected actual=$actual" }
}

function Invoke-Git([string[]]$GitArgs) {
    & git @GitArgs
    if ($LASTEXITCODE -ne 0) { throw "git command failed ($LASTEXITCODE): $($GitArgs -join ' ')" }
}

try {
    if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem -or
        [Runtime.InteropServices.RuntimeInformation]::OSArchitecture -ne [Runtime.InteropServices.Architecture]::X64) {
        throw 'AUTHORIZED_WINDOWS_X64_RUNNER_REQUIRED'
    }

    $chunkNames = @('source_00.part', 'source_01.part', 'source_02.part')
    $outStream = [IO.File]::Open($sourceZip, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        foreach ($chunkName in $chunkNames) {
            $chunkPath = Join-Path $root $chunkName
            if (-not (Test-Path -LiteralPath $chunkPath -PathType Leaf)) { throw "SOURCE_CHUNK_MISSING:$chunkName" }
            $inputStream = [IO.File]::OpenRead($chunkPath)
            try { $inputStream.CopyTo($outStream) } finally { $inputStream.Dispose() }
        }
    } finally { $outStream.Dispose() }
    $actualBytes = (Get-Item -LiteralPath $sourceZip).Length
    if ($actualBytes -ne $sourceExpectedBytes) { throw "SOURCE_ARCHIVE_SIZE_MISMATCH:$actualBytes" }
    Assert-Sha256 $sourceZip $sourceExpectedSha 'PRE-PRE source archive'

    Assert-Sha256 $patchZip $patchZipExpected 'A04 patch package'
    $wheelPartNames = @('wheelhouse_00.part', 'wheelhouse_01.part', 'wheelhouse_02.part')
    $wheelStream = [IO.File]::Open($wheelZip, [IO.FileMode]::Create, [IO.FileAccess]::Write, [IO.FileShare]::None)
    try {
        foreach ($partName in $wheelPartNames) {
            $partPath = Join-Path $root $partName
            if (-not (Test-Path -LiteralPath $partPath -PathType Leaf)) { throw "WHEELHOUSE_CHUNK_MISSING:$partName" }
            $partStream = [IO.File]::OpenRead($partPath)
            try { $partStream.CopyTo($wheelStream) } finally { $partStream.Dispose() }
        }
    } finally { $wheelStream.Dispose() }
    if ((Get-Item -LiteralPath $wheelZip).Length -ne 21874335) { throw 'WHEELHOUSE_ARCHIVE_SIZE_MISMATCH' }
    Assert-Sha256 $wheelZip $wheelExpected '18-wheel build dependency package'
    if (Test-Path -LiteralPath $source) { Remove-Item -LiteralPath $source -Recurse -Force }
    if (Test-Path -LiteralPath $deps) { Remove-Item -LiteralPath $deps -Recurse -Force }
    if (Test-Path -LiteralPath $output) { Remove-Item -LiteralPath $output -Recurse -Force }
    Expand-Archive -LiteralPath $sourceZip -DestinationPath $source
    $delivery = Join-Path $source '_delivery'
    if (Test-Path -LiteralPath $delivery -PathType Container) { Remove-Item -LiteralPath $delivery -Recurse -Force }
    Expand-Archive -LiteralPath $wheelZip -DestinationPath $deps

    $patchDir = Join-Path $evidence 'patch'
    Expand-Archive -LiteralPath $patchZip -DestinationPath $patchDir
    $patchPath = Join-Path $patchDir 'A04_BUILD_REPAIRS_EXACT_PARENT.patch'
    Assert-Sha256 $patchPath $patchExpected 'A04 source patch'

    Invoke-Git @('-C', $source, 'init', '--quiet')
    Invoke-Git @('-C', $source, 'config', 'core.autocrlf', 'false')
    Invoke-Git @('-C', $source, 'add', '--all')
    Invoke-Git @('-C', $source, 'update-index', '--chmod=+x', '--', 'tools/MB1_RUNTIME_PREFLIGHT.py', 'tools/visual_pack_gate.py')
    $baseTree = (& git -C $source write-tree).Trim()
    if ($LASTEXITCODE -ne 0 -or $baseTree -cne $baseTreeExpected) {
        throw "PRE-PRE base tree mismatch: expected=$baseTreeExpected actual=$baseTree"
    }

    Invoke-Git @('-C', $source, 'apply', '--check', $patchPath)
    Invoke-Git @('-C', $source, 'apply', $patchPath)
    Invoke-Git @('-C', $source, 'add', '--all')
    Invoke-Git @('-C', $source, 'update-index', '--chmod=+x', '--', 'tools/MB1_RUNTIME_PREFLIGHT.py', 'tools/visual_pack_gate.py')
    $patchedTree = (& git -C $source write-tree).Trim()
    if ($LASTEXITCODE -ne 0 -or $patchedTree -cne $patchedTreeExpected) {
        throw "A04 patched tree mismatch: expected=$patchedTreeExpected actual=$patchedTree"
    }

    $requirements = Join-Path $deps 'requirements-build-win64-hashed.txt'
    $wheels = Join-Path $deps 'wheels'
    & py -3.12 -E -s -m pip install --disable-pip-version-check --no-index --only-binary=:all: --find-links $wheels --require-hashes -r $requirements
    if ($LASTEXITCODE -ne 0) { throw "OFFLINE_PINNED_DEPENDENCY_INSTALL_FAILED:$LASTEXITCODE" }
    & py -3.12 -E -s -m pip check
    if ($LASTEXITCODE -ne 0) { throw "PIP_CHECK_FAILED:$LASTEXITCODE" }
    & py -3.12 -E -s -c 'import sys,struct,tkinter,pytest,trimesh,numpy,PyInstaller; assert sys.version_info[:3]==(3,12,10); assert struct.calcsize("P")==8; assert PyInstaller.__version__=="6.16.0"'
    if ($LASTEXITCODE -ne 0) { throw "PINNED_PYTHON_TK_AND_BUILD_IMPORTS_REQUIRED:$LASTEXITCODE" }

    New-Item -ItemType Directory -Path $output | Out-Null
    & (Join-Path $source 'C_RELEASE_SPRINT_BUILD.ps1') -OutputDirectory $output -AuthorizedIsolatedWindowsVM
    if ($LASTEXITCODE -ne 0) { throw "C_RELEASE_SPRINT_BUILD_FAILED:$LASTEXITCODE" }
} catch {
    $failure = ($_ | Out-String).Trim()
    Write-Error $failure
} finally {
    if (Test-Path -LiteralPath $output -PathType Container) {
        $exeRecords = @(Get-ChildItem -LiteralPath $output -Filter '*.exe' -File -ErrorAction SilentlyContinue | ForEach-Object {
            [ordered]@{name=$_.Name;bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
        })
    }
    $finished = [DateTime]::UtcNow
    $runStatus = if ($null -eq $failure) { 'BUILD_SCRIPT_RETURNED_SUCCESS' } else { 'INCOMPLETE_OR_FAILED' }
    $result = [ordered]@{
        schema='NOX_PRIVATE_PP_WINDOWS_BUILD_ATTEMPT_V1'
        status=$runStatus
        start_utc=$started.ToString('o')
        end_utc=$finished.ToString('o')
        duration_seconds=[math]::Round(($finished-$started).TotalSeconds,3)
        source_archive_bytes=if (Test-Path -LiteralPath $sourceZip) {(Get-Item -LiteralPath $sourceZip).Length} else {$null}
        source_archive_sha256=if (Test-Path -LiteralPath $sourceZip) {(Get-FileHash -LiteralPath $sourceZip -Algorithm SHA256).Hash.ToLowerInvariant()} else {$null}
        source_base_tree=$baseTree
        source_patched_tree=$patchedTree
        source_tree_expected=$patchedTreeExpected
        a04_patch_zip_sha256=if (Test-Path -LiteralPath $patchZip) {(Get-FileHash -LiteralPath $patchZip -Algorithm SHA256).Hash.ToLowerInvariant()} else {$null}
        wheelhouse_sha256=if (Test-Path -LiteralPath $wheelZip) {(Get-FileHash -LiteralPath $wheelZip -Algorithm SHA256).Hash.ToLowerInvariant()} else {$null}
        exes=$exeRecords
        release_accepted=$false
        failure=$failure
    }
    $result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $evidence 'build-attempt.json') -Encoding UTF8
    New-Item -ItemType Directory -Path $output -Force | Out-Null
    $statusText = @(
        'PRE-RELEASE WINDOWS CANDIDATE BUILD'
        "status: $runStatus"
        "release_accepted: false"
        "executables_observed: $($exeRecords.Count)"
        "source_base_tree: $baseTree"
        "source_patched_tree: $patchedTree"
        "failure: $failure"
    ) -join [Environment]::NewLine
    Set-Content -LiteralPath (Join-Path $output 'BUILD_STATUS.txt') -Value $statusText -Encoding UTF8
    try { Stop-Transcript | Out-Null } catch {}
}

if ($null -ne $failure) { throw $failure }
