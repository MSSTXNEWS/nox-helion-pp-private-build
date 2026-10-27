# NOX P04 component gate, no GPU/model download. Run in PowerShell 7 or Windows PowerShell.
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$project = Join-Path $PSScriptRoot "NoxP04.csproj"
$tests = Join-Path $root "tests/P04"
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
Write-Output "P04_COMPONENT_STATIC_GATE_PASS; runtime/GPU/Windows host acceptance NOT RUN"
