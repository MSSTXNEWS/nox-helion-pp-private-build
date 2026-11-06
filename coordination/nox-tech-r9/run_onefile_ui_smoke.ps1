param([Parameter(Mandatory=$true)][string]$Exe,
      [Parameter(Mandatory=$true)][string]$OutputRoot)
$ErrorActionPreference='Stop'
$exe=(Resolve-Path -LiteralPath $Exe).Path
$runid='NOX-ONEFILE-UI-'+$env:GITHUB_RUN_ID
$p=Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe) -ArgumentList @('--nox-ui-smoke',"--nox-runid=$runid") -PassThru
try{
 Wait-Process -Id $p.Id -Timeout 100 -ErrorAction Stop
 $p.Refresh()
 $path=Join-Path $env:LOCALAPPDATA "NOX_HELION/ui_selftest_$($p.Id).json"
 if(!(Test-Path -LiteralPath $path)){throw 'ONEFILE_UI_RECEIPT_MISSING'}
 $r=Get-Content $path -Raw|ConvertFrom-Json
 $sha=(Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
 if($p.ExitCode -ne 0 -or
    $r.schema -cne 'NOX_WPF_UI_SMOKE_R7_V1' -or
    $r.runId -cne $runid -or
    $r.pid -ne $p.Id -or
    $r.wpfWebView2Accepted -ne $true -or
    $r.qwenE2ETested -ne $false -or
    $r.checks.native_wpf_webview2_renderer -cne 'PASS' -or
    $r.checks.real_webview2_eight_routes -cne 'PASS' -or
    $r.checks.isolated_sqlite_path -cne 'PASS' -or
    ![string]::Equals([string]$r.exeSha256,$sha,[StringComparison]::OrdinalIgnoreCase)){
    throw ('ONEFILE_NATIVE_UI_HOLD '+($r|ConvertTo-Json -Depth 6 -Compress))
 }
 Copy-Item -LiteralPath $path -Destination (Join-Path $OutputRoot 'TECH_UI_RECEIPT.json') -Force
 $buildPath=Join-Path $OutputRoot 'TECH_BUILD_RECEIPT.json'
 $build=Get-Content $buildPath -Raw|ConvertFrom-Json
 $build.native_webview2='PASS'
 $build|ConvertTo-Json -Depth 6|Set-Content -LiteralPath $buildPath -Encoding UTF8
 Write-Host "NOX_ONEFILE_NATIVE_WEBVIEW2_EIGHT_ROUTES_PASS SHA=$sha"
} finally {
 $p.Refresh()
 if(!$p.HasExited){Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue}
}
