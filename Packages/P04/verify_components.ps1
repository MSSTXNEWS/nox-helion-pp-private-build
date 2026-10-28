# NOX P04 isolated component verification; no runtime weights or downloads.
# Supply -P02SourceDir to verify the exact native P02/P04 cross-owner interface.
param([string]$P02SourceDir = "")
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$tests = Join-Path $root "tests/P04"
$project = Join-Path $PSScriptRoot "NoxP04.csproj"
$harness = Join-Path $tests "RagComponentHarness.csproj"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "HOLD_PYTHON_NOT_INSTALLED"; exit 3
}
& python -m unittest discover -s $tests -p "test_*.py" -v
if ($LASTEXITCODE -ne 0) { Write-Error "P04_PYTHON_TESTS_FAILED"; exit 1 }
if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    Write-Error "HOLD_DOTNET_8_SDK_NOT_INSTALLED"; exit 3
}
& dotnet build $project -c Release --nologo
if ($LASTEXITCODE -ne 0) { Write-Error "P04_DOTNET_BUILD_FAILED"; exit 1 }
& dotnet run --project $harness -c Release --no-restore
if ($LASTEXITCODE -ne 0) { Write-Error "P04_RAG_FIXTURE_FAILED"; exit 1 }
if ($P02SourceDir) {
    # Do not accept arbitrary webpage paths: #6 must provide an approved local
    # source directory containing the exactly pinned P02 Python owner sources.
    if (-not (Test-Path -LiteralPath $P02SourceDir -PathType Container)) {
        Write-Error "HOLD_P02_SOURCE_REQUIRED"; exit 3
    }
    $p02 = (Resolve-Path -LiteralPath $P02SourceDir).Path
    $files = @{
        "p02_runtime.py" = "98b06e6f12c3ec0c9119c96a9539972c6964c0ef3e05e0bd788990c2be437edf"
        "p02_chat_bridge.py" = "18d1aad8f071f28d4e89a6607e96e9afabc7d0dc5352c6ea559e6099c77abf39"
    }
    foreach ($name in @("p02_runtime.py", "p02_chat_bridge.py")) {
        $full = Join-Path $p02 $name
        if (-not (Test-Path -LiteralPath $full -PathType Leaf)) {
            Write-Error "HOLD_PINNED_P02_SOURCE_FILE_MISSING"; exit 3
        }
        $actual = (Get-FileHash -LiteralPath $full -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($actual -ne $files[$name]) {
            Write-Error "HOLD_PINNED_P02_SOURCE_SHA256_MISMATCH"; exit 3
        }
    }
    $prior = $env:NOX_P02_SOURCE_DIR
    try {
        $env:NOX_P02_SOURCE_DIR = $p02
        & python -m unittest discover -s $tests -p "test_p02*.py" -v
        if ($LASTEXITCODE -ne 0) {
            Write-Error "P04_P02_CROSS_OWNER_TEST_FAILED"; exit 1
        }
    }
    finally {
        $env:NOX_P02_SOURCE_DIR = $prior
    }
    Write-Output "P02_P04_CROSS_OWNER_COMPONENT_PASS; installed Ollama / Windows IPC NOT RUN"
}
else {
    Write-Output "P02_P04_CROSS_OWNER_NOT_RUN; pass -P02SourceDir for source QA"
}
Write-Output "P04_SOURCE_COMPONENT_CHECKS_PASS; live Ollama/GPU/Windows acceptance NOT RUN"
