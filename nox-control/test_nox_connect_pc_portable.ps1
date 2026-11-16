#requires -Version 5.1
# Syntax and platform-neutral functions only. Does not install anything or touch
# Windows services, credentials, Task Scheduler, the network or the NOX server.
$ErrorActionPreference = 'Stop'
$source = Join-Path $PSScriptRoot 'NOX_CONNECT_PC.ps1'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($source,[ref]$tokens,[ref]$parseErrors)
if ($parseErrors.Count) { throw ('PowerShell parse errors: ' + $parseErrors.Count) }
$names = @('Get-Field','Set-Field','Public-Identity','Public-Fingerprint','Quote-Native','Text-Sha256','Write-PlainFile','Write-AtomicJson','Existing-KeyArguments','Windows-PathAncestors','Local-PathAttributes','Assert-NoReparse')
foreach ($function in $ast.FindAll({param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst]},$false)) {
    if ($names -contains $function.Name) { . ([scriptblock]::Create($function.Extent.Text)) }
}
$Utf8 = New-Object System.Text.UTF8Encoding -ArgumentList $false
$public = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4f test-only'
if ((Public-Identity $public) -cne ($public -replace ' test-only$','')) { throw 'Public key normalization failed' }
$fingerprint = Public-Fingerprint $public
if ($fingerprint -notmatch '^SHA256:[A-Za-z0-9+/]{43}$') { throw 'Public fingerprint format failed' }
if ((Quote-Native '') -cne '""') { throw 'Empty native argument was lost' }
if ((Quote-Native 'C:\folder\') -cne '"C:\folder\\"') { throw 'Trailing native slash was not quoted' }
if ((Existing-KeyArguments '.ssh/authorized_keys .ssh/authorized_keys2' 'C:\ProgramData') -cne '".ssh/authorized_keys" ".ssh/authorized_keys2"') { throw 'Standard authorized key files changed' }
if ((Existing-KeyArguments 'C:/keys/owner.pub' 'C:\ProgramData') -cne '"C:/keys/owner.pub"') { throw 'Single custom key filename changed' }
$ambiguousRejected = $false
try { $null = Existing-KeyArguments 'C:/keys/team one.pub' 'C:\ProgramData' }
catch { if ($_.Exception.Message -ceq 'HOLD_AMBIGUOUS_AUTHORIZED_KEYS_FILES') { $ambiguousRejected=$true } else { throw } }
if (-not $ambiguousRejected) { throw 'Ambiguous existing authorized key policy was guessed' }
$chain = @(Windows-PathAncestors 'C:\NOX_HELION\ACCESS\pc-link')
if (($chain -join '|') -cne 'C:\NOX_HELION\ACCESS\pc-link|C:\NOX_HELION\ACCESS|C:\NOX_HELION|C:\') { throw 'Absolute drive ancestor walk failed' }
if ((@(Windows-PathAncestors 'C:\') -join '|') -cne 'C:\') { throw 'Drive root was interpreted as a current directory' }
if ((@(Windows-PathAncestors 'C:/NOX_HELION/') -join '|') -cne 'C:\NOX_HELION|C:\') { throw 'Forward slash normalization failed' }
$invalidRejected = $false
try { $null = Windows-PathAncestors 'C:relative' } catch { if ($_.Exception.Message -ceq 'HOLD_NONLOCAL_CHECKED_PATH') { $invalidRejected=$true } else { throw } }
if (-not $invalidRejected) { throw 'Drive-relative check was permitted' }
if ($null -ne (Local-PathAttributes (Join-Path ([IO.Path]::GetTempPath()) ('nox-absent-' + [Guid]::NewGuid().ToString('N'))))) { throw 'Missing filesystem node was not handled' }
# Mock only OS attributes: the actual traversal and rejecting guard still run.
$script:MockReparseAt = ''
$script:MockVisited = @()
function Local-PathAttributes([string]$Path) {
    $script:MockVisited += $Path
    if ($Path -ceq $script:MockReparseAt) { return [IO.FileAttributes]([long][IO.FileAttributes]::Directory -bor [long][IO.FileAttributes]::ReparsePoint) }
    if ($Path -eq 'C:\NOX_HELION\missing') { return $null }
    return [IO.FileAttributes]::Directory
}
Assert-NoReparse 'C:\NOX_HELION\missing' 'DESTINATION_ROOT'
if (($script:MockVisited -join '|') -cne 'C:\NOX_HELION\missing|C:\NOX_HELION|C:\') { throw 'Missing target bypassed ancestor validation' }
foreach ($fixture in @(@('C:\NOX_HELION',0),@('C:\',1))) {
    $script:MockReparseAt = $fixture[0]
    $rejected = $false
    try { Assert-NoReparse 'C:\NOX_HELION' 'DESTINATION_ROOT' 3>$null }
    catch { if ($_.Exception.Message -ceq ('HOLD_REPARSE_PATH_DESTINATION_ROOT_D' + $fixture[1])) { $rejected=$true } else { throw } }
    if (-not $rejected) { throw 'Reparse point bypassed the guard' }
}
$value = [pscustomobject]@{a=1}
Set-Field $value 'b' 2
if ((Get-Field $value b 0) -ne 2 -or (Get-Field $value missing 3) -ne 3) { throw 'Manifest field access failed' }
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('nox-pc-test-' + [Guid]::NewGuid().ToString('N') + '.json')
try {
    Write-AtomicJson $temporary $value
    Write-AtomicJson $temporary ([pscustomobject]@{a=3})
    if (([IO.File]::ReadAllText($temporary) | ConvertFrom-Json).a -ne 3) { throw 'Atomic replacement failed' }
} finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary } }
Write-Output 'POWERSHELL_PARSE_ERRORS=0'
Write-Output 'POWERSHELL_PORTABLE_CHECKS=PASSED'
