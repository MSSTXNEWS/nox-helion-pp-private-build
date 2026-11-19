# NOX Google Drive — noninteractive refresh & reconnect

`nox_drive_reconnect.py` provides a bounded connection check every 10 minutes, with persistent exponential backoff (15 seconds–30 minutes), a single instance lock, current STOP and cgroup memory admission, and no remote writes, syncs, deletes or log disclosure of private file names/tokens.

**Status before installation:** the latest authenticated Vast.ai #60509551 `drive_probe` (`GitHub Actions #44606174658`) returns `CONFIG_MISSING`, `NOT_CONNECTED`, read false, write untested. ChatGPT's connected Drive account is NOT a token for NOX, and this source does not make it one.

## One-time authorization on the actual host

Use **your own Google OAuth client ID** (rclone's shared client is being retired in 2026). From a trusted shell with the same OS identity that will run reconnect, use `rclone config` to create remote `noxdrive`, type `drive`, a scope that covers required NOX files, and **root_folder_id** `1ewQ-R7z33fN0fKoMNNuFzv1_3rCEP96v`. Follow the official [headless OAuth](https://rclone.org/remote_setup/) setup with the trusted desktop/browser; never paste tokens/authorization codes in chat, a GitHub issue, CI logs or Notion. Store config only in `/root/.config/rclone/rclone.conf`, `chmod 600`, parent directory private to owner. Use a dedicated account shared to the NOX folder when practical: `root_folder_id` restricts rclone operations but does not by itself restrict the OAuth token's full Google Drive scope.

**No manual OAuth refresh should normally be necessary:** when `rclone lsf` or a data transfer uses the configured remote, rclone automatically refreshes valid OAuth access tokens and updates its private writable config. If Google revokes the refresh token, returns `invalid_grant`, or owner removes access, status becomes `OWNER_REAUTH_REQUIRED`; a legitimate interactive `rclone config reconnect noxdrive:` is necessary. Script will *not* attempt login automation, forge credentials or bypass Google's security prompts. [Rclone docs](https://rclone.org/docs/), [Drive config](https://rclone.org/drive/), [reconnect command](https://rclone.org/commands/rclone_config_reconnect/).

## Deployment on Vast.ai

Use the existing **owner-authenticated, exact-SHA-pinned** route to install the reviewed script at `/root/nox/ops/drive-auth/nox_drive_reconnect.py` and private state directory `/var/lib/nox-drive-reconnect` (mode `0700`, root-owned). Never download and execute arbitrary code from a model response. The source repository file alone is not a running service.

Choose **one** existing supervisor environment:
- Vast container with `supervisord`: install `nox-control/supervisor/nox-drive-reconnect.conf` into the reviewed Supervisor include directory, then `supervisorctl reread && supervisorctl update`. This process is a *connection check*, not another NOX task dispatcher; it sleeps between read-only probes.
- A host using systemd: install `nox-control/systemd/nox-drive-reconnect.{service,timer}`, `systemctl daemon-reload && systemctl enable --now nox-drive-reconnect.timer`. Do not start both monitoring methods.

Do not enable the new monitor while raw cgroup headroom is dangerously low without reviewing the current process budget. The reconnect script itself defers launching rclone if raw cgroup headroom is below 128 MiB and never evicts model weights.

Expected local private receipt: `/var/lib/nox-drive-reconnect/status.json` with `state: CONNECTED`, `project_root_pinned: true`, `verified_live_this_cycle: true`, and NO credentials or filenames. `WAIT_BACKOFF`/`RETRYABLE_*` is recoverable. `HOLD_CONFIG_MISSING` and `OWNER_REAUTH_REQUIRED` are **not** connected.

## Upload/readback and warm weights are separate

This script **does not** verify write access, backup or warm weights. After `CONNECTED`, run one approved small file write → independent readback/SHA-256 → safe deletion of the self-owned test object. Then use the existing NOX SHA-bound Drive→SSD→RAM cache with STOP, owner/CAS, S03, and cgroup admission. Never remove local originals without a verified remote copy and restoration proof.
