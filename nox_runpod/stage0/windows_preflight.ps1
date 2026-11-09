# NOX HELION / RunPod Windows preflight. READ-ONLY inventory; no secrets, uploads, deletions or GPU rental.
$ErrorActionPreference = 'Stop'
$roots = @('C:\NOX_HELION', (Join-Path $env:USERPROFILE '.ollama\models'), (Join-Path $env:USERPROFILE '.cache\huggingface\hub')) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -Unique
$reportFolder = Join-Path $env:LOCALAPPDATA 'NOX_HELION\RunPod'
New-Item -ItemType Directory -Path $reportFolder -Force | Out-Null
$reportFile = Join-Path $reportFolder 'windows_model_preflight.json'
$items = New-Object System.Collections.Generic.List[object]
$names = @('config.json','adapter_config.json','*.safetensors','*.gguf','*.ggml','*.bin','*.pt','*.pth','*.ckpt')
foreach ($root in $roots) {
    Write-Host ("Inspecting " + $root + " (read-only) ...")
    foreach ($pattern in $names) {
        # Avoid running tools, uploading data, or reading model file bytes.
        Get-ChildItem -LiteralPath $root -Recurse -File -Filter $pattern -ErrorAction SilentlyContinue |
            Where-Object { $_.FullName -notmatch '(?i)[\\/](node_modules|\.git|\.venv|venv|site-packages|tmp|temp)[\\/]' } |
            ForEach-Object {
                $items.Add([pscustomobject]@{ Path=$_.FullName; File=$_.Name; Bytes=$_.Length; ModifiedUtc=$_.LastWriteTimeUtc.ToString('o') })
            }
    }
}
$groups = @($items | Group-Object { Split-Path -Path $_.Path -Parent } | ForEach-Object {
    $files = @($_.Group)
    $config = @($files | Where-Object { $_.File -eq 'config.json' -or $_.File -eq 'adapter_config.json' })
    $weights = @($files | Where-Object { $_.File -match '(?i)\.(safetensors|gguf|ggml|bin|pt|pth|ckpt)$' })
    if ($weights.Count -gt 0 -or $config.Count -gt 0) {
        [pscustomobject]@{ Directory=$_.Name; WeightFiles=$weights.Count; WeightBytes=[long](($weights | Measure-Object -Property Bytes -Sum).Sum); ConfigFiles=@($config | ForEach-Object { $_.File }); LatestUtc=($files | Sort-Object ModifiedUtc -Descending | Select-Object -First 1).ModifiedUtc }
    }
} | Sort-Object WeightBytes -Descending)
$report = [ordered]@{ Task='NOX-RUNPOD-WINDOWS-PREFLIGHT'; Status='INVENTORY_ONLY_NOT_TRAINED'; Utc=(Get-Date).ToUniversalTime().ToString('o'); Roots=$roots; CandidateCount=$groups.Count; Candidates=$groups }
$report | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $reportFile -Encoding UTF8
Write-Host ''
Write-Host 'NOX RUNPOD PREFLIGHT COMPLETE - no files modified, uploaded or deleted.'
Write-Host ('Report: ' + $reportFile)
$groups | Select-Object -First 15 Directory, WeightFiles, @{N='GB';E={[math]::Round($_.WeightBytes / 1GB,2)}}, ConfigFiles | Format-Table -AutoSize
if ($groups.Count -eq 0) { Write-Warning 'No weights found at checked locations. Other drives or model folders may require explicit inspection.' }
Write-Host 'Share only the top candidate folder and model architecture (not private files or credentials).'
