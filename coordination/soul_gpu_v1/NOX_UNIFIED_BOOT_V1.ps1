# NOX HELION Unified Brain V1 + SAFE70 WORM.
# Canonical S03 and old LoRA weights are NEVER modified by this installer.
$ErrorActionPreference = "Stop"
$root = "C:\NOX_HELION\NOX_NEW"
$repo = "$root\brain\source\repo"
$ref = "1b0960a45b58423506bc5121c315add4962d7eab"
$base = "coordination/soul_gpu_v1"
$dest = "$root\brain\skills\NOX_UNIFIED_49fca983"
$python = "$env:USERPROFILE\NOX_EXPRESS_AI\NOX_TRAINING\train-venv\Scripts\python.exe"
if (!(Test-Path $python)) { throw "NOX DirectML Python environment not found" }
if (!(Test-Path "$repo\.git")) { throw "NOX Git repository missing" }
$git = (Get-Command git -ErrorAction Stop).Source
$busy = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^python(?:w)?\.exe$' -and
    $_.CommandLine -match 'train_directml_lora[.]py|nox_gpu_safe65_v2[.]py|nox_gpu_10000[.]py|nox_gpu_target_11120[.]py|nox_gpu_worm_safe70_v1[.]py'
})
New-Item -ItemType Directory -Force $dest | Out-Null
Write-Host "NOX UNIFIED: fetching pinned Git source" -ForegroundColor Cyan
& $git -C $repo fetch origin $ref
if ($LASTEXITCODE -ne 0) { throw "Git fetch failed" }
$files = @(
 "forge_wow_live_v6.html","forge_live_server_v6.py",
 "forge_genesis_server_v8.py","forge_actual_telemetry_v1.py",
 "nox_thermal_sensors_v1.py","forge_focus_v4_canonical_live.html",
 "nox_unified_brain_v1.py","nox_unified_chat_v1.html",
 "nox_prime_resource_advisor_v1.py",
 "nox_gpu_target_11120.py","nox_gpu_worm_safe70_v1.py",
 "test_nox_unified_brain_v1.py","test_nox_prime_resource_advisor_v1.py"
)
foreach ($name in $files) {
    $objectPath = "$base/$name"
    $objectRef = $ref + ":" + $objectPath
    $expected = (& $git -C $repo rev-parse $objectRef).Trim()
    if ($LASTEXITCODE -ne 0 -or $expected -notmatch '^[a-f0-9]{40}$') {
        throw "Missing Git blob: $name"
    }
    $target = Join-Path $dest $name
    $tmp = "$target.tmp"
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $git
    $start.Arguments = '-C "' + $repo + '" show ' + $objectRef
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.UseShellExecute = $false
    $p = [Diagnostics.Process]::Start($start)
    try {
        $stream = [IO.File]::Create($tmp)
        try { $p.StandardOutput.BaseStream.CopyTo($stream) }
        finally { $stream.Dispose() }
        $p.WaitForExit()
        if ($p.ExitCode -ne 0) { throw "Git show failed: $name" }
        $actual = (& $git -C $repo hash-object $tmp).Trim()
        if ($actual -ne $expected) { throw "Git blob integrity mismatch: $name" }
        Move-Item $tmp $target -Force
        Write-Host "Verified: $name" -ForegroundColor Green
    }
    finally {
        if (!$p.HasExited) { $p.Kill(); $p.WaitForExit() }
        $p.Dispose()
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
}
& $python -m py_compile "$dest\forge_live_server_v6.py" $dest\nox_unified_brain_v1.py" "$dest\nox_prime_resource_advisor_v1.py" "$dest\nox_gpu_target_11120.py" "$dest\nox_gpu_worm_safe70_v1.py"
if ($LASTEXITCODE -ne 0) { throw "Python syntax validation failed" }
Push-Location $dest
try {
    & $python -m unittest -q test_nox_unified_brain_v1 test_nox_prime_resource_advisor_v1
    if ($LASTEXITCODE -ne 0) { throw "Unified brain contract tests failed" }
} finally { Pop-Location }

# One FORGE server, one identity router, and no GPU commands from the browser.
$selected = $null
foreach ($port in 18880..18888) {
    $url = "http://127.0.0.1:$port/"
    $health = $null
    try { $health = Invoke-RestMethod ($url+"api/health") -TimeoutSec 2 } catch {}
    if ($health -and $health.unified_router -eq "NOX-UNIFIED-BRAIN-V4") {
        $selected = $url
        break
    }
    $occupied = @(Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
    if ($occupied.Count -gt 0) { continue }
    $args = @("-u",('"'+$dest+'\forge_live_server_v6.py"'),"--root",('"'+$root+'"'),"--port",[string]$port)
    Start-Process -FilePath $python -ArgumentList $args -WorkingDirectory $dest -RedirectStandardOutput "$dest\server_$port.log" -RedirectStandardError "$dest\server_$port.err" -WindowStyle Hidden | Out-Null
    for ($i=0; $i -lt 30; $i++) {
        Start-Sleep -Milliseconds 500
        try {
            $health = Invoke-RestMethod ($url+"api/health") -TimeoutSec 2
            if ($health.unified_router -eq "NOX-UNIFIED-BRAIN-V2") {
                $selected = $url
                break
            }
        } catch {}
    }
    if ($selected) { break }
    if (Test-Path "$dest\server_$port.err") { Get-Content "$dest\server_$port.err" -Tail 16 }
}
if (!$selected) { throw "NOX unified server failed. Training not launched." }
$brain = Invoke-RestMethod ($selected+"api/nox/status") -TimeoutSec 15
if ($brain.version -ne "UNIFIED-BRAIN-V1") { throw "Wrong NOX router version" }
Start-Process ($selected+"nox/chat")
Write-Host ("NOX UNIFIED CHAT: "+$selected+"nox/chat") -ForegroundColor Green
Write-Host ("Primary LLM: "+$brain.primary_model)
Write-Host ("Coding LLM: "+$brain.code_model)
Write-Host ("Last LoRA checkpoint: "+$brain.last_lora_checkpoint.step)
Write-Host "S03 writes: NOT CONNECTED; weights: NOT physically merged" -ForegroundColor Yellow
if (!$brain.primary_model) { throw "Ollama has no accessible local models. Training not launched." }
if ($busy.Count -gt 0) {
    Write-Host "NOX GPU process is already running; no duplicate training launched." -ForegroundColor Yellow
    $busy | Select-Object ProcessId,CommandLine | Format-List
    return
}
Write-Host "NOX SAFE70 WORM: resume latest valid LoRA checkpoint to goal 11120" -ForegroundColor Cyan
Write-Host "Hot Spot STOP>=70C; restart below65C; preserve old LoRA weights" -ForegroundColor Yellow
& $python -u "$dest\nox_gpu_worm_safe70_v1.py"
if ($LASTEXITCODE -ne 0) { throw "NOX WORM halted early. See HALT above. Saved weights intact." }
Write-Host "NOX SAFE70 GOAL COMPLETED" -ForegroundColor Green
