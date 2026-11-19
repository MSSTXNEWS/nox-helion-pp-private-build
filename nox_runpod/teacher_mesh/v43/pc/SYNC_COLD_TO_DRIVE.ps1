# Optional rclone backup after the user has configured their own private Google Drive remote.
# No deletion of local files and no auto-exposure of Drive tokens.
param([string]$Vault='C:\NOX_HELION\MODEL_VAULT',[string]$Remote='')
if (-not $Remote) { throw 'Specify an existing authenticated rclone remote path, e.g. "mydrive:NOX_HELION/MODEL_VAULT".' }
if (-not (Get-Command rclone -ErrorAction SilentlyContinue)){throw 'rclone not available; install and configure privately first.'}
& rclone copy $Vault $Remote --checksum --progress --transfers 1 --checkers 2
if ($LASTEXITCODE -ne 0){throw 'Google Drive sync failed, original local files unchanged.'}
& rclone check $Vault $Remote --one-way --size-only
if ($LASTEXITCODE -ne 0){throw 'Verification failed; do not delete local files.'}
Write-Host 'Drive copies checked; the PC originals remain intact.'
