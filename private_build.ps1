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
$qaLockSha = $null
$qaWheels = $null
$qaDependencyFailure = $null
$qaDependenciesReady = $false

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
    $pyLauncher = Get-Command py -ErrorAction Stop
    if ($pyLauncher.CommandType -ne 'Application') { throw 'PY_LAUNCHER_NAME_COLLISION' }
    $venv = Join-Path $work 'build-venv'
    & py -3.12 -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "BUILD_VENV_CREATE_FAILED:$LASTEXITCODE" }
    $venvPython = Join-Path $venv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) { throw 'BUILD_VENV_PYTHON_MISSING' }
    & $venvPython -E -s -m pip --isolated install --disable-pip-version-check --no-index --only-binary=:all: --find-links $wheels --require-hashes -r $requirements
    if ($LASTEXITCODE -ne 0) { throw "OFFLINE_PINNED_DEPENDENCY_INSTALL_FAILED:$LASTEXITCODE" }
    & $venvPython -E -s -m pip --isolated check
    if ($LASTEXITCODE -ne 0) { throw "PIP_CHECK_FAILED:$LASTEXITCODE" }

    $qaRequirements = Join-Path $root 'requirements-qa-win64-hashed.txt'
    if (Test-Path -LiteralPath $qaRequirements -PathType Leaf) {
        $qaLockSha = (Get-FileHash -LiteralPath $qaRequirements -Algorithm SHA256).Hash.ToLowerInvariant()
        $qaWheels = Join-Path $evidence ('qa-wheelhouse-' + $qaLockSha.Substring(0,12))
        Copy-Item -LiteralPath $qaRequirements -Destination (Join-Path $evidence 'requirements-qa-win64-hashed.txt') -Force
        New-Item -ItemType Directory -Path $qaWheels -Force | Out-Null
        try {
            & $venvPython -E -s -m pip --isolated download --disable-pip-version-check --no-deps --only-binary=:all: --dest $qaWheels --require-hashes -r $qaRequirements
            if ($LASTEXITCODE -ne 0) { throw "QA_WHEEL_DOWNLOAD_FAILED:$LASTEXITCODE" }
            $qaExpectedWheels = [ordered]@{
                'lxml-6.1.3-cp312-cp312-win_amd64.whl'='3e9a00d1c2c30936f7add097c41afc5da6556c580909104aafd382cac92a855c'
                'pillow-13.0.0-cp312-cp312-win_amd64.whl'='ff3fe9eb621fbb9db4c4be33ab946f6bac5f98ab50ca8d3260503653656c961b'
                'python_docx-1.2.0-py3-none-any.whl'='3fd478f3250fbbbfd3b94fe1e985955737c145627498896a8a6bf81f4baf66c7'
                'typing_extensions-4.16.0-py3-none-any.whl'='481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8'
                'tzdata-2026.5-py2.py3-none-any.whl'='b683bd1b6659ddcd810ff02ad09ba821d4bf1065072805063eb35c49617905ac'
            }
            foreach ($wheelName in $qaExpectedWheels.Keys) {
                Assert-Sha256 (Join-Path $qaWheels $wheelName) $qaExpectedWheels[$wheelName] ('QA wheel '+$wheelName)
            }
            & $venvPython -E -s -m pip --isolated install --disable-pip-version-check --no-index --no-deps --only-binary=:all: --find-links $qaWheels --require-hashes -r $qaRequirements
            if ($LASTEXITCODE -ne 0) { throw "QA_DEPENDENCY_INSTALL_FAILED:$LASTEXITCODE" }
            & $venvPython -E -s -m pip --isolated check
            if ($LASTEXITCODE -ne 0) { throw "QA_DEPENDENCY_PIP_CHECK_FAILED:$LASTEXITCODE" }
            $qaDependenciesReady = $true
        } catch {
            $qaDependencyFailure = ($_ | Out-String).Trim()
            Write-Warning ("QA_DEPENDENCIES_NOT_READY; continuing to compile and preserve candidate. " + $qaDependencyFailure)
        }
    } else {
        $qaDependencyFailure = 'QA_DEPENDENCY_LOCK_MISSING'
        Write-Warning 'QA_DEPENDENCY_LOCK_MISSING; continuing to compile and preserve candidate.'
    }

    & $venvPython -E -s -c 'import sys,struct,tkinter,pytest,trimesh,numpy,PyInstaller; assert sys.version_info[:3]==(3,12,10); assert struct.calcsize("P")==8; assert PyInstaller.__version__=="6.16.0"'
    if ($LASTEXITCODE -ne 0) { throw "PINNED_PYTHON_TK_AND_BUILD_IMPORTS_REQUIRED:$LASTEXITCODE" }
    if ($qaDependenciesReady) {
        & $venvPython -E -s -c 'import PIL,docx,lxml,typing_extensions,tzdata,zoneinfo; from importlib import metadata; assert metadata.version("Pillow")=="13.0.0"; assert metadata.version("python-docx")=="1.2.0"; assert metadata.version("lxml")=="6.1.3"; assert metadata.version("typing-extensions")=="4.16.0"; assert metadata.version("tzdata")=="2026.5"; zoneinfo.ZoneInfo("Europe/Madrid")'
        if ($LASTEXITCODE -ne 0) {
            $qaDependenciesReady = $false
            $qaDependencyFailure = 'QA_DEPENDENCY_IMPORT_VERSION_OR_ZONEINFO_PROBE_FAILED'
            Write-Warning $qaDependencyFailure
        }
    }

    # Route the existing source builder's `py -3.12` calls to this isolated
    # interpreter; keep the hosted runner's preinstalled tools untouched.
    function py {
        $pythonArgs = @($args)
        if ($pythonArgs.Count -lt 1 -or $pythonArgs[0] -cne '-3.12') {
            throw 'UNEXPECTED_PY_LAUNCHER_SELECTOR'
        }
        $pythonArgs = @($pythonArgs | Select-Object -Skip 1)
        & $venvPython @pythonArgs
    }

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
        qa_requirements_sha256=$qaLockSha
        qa_dependencies_ready=$qaDependenciesReady
        qa_dependency_failure=$qaDependencyFailure
        qa_wheels=if ($null -ne $qaWheels -and (Test-Path -LiteralPath $qaWheels -PathType Container)) {@(Get-ChildItem -LiteralPath $qaWheels -Filter '*.whl' -File | ForEach-Object {[ordered]@{name=$_.Name;bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}})} else {@()}
        exes=$exeRecords
        release_accepted=$false
        failure=$failure
    }
    $result | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $evidence 'build-attempt.json') -Encoding UTF8
    New-Item -ItemType Directory -Path $output -Force | Out-Null
    $baseNotices = Join-Path $deps 'DEPENDENCY_NOTICES.txt'
    if (Test-Path -LiteralPath $baseNotices -PathType Leaf) { Copy-Item -LiteralPath $baseNotices -Destination (Join-Path $output 'DEPENDENCY_NOTICES.txt') -Force }
    $qaNotices = Join-Path $root 'QA_DEPENDENCY_NOTICES.txt'
    if (Test-Path -LiteralPath $qaNotices -PathType Leaf) { Copy-Item -LiteralPath $qaNotices -Destination (Join-Path $output 'QA_DEPENDENCY_NOTICES.txt') -Force }
    if (Test-Path -LiteralPath $qaRequirements -PathType Leaf) { Copy-Item -LiteralPath $qaRequirements -Destination (Join-Path $output 'requirements-qa-win64-hashed.txt') -Force }
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
    $candidateReadme = @(
        'PRE-PRE diagnostic Windows candidate; release_accepted=false.'
        "run_id: $env:GITHUB_RUN_ID"
        "source_base_tree: $baseTree"
        "source_patched_tree: $patchedTree"
        "qa_requirements_sha256: $qaLockSha"
        "qa_dependencies_ready: $qaDependenciesReady"
        "qa_dependency_failure: $qaDependencyFailure"
        'Check C_RELEASE_SPRINT_BUILD_RECEIPT.json and build-attempt.json for exact gates and EXE SHA values.'
        'Real local-model inference through the GUI, Persona/history/STOP, full rights and independent acceptance remain unverified unless separately evidenced.'
    ) -join [Environment]::NewLine
    Set-Content -LiteralPath (Join-Path $output 'CANDIDATE_README.txt') -Value $candidateReadme -Encoding UTF8
    try { Stop-Transcript | Out-Null } catch {}
}

if ($null -ne $failure) { throw $failure }
