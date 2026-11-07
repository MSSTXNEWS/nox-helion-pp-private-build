# NOX HELION WEB · Shell launcher (not Windows EXE)
# instructions_version 0.0.6 · local-only, no downloads, no model changes
[CmdletBinding()]
param(
    [string]$Root = 'C:\NOX_HELION',
    [ValidateRange(1024,65535)][int]$Port = 18775,
    [switch]$ProbeOnly,
    [switch]$NoBrowser
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$url = "http://127.0.0.1:$Port/"

function Test-NoxWeb([string]$Address) {
    try {
        $r = Invoke-WebRequest -Uri $Address -UseBasicParsing -TimeoutSec 3 -MaximumRedirection 0
        $t = [string]$r.Content
        if ($r.StatusCode -ne 200 -or [string]$r.Headers['Content-Type'] -notmatch 'html') { return $false }
        if ($t -notmatch '(?i)NOX[\s._-]*HELION') { return $false }
        foreach($re in @('(?i)(CHAT|ЧАТ|QWEN)', '(?i)(MEMORY|ПАМЯТ|SQLITE)', '(?i)(MODEL|МОДЕЛ|OLLAMA|TRAINING|ОБУЧЕНИЕ)')) {
            if ($t -notmatch $re) { return $false }
        }
        if ($t -match '(?i)(NOX_STATIC_DEMO_ONLY|NOX_MOCK_MODE|NOX_FAKE_BACKEND)') { return $false }
        return $true
    } catch { return $false }
}
function Show-NoxProvider {
    foreach($p in @(11434,11436)) {
        try {
            $models = Invoke-RestMethod "http://127.0.0.1:$p/api/tags" -TimeoutSec 2
            Write-Host "Ollama localhost:$p online · models: $(@($models.models).Count)" -ForegroundColor Cyan
            return
        } catch { }
    }
    Write-Warning 'OLLAMA_PROVIDER_OFFLINE_HOLD: real CHAT may not yet be available'
}
function Get-PortOwners([int]$P) {
    try { return @(Get-NetTCPConnection -LocalPort $P -State Listen -ErrorAction Stop |
                Select-Object -ExpandProperty OwningProcess -Unique) }
    catch { return @() }
}

if(Test-NoxWeb $url) {
    Write-Host "NOX WEB verified on $url" -ForegroundColor Green
    Show-NoxProvider
    if(-not $NoBrowser){Start-Process $url}
    return
}
$owners = @(Get-PortOwners $Port)
if($owners.Count) {
    throw "PORT_OCCUPIED_UNVERIFIED_HOLD ($Port / PID $($owners -join ',')): not starting duplicate or opening old demo."
}
if($ProbeOnly) { Write-Warning 'NOX_WEB_NOT_RUNNING_HOLD'; return }
if(-not (Test-Path -LiteralPath $Root -PathType Container)){throw "NOX_ROOT_NOT_FOUND_HOLD: $Root"}

$dirs = @(
    (Join-Path $Root 'NOX_NEW\WEB'),
    (Join-Path $Root 'APP\NOX_WEB'),
    (Join-Path $Root 'NOX_WEB'),
    (Join-Path $Root 'WEB'),
    (Join-Path $Root 'NOX_NEW'),
    $Root
) | Select-Object -Unique

$sources = @()
foreach($dir in $dirs) {
    $package = Join-Path $dir 'package.json'
    if(-not (Test-Path -LiteralPath $package -PathType Leaf)) { continue }
    try {$j = Get-Content -LiteralPath $package -Raw -Encoding UTF8 | ConvertFrom-Json}
    catch {continue}
    if(([string]$j.name + ' ' + [string]$j.description) -notmatch '(?i)(nox[\s._-]*helion|nox[\s._-]*web)'){continue}
    if(-not (Test-Path -LiteralPath (Join-Path $dir 'node_modules') -PathType Container)){
        Write-Warning "NOX_WEB_DEPENDENCIES_HOLD: $dir; no automatic downloads"
        continue
    }
    $chosen = @('start:web','web','dev','start') | Where-Object {
        $j.scripts -and $j.scripts.PSObject.Properties.Name -contains $_
    } | Select-Object -First 1
    if(-not $chosen){continue}
    $text = [string]$j.scripts.$chosen
    if($text -match '(?i)(demo|mock|storybook|preview|electron|tauri|\.exe\b|powershell|curl\b|wget\b|&&|\|\||;)'){continue}
    if($text -notmatch '(?i)(next|vite|node)'){continue}
    $sources += [pscustomobject]@{Dir=$dir; Command=$text; Script=$chosen}
}
if($sources.Count -ne 1){throw "NOX_WEB_SOURCE_AMBIGUOUS_OR_MISSING_HOLD: validated projects = $($sources.Count)"}
$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if(-not $npm){throw 'NPM_MISSING_HOLD: no software installed'}
$project = $sources[0]
$oldPort=$env:PORT; $oldHost=$env:HOST
try {
    $env:PORT=[string]$Port; $env:HOST='127.0.0.1'
    $argsList = @('run',$project.Script)
    if($project.Command -match '(?i)\bvite\b'){$argsList += @('--','--host','127.0.0.1','--port',[string]$Port)}
    elseif($project.Command -match '(?i)\bnext\b'){$argsList += @('--','-H','127.0.0.1','-p',[string]$Port)}
    $process = Start-Process -FilePath $npm.Source -ArgumentList $argsList -WorkingDirectory $project.Dir -PassThru
} finally {$env:PORT=$oldPort; $env:HOST=$oldHost}

$ok=$false
for($i=0;$i -lt 30;$i++) {
    if($process.HasExited){break}
    if(Test-NoxWeb $url){$ok=$true;break}
    Start-Sleep -Milliseconds 800
}
if(-not $ok){throw "NOX_WEB_BOOT_UNVERIFIED_HOLD: PID $($process.Id) / $url. Existing files and process untouched."}
Write-Host "NOX WEB VERIFIED: $url / PID $($process.Id)" -ForegroundColor Green
Show-NoxProvider
if(-not $NoBrowser){Start-Process $url}
