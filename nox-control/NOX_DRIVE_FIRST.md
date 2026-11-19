# NOX Drive-first · warm weights / direct downloads / automatic chunking

Source: nox-control/nox_drive_first.py. Reuses Google Drive API through the existing rclone binary and official chunker overlay. No second backend, model service, queue, or database.

## Owner-only server configuration (once)

The existing nox-drive-reconnect Supervisor monitor automatically refreshes a VALID Google OAuth token. It does not grant Google's initial consent. Configure noxdrive in /root/.config/rclone/rclone.conf through Google's real OAuth flow:
- type = drive
- root_folder_id = 1ewQ-R7z33fN0fKoMNNuFzv1_3rCEP96v
- private OAuth token only in the actual NOX server config (never in GitHub, chat or logs).

After authorization, create the official chunker overlay using the same private server config:

    rclone --config /root/.config/rclone/rclone.conf config create noxchunks chunker remote noxdrive:NOX_WEIGHT_CHUNKS chunk_size 1Gi hash_type md5

Expected overlay settings:

    [noxchunks]
    type = chunker
    remote = noxdrive:NOX_WEIGHT_CHUNKS
    chunk_size = 1Gi
    hash_type = md5

The chunker overlay transparently presents the original logical file. Never read raw physical part files directly through noxdrive:NOX_WEIGHT_CHUNKS for model restoration; use noxchunks: to reassemble them. Changing chunk size or transaction type on an occupied remote requires a real migration.

WARM = archived existing model weights. DOWNLOADS = new verified Internet downloads. STAGING = unpublished partial remote uploads. All reside below the approved NOX project root. Google per-user daily upload and storage limits still apply.

## Owner-pinned task manifest

Manifest is a PRIVATE regular file, owned by the service account, mode 0600, exact SHA-256 passed to NOX's existing owner/CAS dispatcher. Only one file per job, two actions:

Existing weight:
    {"schema":"nox.drive.first.v1","task_id":"nox-warm-001","action":"offload",
     "name":"model.gguf","size":1048576,"sha256":"<exact lowercase sha256>",
     "approved":true,"source_path":"/root/nox/models/model.gguf"}

New source downloaded directly to Drive (without persistent local model copy):
    {"schema":"nox.drive.first.v1","task_id":"nox-ingest-001","action":"ingest",
     "name":"model.gguf","size":1048576,"sha256":"<exact publisher sha256>",
     "approved":true,
     "source_url":"https://huggingface.co/approved/repo/resolve/main/model.gguf"}

Replace fake size and hash with independently verified source bytes. Use only owner-approved model providers. The trusted-host HTTPS redirect list is bounded to Hugging Face / GitHub / PyTorch and verified CDN hosts.

Run only with a fresh owner lease and resource admission:

    python3 -B /root/nox/ops/drive-auth/nox_drive_first.py \
      --manifest /root/nox/private/nox-ingest-001.json \
      --manifest-sha <verified exact manifest sha256> \
      --config /root/.config/rclone/rclone.conf \
      --state-dir /var/lib/nox-drive-first --execute

Without --execute there is no connection attempt, file download or upload. With --execute STOP and raw cgroup admission guard every transfer.

## End-to-end flow and receipts

1. Confirm noxdrive's Google auth, private 0600 config, exact root folder ID, chunker overlay and STOP/owner resource gates.
2. Offload: hash local model, use rclone copyto (known file size) to remote STAGING. Ingest: HTTPS stream directly into rclone rcat --size (known size) to STAGING; no whole-file local SSD spool.
3. Read logical STAGING file back through rclone cat, check full-file SHA-256 and byte count.
4. Immutable promotion to WARM or DOWNLOADS and independent second readback.
5. Save private receipt with verified hashes. NOX never deletes the local original.
6. To use a WARM model again: set existing nox_drive_prefetch.py manifest remote = noxchunks:WARM and exact asset size+SHA; stage to verified SSD; RAM/GPU only after model-specific admission. Engram partial model has its own pinned 4-part cold-holder and must follow its current separate memfd assembly policy.

If stream/network fails, STAGING can contain incomplete remote parts. Never promote it or count a transfer successful. Cleanup requires an owner-reviewed exact staging-file action; do not delete arbitrary remote files. The existing dispatcher owns retries with a fresh lease, not this transport.

Safety: no passwords or Google tokens in code, no S03, optimizer or checkpoint offload, no changes to live model, no new daemon, no public rclone RC. Reconnect service does not itself authorize Drive.

## Installation / truthful LIVE status

Existing owner-authenticated drive_reconnect_install operation also stages nox_drive_first.py. It does not create Google credentials or start transfers. Until a real on-host Google OAuth has been completed, the last verified server status remains CONFIG_MISSING/NOT_CONNECTED; no uploads or weight offloads can be called LIVE.

Official:
https://rclone.org/chunker/
https://rclone.org/commands/rclone_rcat/
https://rclone.org/drive/
https://developers.google.com/workspace/drive/api/guides/limits
