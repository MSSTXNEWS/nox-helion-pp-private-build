# NOX V16 · pre-SOURCE_READY Windows test harness ONLY, original GitLab final
# builder stays in gitlab_windows_entrypoint.ps1 and requires signed T10.
# No installers, models, training, downloads, real system control, or EXE build.
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repo = (Get-Location).Path
$reportDir = Join-Path $repo 'work/gitlab-qa'
New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
$reportPath = Join-Path $reportDir 'NOX_WINDOWS_SOURCE_QA.json'
$cases = New-Object 'System.Collections.Generic.List[object]'
$startUtc = [DateTime]::UtcNow.ToString('o')
$head = ''
$reason = 'UNKNOWN'

function Write-QAReceipt([string]$Disposition, [string]$Reason) {
    $receipt = [ordered]@{
      schema = 'NOX_V16_WINDOWS_SOURCE_QA_V1'
      mode = 'WINDOWS_SOURCE_QA_NOT_FINAL_EXE'
      runId = [string]$env:CI_PIPELINE_ID
      gitCommit = $head
      gitlabRef = [string]$env:CI_COMMIT_REF_NAME
      startedUtc = $startUtc
      endedUtc = [DateTime]::UtcNow.ToString('o')
      disposition = $Disposition
      reason = $Reason
      checks = @($cases.ToArray())
      independentT08Accepted = $false
      nativeRoutesAccepted = 0
      nativeRoutesPending = 14
      sourceReady = $false
      e07Accepted = $false
      windowsInstalledExe = 'NOT_RUN'
      sourceLock729 = 'NOT_ATTESTED_BY_THIS_JOB'
    }
    $raw = $receipt | ConvertTo-Json -Depth 8
    [IO.File]::WriteAllText($reportPath, $raw + [Environment]::NewLine,
                          (New-Object System.Text.UTF8Encoding($false)))
}
function Invoke-SourceCheck([string]$Label, [string]$Executable, [string[]]$Arguments) {
    $binary = Get-Command -Name $Executable -CommandType Application -ErrorAction SilentlyContinue |
              Select-Object -First 1
    if ($null -eq $binary) {
        $cases.Add([ordered]@{name=$Label;status='NOT_RUN';exitCode=$null;
                             reason='REQUIRED_QA_TOOL_UNAVAILABLE'}) | Out-Null
        return
    }
    $code = 1
    $status = 'FAIL'
    $detail = 'NONZERO_EXIT'
    try {
        # Runner-local, source-only suites, no arbitrary command text or shell interpolation.
        & $binary.Source @Arguments
        $code = [int]$LASTEXITCODE
        if ($code -eq 0) { $status = 'PASS'; $detail = '' }
    } catch {
        # Return error category only, never emit paths, secrets or raw exception text.
        $code = 1
        $detail = 'TEST_PROCESS_ERROR'
    }
    $cases.Add([ordered]@{name=$Label;status=$status;exitCode=$code;reason=$detail}) |
       Out-Null
}
try {
    if ($env:CI_PIPELINE_SOURCE -cnotin @('web','api') -or
        $env:NOX_APPROVE_WINDOWS_QA -cne 'YES' -or
        $env:NOX_APPROVE_WINDOWS_BUILD -ceq 'YES') {
        throw 'QA_MANUAL_ONLY_APPROVAL_REQUIRED'
    }
    if ($env:NOX_QA_SOURCE_SHA -cnotmatch '^[0-9a-f]{40}$' -or
        $env:CI_COMMIT_SHA -cnotmatch '^[0-9a-f]{40}$' -or
        $env:NOX_QA_SOURCE_REF -cnotmatch '^[A-Za-z0-9._/-]{3,128}$' -or
        $env:NOX_QA_SOURCE_REF -match '(^/|/$|//|\.\.)' -or
        $env:CI_COMMIT_REF_NAME -cne $env:NOX_QA_SOURCE_REF) {
        throw 'QA_PIN_INVALID_OR_REF_MISMATCH'
    }
    $head = [string](& git -C $repo rev-parse HEAD)
    if ($LASTEXITCODE -ne 0 -or $head.Trim().ToLowerInvariant() -cne
        $env:CI_COMMIT_SHA.ToLowerInvariant() -or
        $head.Trim().ToLowerInvariant() -cne $env:NOX_QA_SOURCE_SHA.ToLowerInvariant()) {
        throw 'QA_FROZEN_HEAD_MISMATCH'
    }
    $head = $head.Trim().ToLowerInvariant()
    if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) {
        throw 'QA_WINDOWS_HOST_REQUIRED'
    }
    # Source-only: all test files are from the immutable verified checkout.
    # No external package downloads and no destructive native commands.
    Invoke-SourceCheck 'P01_OWNER_PYTHON' 'python' @(
      '-m','unittest','discover','-s','proposals/NOX-PACK01-50',
      '-p','test_p01_windows_owner_ports.py','-v')
    Invoke-SourceCheck 'P02_OWNER_PYTHON' 'python' @(
      '-m','unittest','discover','-s','Packages/P02/worker-python',
      '-p','test_p02_owner_route_ports.py','-v')
    Invoke-SourceCheck 'P04_SNAPSHOT_PYTHON' 'python' @(
      '-m','unittest','discover','-s','tests/P04',
      '-p','test_model_snapshot_probe.py','-v')
    Invoke-SourceCheck 'P03_PRIVACY_NODE' 'node' @(
      '--test','coordination/automation/r30/G3-B/tests/G3B-20261030T013611MSK-R26-P03-ACK-PRIVACY.test.mjs')
    Invoke-SourceCheck 'PACK02_CSV_NODE' 'node' @(
      '--test','proposals/NOX-PACK02-50/test_csv_schema_r37.mjs')
    Invoke-SourceCheck 'P05_SPACE_125_NODE' 'node' @(
      'Packages/P05/E05/space/E05SpaceReadOnlyProjection.test.mjs')
    Invoke-SourceCheck 'P05_STOP_HISTORY_NODE' 'node' @(
      '--test','Packages/P05/E05/space/E05SpaceRunErrorHistoryR15.test.mjs')
    # Compile the original P04 net8 library, never an intermediate EXE or installer.
    Invoke-SourceCheck 'P04_LIBRARY_COMPILE' 'dotnet' @(
      'build','Packages/P04/NoxP04.csproj','-c','Release',
      '--nologo','-v','quiet','-p:RestoreIgnoreFailedSources=true')
    if (@($cases | Where-Object {$_.status -ne 'PASS'}).Count -gt 0 -or
        $cases.Count -ne 8) {
        $reason = 'SOME_SOURCE_SUITES_FAILED_OR_NOT_RUN'
        Write-QAReceipt 'SOURCE_QA_HOLD' $reason
        exit 2
    }
    $reason = 'SOURCE_ONLY_TESTS_PASS_NATIVE_NOT_RUN'
    Write-QAReceipt 'SOURCE_QA_LIMITED_PASS' $reason
    exit 0
} catch {
    $reason = 'FAIL_CLOSED_GIT_PIN_OR_HOST_PRECONDITION'
    Write-QAReceipt 'SOURCE_QA_HOLD' $reason
    exit 2
}
