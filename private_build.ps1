[CmdletBinding()]
param(
    [switch]$OneHostNative,
    [string]$RunId = ''
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
if ($OneHostNative -and ($RunId -cnotmatch '^[\x20-\x7e]{1,128}$')) {
    throw 'ONEHOST_NATIVE_RUN_ID_REQUIRED'
}

$root = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$evidence = Join-Path $root 'ci-evidence'
$work = Join-Path $root 'work'
$source = Join-Path $work 'source'
$deps = Join-Path $work 'dependencies'
$output = Join-Path $work 'candidate'
$qaRequirements = Join-Path $root 'requirements-qa-win64-hashed.txt'
$sourceZip = Join-Path $work 'NOX_PP_SOURCE.zip'
$sourceExpectedBytes = 60364346
$sourceExpectedSha = 'ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a'
$baseTreeExpected = '1454257c66d5107b12091b8e81706e51b0cfb672'
$a04TreeExpected = 'd16663f9fd26aa0eab90270fff1bb65bc3f805e6'
$menuTreeExpected = '63f26c20d703d6aa91b941c94266ae7c3a563a5d'
$patchedTreeExpected = 'd61632a7dd4ca889f16eba2d330e2ed5fd6b3842'
$patchZip = Join-Path $root 'NOX_A04_BUILD_PATCH.zip'
$patchZipExpected = '37078f0105f42ff9964a533399a9a71769d0517e8f0e3f49e3e7266ae28eb4eb'
$patchExpected = 'cc799cde9b99c37be113950da2fcef53491873ccd417ca426cacbced47a83996'
$resourcePatch = Join-Path $root 'PP_MENU_CATALOG_BUNDLE.patch'
$resourcePatchExpected = '9a79aefb78e87aa41ad784e0a0ca4a6f26a765f084420d86e244505d1d7c1215'
$fastCandidatePatch = Join-Path $root 'PP_FAST_CANDIDATE_MODE.patch'
$fastCandidatePatchExpected = 'f37c00be1c47a6dc8c5317b7670d4fe0998622f99a159acae448e3926ee30e5d'
$wheelZip = Join-Path $work 'NOX_PP_BUILD_WHEELHOUSE_18.zip'
$wheelExpected = '2b6291a45f7c03c583e2073d069f6a1de5832d3bc54b33150f940b4aa53598ff'
$started = [DateTime]::UtcNow
$failure = $null
$baseTree = $null
$patchedTree = $null
$sourceQaStatus = 'NOT_RECORDED'
$nativeSmokeStatus = 'NOT_RECORDED'
$fastCandidateSelected = -not [bool]$OneHostNative
$cReceipt = $null
$receiptValid = $false
$fastCandidateComplete = $false
$exeRecords = @()
$qaLockSha = $null
$qaWheels = $null
$qaDependencyFailure = $null
$qaDependenciesReady = $false
$oneHostReceipt = $null
$oneHostData = @()

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

function Test-PatchedSourceCache([string]$Path, [string]$ExpectedTree) {
    $gitDirectory = Join-Path $Path '.git'
    if (-not (Test-Path -LiteralPath $gitDirectory -PathType Container)) { return $false }
    try {
        $deliveryPath = Join-Path $Path '_delivery'
        if (Test-Path -LiteralPath $deliveryPath -PathType Container) {
            Remove-Item -LiteralPath $deliveryPath -Recurse -Force
        }
        Invoke-Git @('-C', $Path, 'config', 'core.autocrlf', 'false')
        Invoke-Git @('-C', $Path, 'add', '--all')
        Invoke-Git @('-C', $Path, 'update-index', '--chmod=+x', '--', 'tools/MB1_RUNTIME_PREFLIGHT.py', 'tools/visual_pack_gate.py')
        $cachedTree = (& git -C $Path write-tree).Trim()
        if ($LASTEXITCODE -ne 0) { return $false }
        return $cachedTree -ceq $ExpectedTree
    } catch {
        return $false
    }
}

try {
    $freezePath = Join-Path (Join-Path $root 'evidence') 'PP-ONE-037-C2-SOURCE-FREEZE.json'
    if (-not (Test-Path -LiteralPath $freezePath -PathType Leaf)) { throw 'SOURCE_FREEZE_MANIFEST_MISSING' }
    $freeze = Get-Content -LiteralPath $freezePath -Raw | ConvertFrom-Json
    if ($freeze.schema -cne 'NOX_PP_SOURCE_FREEZE_BINDING_V1' -or $freeze.packet -cne 'PP-ONE-037' -or $freeze.approach -cne 'C2') {
        throw 'SOURCE_FREEZE_MANIFEST_IDENTITY_MISMATCH'
    }
    $locked = $freeze.pinned_build_inputs
    if ($locked.source_archive_sha256 -cne $sourceExpectedSha -or $locked.source_archive_bytes -ne $sourceExpectedBytes) {
        throw 'SOURCE_FREEZE_ARCHIVE_BINDING_MISMATCH'
    }
    if ($locked.base_tree -cne $baseTreeExpected -or $locked.patched_tree_expected -cne $patchedTreeExpected) {
        throw 'SOURCE_FREEZE_TREE_BINDING_MISMATCH'
    }
    if ($locked.a04_patch_zip_sha256 -cne $patchZipExpected -or $locked.a04_patch_sha256 -cne $patchExpected) {
        throw 'SOURCE_FREEZE_A04_PATCH_BINDING_MISMATCH'
    }
    if ($locked.menu_patch_sha256 -cne $resourcePatchExpected -or $locked.fast_candidate_patch_sha256 -cne $fastCandidatePatchExpected) {
        throw 'SOURCE_FREEZE_PATCH_CHAIN_BINDING_MISMATCH'
    }
    if ($locked.build_wheelhouse_sha256 -cne $wheelExpected) {
        throw 'SOURCE_FREEZE_WHEELHOUSE_BINDING_MISMATCH'
    }

    # P01 SourceLock: pin the checkout identity before touching the archived source.
    # The archive and its independent source-freeze binding remain authoritative.
    $checkoutCommit = (& git -C $root rev-parse HEAD 2>$null)
    $checkoutTree = (& git -C $root rev-parse HEAD^{tree} 2>$null)
    if ($LASTEXITCODE -ne 0 -or -not $checkoutCommit -or -not $checkoutTree) {
        throw 'P01_SOURCELOCK_CHECKOUT_UNAVAILABLE'
    }
    $checkoutCommit = ([string]$checkoutCommit).Trim()
    $checkoutTree = ([string]$checkoutTree).Trim()
    $sourceLock = [ordered]@{
        schema = 'NOX_P01_SOURCELOCK_V1'
        task_id = 'NOX-FIN-ZAGR-V15-EXECUTOR-1-P01'
        repository = 'MSSTXNEWS/nox-helion-pp-private-build'
        checkout_commit = $checkoutCommit
        checkout_tree = $checkoutTree
        frozen_source_sha256 = $sourceExpectedSha
        frozen_base_tree = $baseTreeExpected
        frozen_patched_tree = $patchedTreeExpected
        freeze_manifest = 'evidence/PP-ONE-037-C2-SOURCE-FREEZE.json'
        captured_utc = [DateTime]::UtcNow.ToString('o')
    }
    $sourceLock | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $evidence 'p01-sourcelock.json') -Encoding UTF8

    # Diagnostic only: installed prerequisites must never be mistaken for
    # bundled dependencies. No host software is modified or silently installed.
    $toolState = [ordered]@{}
    foreach ($toolName in @('py','python','ollama','git','makensis')) {
        $command = Get-Command $toolName -CommandType Application -ErrorAction SilentlyContinue |
            Select-Object -First 1
        $toolState[$toolName] = [ordered]@{
            detected = ($null -ne $command)
            path = if ($null -ne $command) { $command.Source } else { $null }
        }
    }
    [ordered]@{
        schema = 'NOX_P01_PREREQUISITES_V1'
        task_id = 'NOX-FIN-ZAGR-V15-EXECUTOR-1-P01'
        checkout_commit = $checkoutCommit
        captured_utc = [DateTime]::UtcNow.ToString('o')
        tools = $toolState
        note = 'Detection only; no download, install, update, rollback or runtime acceptance inferred.'
    } | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $evidence 'p01-prerequisites.json') -Encoding UTF8

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
    $wheelArchiveReused = $false
    if (Test-Path -LiteralPath $wheelZip -PathType Leaf) {
        if ((Get-Item -LiteralPath $wheelZip).Length -eq 21874335) {
            try {
                $cachedWheelSha = (Get-FileHash -LiteralPath $wheelZip -Algorithm SHA256).Hash.ToLowerInvariant()
                $wheelArchiveReused = $cachedWheelSha -ceq $wheelExpected
            } catch {
                $wheelArchiveReused = $false
            }
        }
    }
    if (-not $wheelArchiveReused) {
        if (Test-Path -LiteralPath $wheelZip -PathType Leaf) { Remove-Item -LiteralPath $wheelZip -Force }
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
    } else {
        Write-Output "WHEELHOUSE_ARCHIVE_REUSED:$wheelExpected"
    }
    $sourceReady = Test-PatchedSourceCache -Path $source -ExpectedTree $patchedTreeExpected
    if (Test-Path -LiteralPath $deps) { Remove-Item -LiteralPath $deps -Recurse -Force }
    if (Test-Path -LiteralPath $output) { Remove-Item -LiteralPath $output -Recurse -Force }
    if (-not $sourceReady) {
        if (Test-Path -LiteralPath $source) { Remove-Item -LiteralPath $source -Recurse -Force }
        Expand-Archive -LiteralPath $sourceZip -DestinationPath $source
        $delivery = Join-Path $source '_delivery'
        if (Test-Path -LiteralPath $delivery -PathType Container) { Remove-Item -LiteralPath $delivery -Recurse -Force }
    } else {
        Write-Output "SOURCE_CACHE_REUSED:$patchedTreeExpected"
    }
    Expand-Archive -LiteralPath $wheelZip -DestinationPath $deps

    $patchDir = Join-Path $evidence 'patch'
    Expand-Archive -LiteralPath $patchZip -DestinationPath $patchDir
    $patchPath = Join-Path $patchDir 'A04_BUILD_REPAIRS_EXACT_PARENT.patch'
    Assert-Sha256 $patchPath $patchExpected 'A04 source patch'
    Assert-Sha256 $resourcePatch $resourcePatchExpected 'PP menu catalog bundle patch'
    Assert-Sha256 $fastCandidatePatch $fastCandidatePatchExpected 'PP fast candidate mode patch'

    if (-not $sourceReady) {
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
        $a04Tree = (& git -C $source write-tree).Trim()
        if ($LASTEXITCODE -ne 0 -or $a04Tree -cne $a04TreeExpected) {
            throw "A04 patched tree mismatch: expected=$a04TreeExpected actual=$a04Tree"
        }
        Invoke-Git @('-C', $source, 'apply', '--check', $resourcePatch)
        Invoke-Git @('-C', $source, 'apply', $resourcePatch)
        Invoke-Git @('-C', $source, 'add', '--all')
        Invoke-Git @('-C', $source, 'update-index', '--chmod=+x', '--', 'tools/MB1_RUNTIME_PREFLIGHT.py', 'tools/visual_pack_gate.py')
        $menuTree = (& git -C $source write-tree).Trim()
        if ($LASTEXITCODE -ne 0 -or $menuTree -cne $menuTreeExpected) {
            throw "Menu catalog bundle tree mismatch: expected=$menuTreeExpected actual=$menuTree"
        }
        Invoke-Git @('-C', $source, 'apply', '--check', $fastCandidatePatch)
        Invoke-Git @('-C', $source, 'apply', $fastCandidatePatch)
        Invoke-Git @('-C', $source, 'add', '--all')
        Invoke-Git @('-C', $source, 'update-index', '--chmod=+x', '--', 'tools/MB1_RUNTIME_PREFLIGHT.py', 'tools/visual_pack_gate.py')
        $patchedTree = (& git -C $source write-tree).Trim()
        if ($LASTEXITCODE -ne 0 -or $patchedTree -cne $patchedTreeExpected) {
            throw "Final patched tree mismatch: expected=$patchedTreeExpected actual=$patchedTree"
        }
    } else {
        $patchedTree = $patchedTreeExpected
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
                'python_pptx-1.0.2-py3-none-any.whl'='160838e0b8565a8b1f67947675886e9fea18aa5e795db7ae531606d68e785cba'
                'xlsxwriter-3.3.0-py3-none-any.whl'='5f04772d43281da5109af66f39b65153359a203e896847c416476e709b024469'
                'reportlab-5.1.0-py3-none-any.whl'='59fdbaec5efe437095ad1d7292ec9a271c8ca2d3ec75e889c6e61400929b90df'
                'charset_normalizer-3.5.2-cp312-cp312-win_amd64.whl'='780fbe7cab297b81dad9fb8dc5eb003c0468ffb0d9e5f65068c53a34661a96bc'
                'pypdf-6.21.2-py3-none-any.whl'='1d44d1a3a200f25062adff0085b02040e4646431ac2ccac22e42679e91466084'
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
        & $venvPython -E -s -c 'import PIL,docx,lxml,typing_extensions,tzdata,zoneinfo,pptx,reportlab,xlsxwriter,charset_normalizer,pypdf; from importlib import metadata; assert metadata.version("Pillow")=="13.0.0"; assert metadata.version("python-docx")=="1.2.0"; assert metadata.version("lxml")=="6.1.3"; assert metadata.version("typing-extensions")=="4.16.0"; assert metadata.version("tzdata")=="2026.5"; assert metadata.version("python-pptx")=="1.0.2"; assert metadata.version("XlsxWriter")=="3.3.0"; assert metadata.version("reportlab")=="5.1.0"; assert metadata.version("charset-normalizer")=="3.5.2"; assert metadata.version("pypdf")=="6.21.2"; zoneinfo.ZoneInfo("Europe/Madrid")'
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
    if ($OneHostNative) {
        # OneHost uses the original CLI entrypoint, not the windowed diagnostic
        # entrypoint which does not route --native-stdio and has no stdout.
        $stageTool = Join-Path $root 'coordination/e06/stage_native_stdio.py'
        $stageCode = 'import importlib.util,json,sys,pathlib; p=pathlib.Path(sys.argv[1]); spec=importlib.util.spec_from_file_location("e06_native_stage",p); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print(json.dumps(m.stage(pathlib.Path(sys.argv[2]))))'
        $stageOutput = @(& $venvPython -I -c $stageCode $stageTool $source)
        if ($LASTEXITCODE -ne 0) { throw 'ONEHOST_NATIVE_STAGE_FAILED' }
        $nativeStage = ($stageOutput -join "`n") | ConvertFrom-Json
        if ($nativeStage.original_archive_modified -ne $false -or
            $nativeStage.installed_windows_exe_accepted -ne $false -or
            @($nativeStage.runtime_data_files).Count -lt 5) {
            throw 'ONEHOST_NATIVE_STAGE_RECEIPT_INVALID'
        }
        $oneHostData = @($nativeStage.runtime_data_files)
        $seenRuntime = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
        $nativeArgs = @('-I','-m','PyInstaller','--noconfirm','--onefile','--console',
            '--noupx','--name','NOX_HELION_PRIVATE_CANDIDATE','--distpath',$output,
            '--workpath',(Join-Path $work 'onehost-pyinstaller-work'),
            '--specpath',(Join-Path $work 'onehost-pyinstaller-spec'),'--paths',$source,
            '--add-data',((Join-Path $source 'assets')+';assets'),
            '--add-data',((Join-Path $source 'helion/data/traits_seed_64.json')+';helion/data'),
            '--add-data',((Join-Path $source 'helion/ai_weights/weights')+';helion/ai_weights/weights'))
        foreach ($record in $oneHostData) {
            $rel = [string]$record.runtime_path
            $destination = [string]$record.pyinstaller_destination
            if ($rel -cnotmatch '^[A-Za-z0-9_.\/-]+$' -or $rel.StartsWith('/') -or
                @($rel.Split('/') | Where-Object { $_ -in @('','..','.') }).Count -gt 0 -or
                -not $seenRuntime.Add($rel) -or [string]$record.sha256 -cnotmatch '^[0-9a-f]{64}$') {
                throw 'ONEHOST_NATIVE_DATA_PATH_OR_SHA_INVALID'
            }
            $expectedDestination = [IO.Path]::GetDirectoryName($rel).Replace('\','/')
            if ([string]::IsNullOrEmpty($expectedDestination)) { $expectedDestination = '.' }
            if ($destination.Replace('\','/') -cne $expectedDestination) {
                throw 'ONEHOST_NATIVE_DATA_DESTINATION_MISMATCH'
            }
            $dataPath = Join-Path $source $rel
            $cursor = Get-Item -LiteralPath $dataPath -Force
            while ($null -ne $cursor -and $cursor.FullName -cne $source) {
                if (($cursor.Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
                    throw 'ONEHOST_NATIVE_DATA_REPARSE_DENIED'
                }
                $cursor = [IO.Directory]::GetParent($cursor.FullName)
            }
            Assert-Sha256 $dataPath ([string]$record.sha256) ('OneHost runtime data '+$rel)
            # Original assets are already included as a complete directory.
            if (-not $rel.StartsWith('assets/',[StringComparison]::Ordinal)) {
                $nativeArgs += @('--add-data',($dataPath+';'+$destination))
            }
        }
        foreach ($required in @('catalog30.discovery.json',
            'assets/NOX_SOUL_CPU_REAL_WEIGHTS_TRAINED_V1_20261022.zip',
            'Packages/P04/train_qlora.py','Packages/P04/preflight_local_gpu.py',
            'Packages/P04/merge_qlora_adapter.py')) {
            if (-not $seenRuntime.Contains($required)) { throw ('ONEHOST_RUNTIME_DATA_MISSING:'+ $required) }
        }
        $nativeArgs += @((Join-Path $source 'run_helion.py'))
        & $venvPython @nativeArgs
        if ($LASTEXITCODE -ne 0) { throw 'ONEHOST_NATIVE_PYINSTALLER_FAILED' }
        $nativeExe = Join-Path $output 'NOX_HELION_PRIVATE_CANDIDATE.exe'
        if (-not (Test-Path -LiteralPath $nativeExe -PathType Leaf)) { throw 'ONEHOST_NATIVE_EXE_MISSING' }
        $dataReceipt = Join-Path $evidence 'onehost-native-stage.json'
        $nativeStage | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $dataReceipt -Encoding UTF8
        # Check the actual built archive entries, not just the staging folder.
        $archiveCheck = 'import hashlib,json,sys; from PyInstaller.archive.readers import CArchiveReader; a=CArchiveReader(sys.argv[1]); r=json.load(open(sys.argv[2],encoding="utf-8-sig")); names={n.replace(chr(92),"/"):n for n in a.toc}; [(None if x["runtime_path"] in names and hashlib.sha256(a.extract(names[x["runtime_path"]])).hexdigest()==x["sha256"] else (_ for _ in ()).throw(RuntimeError("BUNDLED_RUNTIME_DATA_SHA_MISMATCH:"+x["runtime_path"]))) for x in r["runtime_data_files"]]; print("ONEHOST_BUNDLED_RUNTIME_DATA_SHA_PASS")'
        & $venvPython -I -c $archiveCheck $nativeExe $dataReceipt
        if ($LASTEXITCODE -ne 0) { throw 'ONEHOST_BUNDLED_RUNTIME_DATA_HOLD' }
        $oneHostReceipt = [ordered]@{
            schema = 'NOX-ONEHOST-PYTHON-BUILD-V1'
            source_commit = $checkoutCommit; source_tree = $checkoutTree; run_id = $RunId
            original_archive_sha256 = $sourceExpectedSha
            source_original_archive_sha256 = $sourceExpectedSha
            original_archive_path = $sourceZip
            staged_original_app_sha256 = $nativeStage.staged_app_sha256
            staged_original_app_path = (Join-Path $source 'helion/app.py')
            python_exe = $nativeExe
            python_exe_sha256 = (Get-FileHash -LiteralPath $nativeExe -Algorithm SHA256).Hash.ToLowerInvariant()
            entrypoint = 'run_helion.py'; console_stdio = $true; python_host_count = 1
            native_stage = $nativeStage; runtime_data_files = $oneHostData
            bundled_runtime_data_verified = $true
            native_stdio_smoke = 'NOT_RUN'; release_accepted = $false
        }
        $oneHostReceipt | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $output 'ONEHOST_PYTHON_BUILD_RECEIPT.json') -Encoding UTF8
    } else {
        & (Join-Path $source 'C_RELEASE_SPRINT_BUILD.ps1') -OutputDirectory $output -AuthorizedIsolatedWindowsVM -FastCandidate
        if ($LASTEXITCODE -ne 0) { throw "C_RELEASE_SPRINT_BUILD_FAILED:$LASTEXITCODE" }
    }
} catch {
    $failure = ($_ | Out-String).Trim()
    Write-Error $failure
} finally {
    if (Test-Path -LiteralPath $output -PathType Container) {
        $exeRecords = @(Get-ChildItem -LiteralPath $output -Filter '*.exe' -File -ErrorAction SilentlyContinue | ForEach-Object {
            [ordered]@{name=$_.Name;bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
        })
    }
    $cReceiptPath = Join-Path $output 'C_RELEASE_SPRINT_BUILD_RECEIPT.json'
    if (Test-Path -LiteralPath $cReceiptPath -PathType Leaf) {
        try {
            $cReceipt = Get-Content -LiteralPath $cReceiptPath -Raw | ConvertFrom-Json
            $fastModeProp = $cReceipt.PSObject.Properties['fast_candidate_mode']
            if ($null -eq $fastModeProp) { throw 'FAST_CANDIDATE_RECEIPT_FLAG_MISSING' }
            $fastModeValue = $fastModeProp.Value
            if ($fastModeValue -isnot [bool]) {
                $isPresentProp = $null
                if ($null -ne $fastModeValue) { $isPresentProp = $fastModeValue.PSObject.Properties['IsPresent'] }
                if ($null -eq $isPresentProp -or $isPresentProp.Value -isnot [bool]) {
                    throw 'FAST_CANDIDATE_RECEIPT_FLAG_INVALID'
                }
                $fastModeProp.Value = [bool]$isPresentProp.Value
            }
            $cReceipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $cReceiptPath -Encoding UTF8
            $cReceipt = Get-Content -LiteralPath $cReceiptPath -Raw | ConvertFrom-Json
            if ($cReceipt.schema -ceq 'NOX_C_RELEASE_SPRINT_BUILD_RECEIPT_V2') {
                $sourceQaStatus = [string]$cReceipt.source_qa_status
                $nativeSmokeStatus = [string]$cReceipt.native_smoke_status
                $receiptValid = ($cReceipt.exe_artifacts.Count -eq 2 -and
                    $cReceipt.fast_candidate_mode -is [bool] -and $cReceipt.fast_candidate_mode -eq $true -and
                    $cReceipt.release_accepted -is [bool] -and $cReceipt.release_accepted -eq $false -and
                    $cReceipt.release_v1_pass -is [bool] -and $cReceipt.release_v1_pass -eq $false)
            }
        } catch { $receiptValid = $false }
    }
    $fastCandidateComplete = ($receiptValid -and $sourceQaStatus -eq 'NOT_RUN' -and
        $nativeSmokeStatus -eq 'NOT_RUN' -and $exeRecords.Count -eq 2)
    $finished = [DateTime]::UtcNow
    if ($null -ne $failure) { $runStatus = 'INCOMPLETE_OR_FAILED' }
    elseif ($OneHostNative -and $null -ne $oneHostReceipt) { $runStatus = 'ONEHOST_NATIVE_BACKEND_BUILT_SMOKE_NOT_RUN' }
    elseif ($fastCandidateComplete) { $runStatus = 'PREPRE_FAST_CANDIDATE_BUILT_QA_NOT_RUN' }
    elseif ($receiptValid) { $runStatus = 'BUILD_SCRIPT_RETURNED_SUCCESS' }
    else { $runStatus = 'INCOMPLETE_OR_FAILED' }
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
        source_qa_status=$sourceQaStatus
        native_smoke_status=$nativeSmokeStatus
        fast_candidate_mode=$fastCandidateSelected
        onehost_native_mode=[bool]$OneHostNative
        onehost_runtime_data=$oneHostData
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
        $(if ($OneHostNative) { 'ONEHOST NATIVE PYTHON BACKEND; WINDOWS ACCEPTANCE PENDING' } else { 'PRE-RELEASE WINDOWS CANDIDATE BUILD' })
        "status: $runStatus"
        "release_accepted: false"
        "SOURCE_QA=$sourceQaStatus"
        "NATIVE_SMOKE=$nativeSmokeStatus"
        "fast_candidate_mode=$fastCandidateSelected"
        "executables_observed: $($exeRecords.Count)"
        "source_base_tree: $baseTree"
        "source_patched_tree: $patchedTree"
        "failure: $failure"
    ) -join [Environment]::NewLine
    Set-Content -LiteralPath (Join-Path $output 'BUILD_STATUS.txt') -Value $statusText -Encoding UTF8
    $candidateReadme = @(
        $(if ($OneHostNative) { 'Single OneHost native-stdio Python backend; release_accepted=false.' } else { 'PRE-PRE fast diagnostic candidate; release_accepted=false.' })
        "SOURCE_QA=$sourceQaStatus"
        "NATIVE_SMOKE=$nativeSmokeStatus"
        "fast_candidate_mode=$fastCandidateSelected"
        "run_id: $env:GITHUB_RUN_ID"
        "source_base_tree: $baseTree"
        "source_patched_tree: $patchedTree"
        "qa_requirements_sha256: $qaLockSha"
        "qa_dependencies_ready: $qaDependenciesReady"
        "qa_dependency_failure: $qaDependencyFailure"
        $(if ($OneHostNative) { 'Check ONEHOST_PYTHON_BUILD_RECEIPT.json and build-attempt.json for runtime data and actual EXE SHA; separate native smoke is mandatory.' } else { 'Check C_RELEASE_SPRINT_BUILD_RECEIPT.json and build-attempt.json for exact gates and EXE SHA values.' })
        'Real local-model inference through the GUI, Persona/history/STOP, full rights and independent acceptance remain unverified unless separately evidenced.'
    ) -join [Environment]::NewLine
    Set-Content -LiteralPath (Join-Path $output 'CANDIDATE_README.txt') -Value $candidateReadme -Encoding UTF8
    try { Stop-Transcript | Out-Null } catch {}
}

if ($null -ne $failure) { throw $failure }
