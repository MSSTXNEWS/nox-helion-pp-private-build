# NOX P04 isolated component verification; no runtime weights or downloads.
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
Write-Output "P04_SOURCE_COMPONENT_CHECKS_PASS; live Ollama/GPU/Windows acceptance NOT RUN"
