# NOX PRIME V9 single HOME / chat / experience / SOUL boot - no GPU training.
# Windows PowerShell 5.1, ASCII-only. Use after git archive of exact SourceSha.
param([Parameter(Mandatory=$true)][ValidatePattern('^[a-f0-9]{40}$')][string]$SourceSha)
$ErrorActionPreference = "Stop"
$root = "C:\NOX_HELION\NOX_NEW"
$repo = "$root\brain\source\repo"
$python = Join-Path $env:USERPROFILE "NOX_EXPRESS_AI\NOX_TRAINING\train-venv\Scripts\python.exe"
$source = Split-Path -Parent $MyInvocation.MyCommand.Path

if (!(Test-Path "$repo\.git")) { throw "Existing canonical repository not found" }
if (!(Test-Path "$root\brain")) { throw "NOX root not found" }
if (!(Test-Path $python)) { throw "Existing NOX Python environment not found" }
if (!(Test-Path "$source\forge_live_server_v6.py")) {
    throw "Source must be run from exact versioned source archive"
}
$actualCommit = (& git -C $repo rev-parse $SourceSha).Trim()
if ($LASTEXITCODE -ne 0 -or $actualCommit -ne $SourceSha) {
    throw "Invalid/pinned Git source sha"
}

# Only SOURCE checks are run here, never model training or writing to S03.
$modules = @(
 "forge_live_server_v6.py",
 "nox_unified_brain_v1.py",
 "nox_prime_resource_advisor_v1.py",
 "nox_prime_cognitive_memory_v1.py",
 "nox_prime_semantic_retriever_v1.py",
 "nox_prime_memory_continuum_v1.py",
 "nox_prime_experience_v1.py",
 "nox_prime_core_matrix_v1.py",
 "nox_prime_dream_v1.py",
 "nox_prime_affect_runtime_v1.py",
 "nox_prime_self_edit_lab_v1.py",
 "nox_prime_forge_job_v1.py",
 "nox_prime_autonomous_router_v1.py",
 "nox_prime_weight_audit_v1.py",
 "nox_prime_unified_self_v51.py",
 "nox_prime_absorption_registry_v1.py",
 "nox_prime_absorb_text_v2.py",
 "nox_prime_progress_v1.py",
 "nox_prime_distill_v1.py",
 "nox_prime_student_dataset_v1.py",
 "nox_prime_soul_stage1_train.py"
)
foreach ($name in $modules) {
    if (!(Test-Path (Join-Path $source $name))) { throw "MISSING_SOURCE: $name" }
}
$paths = @($modules | ForEach-Object { Join-Path $source $_ })
& $python -m py_compile @paths
if ($LASTEXITCODE -ne 0) { throw "Python source syntax check failed" }
Push-Location $source
try {
    $tests = @(
      "test_nox_unified_brain_v1",
      "test_nox_prime_resource_advisor_v1",
      "test_nox_prime_cognitive_memory_v1",
      "test_nox_prime_semantic_retriever_v1",
      "test_nox_prime_memory_continuum_v1",
      "test_nox_prime_experience_v1",
      "test_nox_prime_core_matrix_v1",
      "test_nox_prime_dream_v1",
      "test_nox_prime_affect_runtime_v1",
      "test_nox_prime_self_edit_lab_v1",
      "test_nox_prime_autonomous_router_v1",
      "test_nox_prime_unified_self_v51",
      "test_nox_prime_absorption_v2",
      "test_nox_prime_student_dataset_v1",
      "test_nox_prime_progress_v1",
      "test_nox_prime_live_pipeline_v1"
    )
    & $python -m unittest -q @tests
    if ($LASTEXITCODE -ne 0) { throw "PRIME integrated SOURCE contract tests failed" }
}
finally { Pop-Location }

