# NOX SOUL MODEL CONSOLIDATOR V2 — PowerShell 7/5.1; dry-run by default.
# Run: powershell -ExecutionPolicy Bypass -File .\CONSOLIDATE_NOX_WEIGHTS.ps1 -Apply -CleanDownloads
[CmdletBinding()]
param([switch]$Apply,[switch]$CleanDownloads,[string]$NoxRoot='C:\NOX_HELION\NOX_NEW',[int]$ReserveGB=60)
$ErrorActionPreference='Stop'
$homeDownloads=Join-Path $env:USERPROFILE 'Downloads'
$store=Join-Path $NoxRoot 'models\imported'
$logs=Join-Path $NoxRoot 'logs'
$extensions=@('.gguf','.safetensors','.onnx','.pt','.pth','.ckpt','.bin')
$maxItems=5000
if ($Apply) { New-Item -ItemType Directory -Force $store,$logs | Out-Null }
$actions=New-Object System.Collections.Generic.List[object]
function IsChild([string]$file,[string]$root) {
  $r=[IO.Path]::GetFullPath($root).TrimEnd('\')+'\'
  return [IO.Path]::GetFullPath($file).StartsWith($r,[StringComparison]::OrdinalIgnoreCase)
}
function HashFile([string]$p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() }
function Record([string]$status,[string]$source,[string]$destination,[string]$reason) {
  $actions.Add([pscustomobject]@{status=$status;source=$source;destination=$destination;reason=$reason})
}
if (!(Test-Path -LiteralPath $NoxRoot)) { throw "NOX_NEW not found: $NoxRoot" }
if (IsChild $store $homeDownloads) { throw 'Destination must not be inside Downloads' }
# Ollama's content-addressed blob store is NOT a collection of independent weights.
# Never move blobs/manifests; reconfigure OLLAMA_MODELS and restart daemon separately.
$existing=@{}
if (Test-Path -LiteralPath $store) {
  Get-ChildItem -LiteralPath $store -Recurse -File -ErrorAction Stop | Where-Object {
    $extensions -contains $_.Extension.ToLowerInvariant()
  } | ForEach-Object { $existing[(HashFile $_.FullName)]=$_.FullName }
}
$inputs=@()
if (Test-Path -LiteralPath $homeDownloads) {
 $inputs=@(Get-ChildItem -LiteralPath $homeDownloads -Recurse -File -ErrorAction SilentlyContinue |
 Where-Object {
   ($extensions -contains $_.Extension.ToLowerInvariant()) -and
   $_.FullName -notmatch '[\\/](ollama[\\/]models|blobs|manifests)[\\/]'
 } | Select-Object -First $maxItems)
}
foreach ($f in $inputs) {
 try {
  $digest=HashFile $f.FullName
  if ($existing.ContainsKey($digest)) {
    $target=$existing[$digest]
    if ($Apply -and $CleanDownloads -and (IsChild $f.FullName $homeDownloads)) {
      Remove-Item -LiteralPath $f.FullName -Force
      Record 'duplicate-removed' $f.FullName $target 'SHA256 identical to canonical copy'
    } else { Record 'duplicate-found' $f.FullName $target 'Source retained (preview or cleanup disabled)' }
    continue
  }
  $dest=Join-Path $store ($digest.Substring(0,16)+'_'+$f.Name)
  if (!$Apply) { Record 'would-import' $f.FullName $dest 'Preview only';continue }
  $drive=[IO.Path]::GetPathRoot($dest)
  $free=(Get-PSDrive -Name $drive.Substring(0,1)).Free
  if ($free -lt ($f.Length + $ReserveGB * 1GB)) {
    Record 'skipped' $f.FullName $dest 'Insufficient free space / reserved 60GB';continue
  }
  $temporary=$dest+'.partial'
  if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary -Force }
  Copy-Item -LiteralPath $f.FullName -Destination $temporary -ErrorAction Stop
  if ((HashFile $temporary) -ne $digest) { Remove-Item -LiteralPath $temporary -Force;throw 'Post-copy SHA256 mismatch' }
  Move-Item -LiteralPath $temporary -Destination $dest -ErrorAction Stop
  $existing[$digest]=$dest
  if ($CleanDownloads -and (IsChild $f.FullName $homeDownloads)) {
    Remove-Item -LiteralPath $f.FullName -Force
    Record 'imported-and-source-removed' $f.FullName $dest 'SHA256 verified'
  } else { Record 'imported-source-kept' $f.FullName $dest 'SHA256 verified' }
 } catch {
   Record 'error' $f.FullName '' $_.Exception.Message
 }
}
$summary=$actions | Group-Object status | ForEach-Object { [pscustomobject]@{status=$_.Name;count=$_.Count} }
$report=[pscustomobject]@{version='2.0';timestamp=(Get-Date).ToString('o');nox_root=$NoxRoot;apply=[bool]$Apply;clean_downloads=[bool]$CleanDownloads;ollama_note='Do not relocate Ollama blobs directly; configure OLLAMA_MODELS for the running Ollama server';summary=$summary;actions=$actions}
if ($Apply) {
 $path=Join-Path $logs ('weights-consolidation-'+(Get-Date -Format 'yyyyMMdd-HHmmss')+'.json')
 $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $path -Encoding UTF8
 Write-Host "Audit: $path"
}
$report | ConvertTo-Json -Depth 8
