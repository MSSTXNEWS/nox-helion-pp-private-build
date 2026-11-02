# Existing NOX EXPRESS Windows runner only; no second installer or release grant.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$ExpectedSha)
$ErrorActionPreference='Stop'
Set-StrictMode -Version Latest
if ($env:CI_SERVER_HOST -cne 'gitlab.com' -or
    $env:CI_PROJECT_PATH -cne 's-grouptwet/nox-helion-pp-private-build' -or
    $env:CI_PIPELINE_SOURCE -cnotin @('api','web') -or
    $env:CI_RUNNER_EXECUTABLE_ARCH -cne 'windows/amd64' -or
    ($env:NOX_T06_LOCAL_BRIDGE -cne 'YES' -and $env:NOX_APPROVE_T06_BRIDGE -cne 'YES') -or
    $ExpectedSha -cnotmatch '\A[0-9a-f]{40}\z' -or
    $env:CI_COMMIT_SHA -cnotmatch '\A[0-9a-f]{40}\z') {
  throw 'T06_GITHUB_CI_SCOPE_HOLD'
}
if ($env:GIT_CONFIG_COUNT -or [string]::IsNullOrWhiteSpace($env:NOX_T06_GITHUB_READ_TOKEN)) {
  throw 'T06_GITHUB_MASKED_READ_TOKEN_REQUIRED'
}
$checkout=(Resolve-Path -LiteralPath $env:CI_PROJECT_DIR).Path
if (-not [string]::Equals($checkout,(Get-Location).Path,
    [StringComparison]::OrdinalIgnoreCase)) { throw 'T06_GITHUB_CI_WORKDIR_HOLD' }
$git=(Get-Command git.exe -CommandType Application -ErrorAction Stop).Source
$gitlabCommit=$env:CI_COMMIT_SHA.ToLowerInvariant()
# Never include credential in URL, argv, git config files, or CI receipts.
$encoded=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(
    'x-access-token:'+$env:NOX_T06_GITHUB_READ_TOKEN))
$env:GIT_CONFIG_COUNT='1'
$env:GIT_CONFIG_KEY_0='http.https://github.com/.extraheader'
$env:GIT_CONFIG_VALUE_0='AUTHORIZATION: basic '+$encoded
$encoded=$null
$env:GIT_TERMINAL_PROMPT='0'
try {
  & $git -c credential.helper= fetch --no-tags --depth=1 'https://github.com/MSSTXNEWS/nox-helion-pp-private-build.git' 'refs/heads/integration/nox-v16-unified-candidate-20261028-r01'
  if ($LASTEXITCODE -ne 0) { throw 'T06_GITHUB_AUTH_FETCH_FAILED' }
} finally {
  foreach($key in @('GIT_CONFIG_COUNT','GIT_CONFIG_KEY_0',
                   'GIT_CONFIG_VALUE_0','GIT_TERMINAL_PROMPT')) {
    Remove-Item -LiteralPath ('Env:'+$key) -ErrorAction SilentlyContinue
  }
}
$remoteHead=(& $git rev-parse --verify FETCH_HEAD).Trim().ToLowerInvariant()
if ($LASTEXITCODE -ne 0 -or $remoteHead -cne $ExpectedSha) {
  throw 'T06_GITHUB_REF_MOVED_OR_FROZEN_SHA_HOLD'
}
& $git checkout --detach --force $remoteHead
if ($LASTEXITCODE -ne 0) { throw 'T06_GITHUB_WORKTREE_CHECKOUT_HOLD' }
$head=(& $git rev-parse --verify HEAD).Trim().ToLowerInvariant()
$tree=(& $git rev-parse 'HEAD^{tree}').Trim().ToLowerInvariant()
$dirty=@(& $git status --porcelain --untracked-files=all)
if ($LASTEXITCODE -ne 0 -or $head -cne $ExpectedSha -or
    $tree -cnotmatch '\A[0-9a-f]{40}\z' -or $dirty.Count -gt 0) {
  throw 'T06_GITHUB_EXACT_TREE_READBACK_HOLD'
}
$env:NOX_T06_GITLAB_ORIGIN_SHA=$gitlabCommit
$env:NOX_T06_GITHUB_FROZEN_SHA=$ExpectedSha
$env:NOX_T06_AUTHENTICATED_GITHUB_FETCH='PASS'
Write-Host ('T06_GITHUB_EXACT_SOURCE_PASS head='+$head+
            ' tree='+$tree+' gitlab_bootstrap='+$gitlabCommit+
            ' e07=NOT_RUN')
