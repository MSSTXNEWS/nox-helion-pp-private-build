# NOX LOCAL LIVE INTEGRATION - safe one-command installer for Windows PowerShell 5.1.
# Pinned source. Never changes the original Ollama, models, SQLite/S03 or trainer.
& {
  $ErrorActionPreference = 'Stop'
  [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
  $root = 'C:\NOX_HELION\APP\NOX_WEB'
  $dest = Join-Path $root 'NOX_INTEGRATED'
  $stage = Join-Path $root '_NOX_INTEGRATION_STAGING'
  $sourceRef = '46a4799bf4faa795cf63d3e20c7059a3878911f5'
  $base = 'https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/'+$sourceRef+'/nox-local/live-integration'
  New-Item -ItemType Directory -Force -Path $root | Out-Null
  $launchName = 'START_NOX_INTEGRATED.ps1'
  if(Test-Path (Join-Path $dest 'NOX_INTEGRATED_MANIFEST.json')) {
    $current = Get-Content -Raw -LiteralPath (Join-Path $dest 'NOX_INTEGRATED_MANIFEST.json') | ConvertFrom-Json
    if($current.source_ref -ne $sourceRef){ throw 'Another NOX integrated version exists; preserved. Do not overwrite a running app.' }
    Write-Host 'NOX candidate already installed. Checking launcher...' -ForegroundColor Cyan
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $dest $launchName)
    return
  }
  if(Test-Path $dest){throw 'Existing unverified NOX_INTEGRATED found. Source preserved; no overwrite.'}
  if(!(Test-Path $stage)) {
    $src = $null
    foreach($name in @('NOX_READY_01','WOW_MEGA_01','WOW_V7_FIXED')) {
      $p = Join-Path $root $name
      if((Test-Path (Join-Path $p 'server_mega.py')) -and (Test-Path (Join-Path $p 'chat.html')) -and (Test-Path (Join-Path $p 'vendor\tabler\tabler.min.css'))) { $src=$p; break }
    }
    if(!$src) {throw 'Compatible existing NOX_READY_01 not found. Nothing modified. Install approved READY package first.'}
    Write-Host ('Copying existing NOX source: '+$src) -ForegroundColor Cyan
    Copy-Item -LiteralPath $src -Destination $stage -Recurse -ErrorAction Stop
  }
  if(!(Test-Path (Join-Path $stage 'server_mega.py'))){throw 'Incomplete original source in candidate; preserved.'}
  $files = @'
nox_probe.py|0394605205CA7BC8E6CC146F6D30B4AAE11664096A6A6688FA8661D0FC7EC939
server_integrated.py|0684CFAF877D98B52B757792BAAAD7FD745F2500BB0838C08D30E954707B95FC
nox-pages.js|6F6E8F937C55B7C42091CB2EB0B806974CF477459EAC118D984F865DF5C5EB9F
nox-pages.css|F5455A040CDE4C3C055F8EF8FA8E29C598990588236F01301A4547495D884E24
nox-notices.js|CD8A854B46399F9FE7950E571C16E2BF3216AE260FEE749ED1FCE0845A000B88
nox-home-nav.js|8B0CFD6B650DC2BEB36F3BAAAA499B0634204972CD1D8D45A9927BA6B18D1D54
nox-nav-ext.js|169F2A815935CD29ED68F36F4C86D20429D730A2CB47EC854811940549C3DBFE
nox-route-menu.css|F1F253E879031ED3B1032AB558D5E79DD55327786B1CCA13BA587370BADBA6CE
chat.js|E545F8BEB4C8F1118402467E149E00DBFF5192F0701B3AD80115207D847E4F49
index.html|CB4E3389DDA7231CF86E41C7DF7BB6DD7B7F5FA81D7F88FF0DE680769FDCD97E
chat.html|6EF2DDCC5C00507EC0DE9163066CDBAD4A00629A42443E34D65EC9DCDF145906
training.html|29BD5777A6BD12AE4931A87CB1415A417B8CC07E596F0203A32397B62DFFDDC5
models.html|DD5BAF8771A9A99595AF26E3BDC975AF63153715F742021C4C15FABF241AE77D
memory.html|73ACB5AB38E56D942311E7E9ACA07FDC9DFDF7D6A8E86102A61F4036FBA38B03
system.html|7C9FAC9100FC3D1D841301EFC9C4ED022152603365340C38D6C7C40A6830656C
install.html|D3099027BE3665882CD685B02075A0E2E8D8A7CD6170E513D4E3528E621188FA
projects.html|879E96EBE8D239CF70860BC3ABE53C2BF9D8CDE68E1E14B4D8A8D2A20233FCC0
settings.html|868A9D5CA86C5D83EDCDFCD5259BAB17B123744DD2186DF126669A938CDE438B
test_integrated.py|D92F90C8AB01D0A57C24F2F3DBDB4D5C09E430D5453B97C6AA7C12CA6CD18BD2
START_NOX_INTEGRATED.ps1|16D57232D1F5C2BD3602CEBA3F673D6B7E2A2941F4DDA947DB5D04C2FFDEA1C2
tests/test_browser.py|51AA93685A823375CE2AC9918044BCF143D3C7A4537D33B86503E552DF119783
'@ -split '[\r\n]+' | Where-Object {$_ -match '\|'}
  $written = New-Object System.Collections.ArrayList
  foreach($line in $files) {
    $parts=$line.Split('|')
    $name=$parts[0];$sha=$parts[1].ToUpperInvariant();$target=Join-Path $stage $name
    $parent=Split-Path -Parent $target
    New-Item -ItemType Directory -Force -Path $parent | Out-Null
    if((Test-Path $target) -and (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -eq $sha) {continue}
    $tmp="$target.partial"
    if(Test-Path $tmp){Remove-Item -LiteralPath $tmp -Force}
    try {
      Invoke-WebRequest -UseBasicParsing -Uri ($base+'/'+$name) -OutFile $tmp -TimeoutSec 90 -ErrorAction Stop
      if((Get-FileHash -LiteralPath $tmp -Algorithm SHA256).Hash -ne $sha){throw ('Downloaded SHA256 mismatch: '+$name)}
      Move-Item -LiteralPath $tmp -Destination $target -Force
      [void]$written.Add($name)
    } finally {if(Test-Path $tmp){Remove-Item -LiteralPath $tmp -Force}}
  }
  if(!(Test-Path (Join-Path $stage 'vendor\fx\echarts.min.js'))){throw 'Original ECharts not found; no unverified library substituted.'}
  if(!(Test-Path (Join-Path $stage 'server.py'))){throw 'Original NOX server missing; preserved.'}
  $python = Get-Command python.exe -ErrorAction SilentlyContinue
  if(!$python){throw 'Python 3 not available; no existing server modified.'}
  Push-Location $stage
  try {
    & $python.Source -m py_compile server_integrated.py nox_probe.py nox_services.py server_mega.py
    if($LASTEXITCODE -ne 0){throw 'Python source compile failed'}
    & $python.Source -m unittest -q test_integrated
    if($LASTEXITCODE -ne 0){throw 'HTTP contract tests failed'}
  } finally { Pop-Location }
  $manifest=[ordered]@{
    source_ref=$sourceRef
    installed_at=(Get-Date).ToString('o')
    reused_source=$true
    edited_only_candidate=$true
    source_files=@($files.Count)
    last_downloaded=@($written)
    ollama_models_changed=$false
    original_s03_changed=$false
    original_trainer_changed=$false
    physical_visual_qa='NOT_VERIFIED'
    trainer_control='HOLD_PENDING_ORIGINAL_CONTRACT'
    s03_write='HOLD_PENDING_SCHEMA'
    push_closed_tab='HOLD_PENDING_VAPID_AND_DELIVERY_TEST'
  }
  $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $stage 'NOX_INTEGRATED_MANIFEST.json') -Encoding UTF8
  Move-Item -LiteralPath $stage -Destination $dest -ErrorAction Stop
  Write-Host ('NOX integrated local candidate READY: '+$dest) -ForegroundColor Green
  Write-Host 'Existing running NOX, weights, memory and trainer were not replaced.'
  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $dest $launchName)
}