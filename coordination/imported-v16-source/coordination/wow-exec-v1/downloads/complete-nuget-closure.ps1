# NOX R11/MENU10 BLOCK 1 - missing NuGet dependency closure, evidence only.
param([string]$Output = (Join-Path $env:RUNNER_TEMP 'nox-r11-block1-closure'))
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
$version='1.8.260921001'
$source='https://api.nuget.org/v3/index.json'
$rootUrl="https://api.nuget.org/v3-flatcontainer/microsoft.windowsappsdk/$version/microsoft.windowsappsdk.$version.nupkg"
$expectedRoot='ee0c5218ded2dff2b5a40bd2fd15a5d91ae66fc612ab1ad0b9c66bf13fc6193a'
New-Item -ItemType Directory -Force -Path $Output | Out-Null
$Output=(Resolve-Path $Output).Path
$pkg=Join-Path $Output 'microsoft.windowsappsdk.1.8.260921001.nupkg'
$cache=Join-Path $Output 'nuget-packages'
$probe=Join-Path $Output '_restore_probe'
$log=Join-Path $Output 'nuget-command-evidence.txt'
New-Item -ItemType Directory -Force -Path $probe | Out-Null
$r=[ordered]@{schema='NOX-R11-BLOCK1-NUGET-CLOSURE-V2';scope='DOWNLOAD_ONLY';installed=$false;merged=$false;version=$version;source=$source;status='HOLD';root_sha256=$null;restore_exit=$null;packages=@();errors=@()}
function Run-Verify([string]$file){
  & dotnet nuget verify --all $file *>> $log
  if($LASTEXITCODE -ne 0){throw ('NUGET_SIGNATURE_HOLD:'+ [IO.Path]::GetFileName($file))}
}
try{
  if(-not (Get-Command dotnet -ErrorAction SilentlyContinue)){throw 'DOTNET_8_CI_SDK_MISSING'}
  if(-not (Test-Path -LiteralPath $pkg -PathType Leaf)){
     Invoke-WebRequest -Uri $rootUrl -OutFile $pkg -MaximumRedirection 4 -TimeoutSec 180 -UseBasicParsing
  }
  $h=(Get-FileHash -LiteralPath $pkg -Algorithm SHA256).Hash.ToLowerInvariant()
  $r.root_sha256=$h
  if($h -cne $expectedRoot){throw 'ROOT_SHA256_MISMATCH'}
  Run-Verify $pkg
  $xml=@'
<Project Sdk="Microsoft.NET.Sdk.WindowsDesktop">
<PropertyGroup>
<TargetFramework>net8.0-windows10.0.19041.0</TargetFramework>
<EnableWindowsTargeting>true</EnableWindowsTargeting>
<UseWPF>true</UseWPF>
<RestoreIgnoreFailedSources>false</RestoreIgnoreFailedSources>
</PropertyGroup>
<ItemGroup><PackageReference Include="Microsoft.WindowsAppSDK" Version="1.8.260921001"/></ItemGroup>
</Project>
'@
  $project=Join-Path $probe 'Block1Restore.csproj'
  [IO.File]::WriteAllText($project,$xml,([Text.UTF8Encoding]::new($false)))
  $cfg=Join-Path $probe 'NuGet.Config'
  [IO.File]::WriteAllText($cfg,'<?xml version="1.0" encoding="utf-8"?><configuration><packageSources><clear/><add key="nuget.org" value="https://api.nuget.org/v3/index.json"/></packageSources></configuration>',([Text.UTF8Encoding]::new($false)))
  & dotnet restore $project --packages $cache --configfile $cfg --disable-parallel --force --verbosity minimal *>> $log
  $r.restore_exit=$LASTEXITCODE
  if($LASTEXITCODE -ne 0){throw 'NUGET_RESTORE_FAILED'}
  $all=@(Get-ChildItem -LiteralPath $cache -Recurse -File -Filter '*.nupkg')
  if($all.Count -lt 10){throw ('NUGET_CLOSURE_TOO_SMALL:'+ $all.Count)}
  foreach($item in $all){
    Run-Verify $item.FullName
    $r.packages += [ordered]@{relative_path=$item.FullName.Substring($Output.Length+1).Replace('\','/');bytes=$item.Length;sha256=(Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash.ToLowerInvariant();verification='SIGNED_NUGET_PASS'}
  }
  $r.status='PASS';$r.package_count=$all.Count
} catch {
  $r.status='HOLD';$r.errors+=([string]$_.Exception.Message)
} finally {
  $receipt=Join-Path $Output 'BLOCK1_NUGET_CLOSURE_RECEIPT.json'
  [IO.File]::WriteAllText($receipt,($r|ConvertTo-Json -Depth 12),([Text.UTF8Encoding]::new($false)))
  Write-Host ('NOX_NUGET_CLOSURE status='+$r.status+' packages='+$r.packages.Count+' errors='+($r.errors -join ';'))
}
if($r.status -ne 'PASS'){exit 2}