$server = Join-Path $source "forge_live_server_v6.py"
$ui = Join-Path $source "nox_unified_chat_v1.html"
if (!(Test-Path $ui)) { throw "NOX PRIME V9 HOME UI MISSING" }
$expected = (Get-FileHash -Algorithm SHA256 $server).Hash.ToLowerInvariant()
$expectedUI = (Get-FileHash -Algorithm SHA256 $ui).Hash.ToLowerInvariant()
$selected = $null
foreach ($port in 18880..18896) {
    $url = "http://127.0.0.1:$port/"
    $health = $null
    try { $health = Invoke-RestMethod ($url+"api/health") -TimeoutSec 2 } catch {}
    if ($health -and $health.unified_router -eq "NOX-UNIFIED-BRAIN-V6" -and
        $health.source_sha256 -eq $expected -and
        $health.chat_ui_sha256 -eq $expectedUI -and
        $health.page_schema -eq "NOX-PRIME-HOME-V9") {
        $selected = $url
        Write-Host "Reusing exact-source NOX PRIME server on $port"
        break
    }
    $occupied = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    if ($occupied.Count -gt 0) { continue }
    $outlog = Join-Path $source ("server_"+$port+".out")
    $errlog = Join-Path $source ("server_"+$port+".err")
    $args = @("-u",$server,"--root",$root,"--port",[string]$port,"--source-sha",$SourceSha)
    Start-Process -FilePath $python -ArgumentList $args -WorkingDirectory $source -WindowStyle Hidden -RedirectStandardOutput $outlog -RedirectStandardError $errlog | Out-Null
    for ($n=0; $n -lt 35; $n++) {
        Start-Sleep -Milliseconds 450
        try {
            $health = Invoke-RestMethod ($url+"api/health") -TimeoutSec 2
            if ($health.unified_router -eq "NOX-UNIFIED-BRAIN-V6" -and
                $health.source_sha256 -eq $expected -and
        $health.chat_ui_sha256 -eq $expectedUI -and
        $health.page_schema -eq "NOX-PRIME-HOME-V9") {
                $selected = $url
                break
            }
        }
        catch {}
    }
    if ($selected) { break }
    if (Test-Path $errlog) { Get-Content $errlog -Tail 30 }
}
if (!$selected) {
    throw "NOX PRIME V6 live server not accepted; old servers and S03 remain untouched"
}
$core = Invoke-RestMethod ($selected+"api/nox/status") -TimeoutSec 15
$history = Invoke-RestMethod ($selected+"api/nox/history") -TimeoutSec 15
$soul = Invoke-RestMethod ($selected+"api/nox/soul/status") -TimeoutSec 15
$cognition = Invoke-RestMethod ($selected+"api/nox/cognition/status") -TimeoutSec 15
$experience = Invoke-RestMethod ($selected+"api/nox/experience") -TimeoutSec 15
$cores = Invoke-RestMethod ($selected+"api/nox/cores") -TimeoutSec 15
if (!$core.primary_model) { throw "No installed Ollama primary model; source is ready, inference HOLD" }
if (!$cognition.layers -or $null -eq $experience.count -or @($cores.core_ids).Count -ne 8) {
    throw "Cognitive memory endpoints not ready"
}
Write-Host ("NOX CORE: "+$core.primary_model) -ForegroundColor Green
Write-Host ("SOUL candidate accepted: "+$soul.available+" | scope "+$soul.scope)
Write-Host ("Persisted chat messages restored: "+@($history.messages).Count)
Write-Host ("Autobiography transcript episodes: "+$experience.count)
Write-Host "S03 authority: native only; chat writes remain HOLD until OneHost approval"
Write-Host ("NOX PRIME V9 HOME: "+$selected) -ForegroundColor Green
Write-Host ("Source SHA: "+$SourceSha+" | Server hash: "+$expected.Substring(0,12)+" | UI hash: "+$expectedUI.Substring(0,12))
Write-Host "Previous browser tabs can still show old NOX. Use this exact new URL." -ForegroundColor Yellow
Start-Process ($selected+"?nox=v9&ui="+$expectedUI.Substring(0,12))
