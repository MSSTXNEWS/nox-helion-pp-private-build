& {
  $ErrorActionPreference='Stop'
  [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
  $dest='C:\NOX_HELION\APP\NOX_WEB\BLACKHOLE_STAGE1'
  $src=Join-Path $dest 'SOURCE'
  $vendor=Join-Path $dest 'vendor'
  New-Item -ItemType Directory -Force -Path $src,$vendor | Out-Null
  $repo='https://raw.githubusercontent.com/sysscan/3d-blackhole-simulation/9cd793f34b972f6c8928b0d3127d94eff7613a61'
  function Download-Safe([string]$url,[string]$path,[int]$min) {
    if((Test-Path -LiteralPath $path) -and (Get-Item -LiteralPath $path).Length -ge $min){return}
    $partial="$path.partial"
    if(Test-Path -LiteralPath $partial){Remove-Item -LiteralPath $partial -Force}
    try {
      Invoke-WebRequest -Uri $url -OutFile $partial -UseBasicParsing -ErrorAction Stop
      if((Get-Item -LiteralPath $partial).Length -lt $min){throw "Truncated download: $url"}
      Move-Item -LiteralPath $partial -Destination $path -Force
    } finally {if(Test-Path -LiteralPath $partial){Remove-Item -LiteralPath $partial -Force}}
  }
  $html=Join-Path $src 'index.html'
  $license=Join-Path $src 'LICENSE'
  $readme=Join-Path $src 'README.md'
  $three=Join-Path $vendor 'three.min.js'
  Download-Safe "$repo/index.html" $html 20000
  Download-Safe "$repo/LICENSE" $license 900
  Download-Safe "$repo/README.md" $readme 2000
  Download-Safe 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js' $three 400000
  function Assert-GitBlob([string]$path,[string]$expected){
    [byte[]]$data=[IO.File]::ReadAllBytes($path)
    [byte[]]$prefix=[Text.Encoding]::ASCII.GetBytes("blob $($data.Length)")
    [byte[]]$prefix=@($prefix)+@(0)
    [byte[]]$joined=New-Object byte[] ($prefix.Length+$data.Length)
    [Array]::Copy($prefix,0,$joined,0,$prefix.Length)
    [Array]::Copy($data,0,$joined,$prefix.Length,$data.Length)
    $sha=[Security.Cryptography.SHA1]::Create()
    try{$got=([BitConverter]::ToString($sha.ComputeHash($joined))).Replace('-','').ToLowerInvariant()}finally{$sha.Dispose()}
    if($got -ne $expected){throw "Pinned Git source SHA mismatch: $path"}
  }
  Assert-GitBlob $html 'baae2a37c851c73c6cf41039d000363d18e47643'
  Assert-GitBlob $license 'd59de81c4eb387bba2a515b76a25944c59e5f83e'
  Assert-GitBlob $readme '0e0a0727013e2e453db57ef65ae2b281473ebe0c'
  if(!([IO.File]::ReadAllText($license).StartsWith('MIT License'))){throw 'License not verified'}
  $original=[IO.File]::ReadAllText($html)
  $cdn='https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js'
  if(!$original.Contains($cdn)){throw 'Unexpected source, stopping'}
  $offline=$original.Replace($cdn,'./vendor/three.min.js')
  $index=Join-Path $dest 'index.html'
  if(Test-Path -LiteralPath $index){
    if([IO.File]::ReadAllText($index) -ne $offline){throw 'Existing modified file preserved; no overwrite'}
  }else{[IO.File]::WriteAllText($index,$offline,[Text.UTF8Encoding]::new($false))}
  [ordered]@{
    source='https://github.com/sysscan/3d-blackhole-simulation'
    commit='9cd793f34b972f6c8928b0d3127d94eff7613a61'
    license='MIT'
    original_sha256=(Get-FileHash $html -Algorithm SHA256).Hash
    offline_sha256=(Get-FileHash $index -Algorithm SHA256).Hash
    three_sha256=(Get-FileHash $three -Algorithm SHA256).Hash
    integrated_into_nox=$false
  } | ConvertTo-Json | Set-Content (Join-Path $dest 'STAGE1_MANIFEST.json') -Encoding UTF8
  Write-Host "BLACK HOLE REAL WEBGL DEMO READY: $index" -ForegroundColor Green
  Write-Host 'Current NOX HOME, chat, models and SQLite were not modified.'
  Start-Process -FilePath $index
}