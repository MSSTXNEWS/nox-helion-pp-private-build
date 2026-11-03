# EXPRESS entry. Does not replace private_build.ps1.
# Fails closed until PATCH-A/B are sealed and I0 merges into PR162.
param([string]$SourceHead = "f41e2f5b1866542b50db011452d6d0af3feb26ca")
$ErrorActionPreference = "Stop"
Write-Output "EXPRESS_BUILD_HOLD"
Write-Output "reason=PATCH_A_B_NOT_SEALED"
Write-Output "source_head=$SourceHead"
Write-Output "pr162=OPEN integration/nox-v16-unified-candidate-20261028-r01"
Write-Output "release_accepted=false"
exit 2

# EXPRESS head is fix/b6-navidle-20261103. PRE-PRE private_build.ps1 is unchanged.
