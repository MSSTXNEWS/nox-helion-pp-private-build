# One existing T06 GitLab Windows job -> canonical GitHub PR162 source.
# Never a second installer, backend, fake approval or independent E07 PASS.
[CmdletBinding()]param()
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
$sha=[string]$env:NOX_PR162_EXACT_SHA
if ($env:CI_PROJECT_PATH -cne 's-grouptwet/nox-helion-pp-private-build' -or
    $env:CI_SERVER_HOST -cne 'gitlab.com' -or
    $env:CI_RUNNER_EXECUTABLE_ARCH -cne 'windows/amd64' -or
    $env:NOX_T06_LOCAL_BRIDGE -cne 'YES' -or
    $env:CI_PIPELINE_SOURCE -cnotin @('api','web')) {
  throw 'T06_GITHUB_EXACT_SOURCE_OWNER_APPROVAL_HOLD'
}
if ($sha -cnotmatch '\A[0-9a-f]{40}\z' -or
    [string]::IsNullOrWhiteSpace($env:NOX_GITHUB_READ_TOKEN) -or
    $env:CI_COMMIT_SHA -cnotmatch '\A[0-9a-f]{40}\z') {
  throw 'T06_GITHUB_EXACT_SOURCE_SHA_OR_MASKED_TOKEN_HOLD'
}
$origin=$env:CI_COMMIT_SHA
$priorAsk=$env:GIT_ASKPASS
$priorPrompt=$env:GIT_TERMINAL_PROMPT
$priorGcm=$env:GCM_INTERACTIVE
$priorLfs=$env:GIT_LFS_SKIP_SMUDGE
$root=(Resolve-Path -LiteralPath $env:CI_PROJECT_DIR).Path
$out=Join-Path $root 'work'
$clone=Join-Path $out ("pr162-"+$sha)
if (Test-Path -LiteralPath $clone) { throw 'T06_GITHUB_EXACT_SOURCE_WORK_COLLISION' }
New-Item -ItemType Directory -Path $clone -Force | Out-Null
$ask=Join-Path $env:TEMP ("nox-ask-"+[guid]::NewGuid().ToString('N')+".cmd")
# Token is inherited from the owner's masked CI variable only, not stored in
# this helper, remote URL, command-line arguments, git config or artifacts.
$cmd=@'
@echo off
setlocal DisableDelayedExpansion
echo %~1 | findstr /I /C:"Username" >NUL
if errorlevel 1 (
  powershell.exe -NoProfile -NonInteractive -Command "[Console]::Out.WriteLine($env:NOX_GITHUB_READ_TOKEN)"
) else (
  echo x-access-token
)
'@
[IO.File]::WriteAllText($ask,$cmd,(New-Object System.Text.ASCIIEncoding))
$head=$null
$tree=$null
$setupHash=$null
$done=$false
$entered=$false
try {
  $env:GIT_ASKPASS=$ask
  $env:GIT_TERMINAL_PROMPT='0'
  $env:GCM_INTERACTIVE='never'
  # Never auto-download model weights. Existing SourceLock fails if needed.
  $env:GIT_LFS_SKIP_SMUDGE='1'
  & git -C $clone init -q
  if ($LASTEXITCODE -ne 0) { throw 'T06_GITHUB_GIT_INIT_HOLD' }
  & git -C $clone config core.autocrlf false
  & git -C $clone -c 'credential.helper=' -c 'http.followRedirects=false' fetch --depth=1 --no-tags 'https://github.com/MSSTXNEWS/nox-helion-pp-private-build.git' 'refs/pull/162/head'
  if ($LASTEXITCODE -ne 0) { throw 'T06_GITHUB_PRIVATE_FETCH_AUTH_HOLD' }
  $fetched=((& git -C $clone rev-parse FETCH_HEAD)|Out-String).Trim().ToLowerInvariant()
  if ($LASTEXITCODE -ne 0 -or $fetched -cne $sha) { throw 'T06_GITHUB_PR162_HEAD_CHANGED_HOLD' }
  & git -C $clone checkout --detach FETCH_HEAD
  if ($LASTEXITCODE -ne 0) { throw 'T06_GITHUB_CHECKOUT_HOLD' }
  $head=((& git -C $clone rev-parse HEAD)|Out-String).Trim().ToLowerInvariant()
  $tree=((& git -C $clone rev-parse 'HEAD^{tree}')|Out-String).Trim().ToLowerInvariant()
  if ($LASTEXITCODE -ne 0 -or $head -cne $sha -or
      $tree -cnotmatch '\A[0-9a-f]{40}\z') { throw 'T06_GITHUB_EXACT_TREE_HOLD' }
  & git -C $clone diff --quiet HEAD --
  if ($LASTEXITCODE -ne 0) { throw 'T06_GITHUB_SOURCE_DIRTY_HOLD' }
  # The original producer requires CI_COMMIT_SHA == checkout HEAD. Preserve
  # the distinct GitLab source in an explicit extra audit field.
  $env:CI_COMMIT_SHA=$sha
  $env:NOX_GITLAB_RUNNER_SHA=$origin
  Push-Location -LiteralPath $clone
  $entered=$true
  $py=((& python -c 'import platform;print(platform.python_version())')|Out-String).Trim()
  if ($LASTEXITCODE -ne 0 -or $py -cne '3.12.10') { throw 'T06_PYTHON_31210_HOLD' }
  & python -m unittest discover -s tests/e06 -p 'test_t06_samevm_webview2_preflight_stage.py' -v
  if ($LASTEXITCODE -ne 0) { throw 'T06_SIGNED_WEBVIEW2_STAGE_TEST_HOLD' }
  & python -m unittest discover -s 'Packages/P02/worker-python' -p 'test_p02_native_ingress.py' -v
  if ($LASTEXITCODE -ne 0) { throw 'T06_P02_ORIGINAL_TEST_HOLD' }
  & python coordination/e06/t06_local_onehost_bridge.py
  if ($LASTEXITCODE -ne 0) { throw 'T06_ORIGINAL_NSIS_ONEHOST_HOLD' }
  $installer=Join-Path $clone 'work/t06-wpf-p02-compile/NOX-HELION-V16-ONEHOST-CANDIDATE-SETUP.exe'
  if (-not (Test-Path -LiteralPath $installer -PathType Leaf) -or
      (Get-Item -LiteralPath $installer).Length -le 1000000) {
    throw 'T06_ORIGINAL_NSIS_EXE_MISSING_OR_TRUNCATED'
  }
  $setupHash=(Get-FileHash -LiteralPath $installer -Algorithm SHA256).Hash.ToLowerInvariant()
  & git -C $clone diff --quiet HEAD --
  if ($LASTEXITCODE -ne 0) { throw 'T06_EXACT_SOURCE_CHANGED_DURING_BUILD' }
  $done=$true
}
finally {
  if ($entered) { Pop-Location }
  $env:CI_COMMIT_SHA=$origin
  $env:GIT_ASKPASS=$priorAsk
  $env:GIT_TERMINAL_PROMPT=$priorPrompt
  $env:GCM_INTERACTIVE=$priorGcm
  $env:GIT_LFS_SKIP_SMUDGE=$priorLfs
  if (Test-Path -LiteralPath $ask) { Remove-Item -LiteralPath $ask -Force -ErrorAction SilentlyContinue }
  foreach($name in @('t06-local-bridge','t06-wpf-p02-compile','t06-manual-source-inspect')) {
    $from=Join-Path (Join-Path $clone 'work') $name
    $to=Join-Path $out $name
    if (Test-Path -LiteralPath $from -PathType Container) {
      if (Test-Path -LiteralPath $to) { throw 'T06_EXACT_SOURCE_ARTIFACT_COLLISION' }
      Copy-Item -LiteralPath $from -Destination $to -Recurse -ErrorAction Stop
    }
  }
  $copy=Join-Path $out 't06-wpf-p02-compile/NOX-HELION-V16-ONEHOST-CANDIDATE-SETUP.exe'
  if ($done -and ((-not (Test-Path -LiteralPath $copy -PathType Leaf)) -or
      (Get-FileHash -LiteralPath $copy -Algorithm SHA256).Hash.ToLowerInvariant() -cne $setupHash)) {
    throw 'T06_EXACT_SOURCE_SETUP_COPY_SHA_HOLD'
  }
  $reportDir=Join-Path $out 't06-local-bridge'
  New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
  [ordered]@{schema='NOX-T06-GITHUB-PR162-SAMEVM-V1';github_head=$head;
    github_tree=$tree;gitlab_runner_head=$origin;exact_sha_match=$head -ceq $sha;
    setup_candidate_sha256=$setupHash;original_builder_completed=$done;
    installed_independent_e07='NOT_RUN';release_accepted=$false} |
    ConvertTo-Json -Depth 5 |
    Set-Content -LiteralPath (Join-Path $reportDir 'EXACT_PR162_SOURCE_RECEIPT.json') -Encoding UTF8
}
if (-not $done) { throw 'T06_EXACT_GITHUB_SOURCE_BUILD_HOLD' }
Write-Host "T06_EXACT_PR162_WINDOWS_CANDIDATE_NOT_E07 sha=$head setup_sha256=$setupHash"
