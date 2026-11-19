# NOX Drive-first skill (v1)
Use for owner-approved Google Drive weight uploads, internet model ingest and warm model restoration. No separate dispatcher.

1. Before a transfer verify the owner's exact private manifest task_id, size, SHA256, action and source URL or local model path.
2. Google OAuth in the running Vast instance must be valid and the folder root pinned to NOX. If CONFIG_MISSING, report HOLD_GOOGLE_AUTH; a running monitor does not count as connected.
3. Enforce STOP, owner/CAS, active-model safety, disk/cgroup limits, HTTPS download-host allowlist, and never log credentials or signed URL query strings.
4. For new external downloads prefer nox_drive_first.py ingest: HTTPS to rclone rcat with exact size to Google Drive; no full local disk copy. For existing inactive model weights prefer offload to Google Drive. No deletion of source.
5. The official rclone chunker overlay noxchunks: with 1Gi chunk size transparently splits/reassembles large logical files; do not invent independent chunk file names.
6. Accept completion only after full SHA256+size readback, immutable promotion and a second exact readback. Retain private receipt and never claim success from a source commit.
7. For model inference restore from noxchunks:WARM through the existing nox_drive_prefetch.py verified SSD, then RAM/GPU admission; no direct layer seek over Drive.
8. Failed transfers go to HOLD with approved retriable lease. Preserve incomplete STAGING and all active weights; cleanup requires exact owner action.
9. Preserve high-priority chat, C01-C08 identity and S03. No model-answer suggested shell commands, external API token export or unconditional automatic file deletion.
10. Use nox-control/NOX_DRIVE_FIRST.md as the executable guide and its source/receipts for real acceptance.
