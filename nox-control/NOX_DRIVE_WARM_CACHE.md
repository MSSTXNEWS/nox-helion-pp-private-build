# NOX Drive warm-cache — owner-only installation

Status: SOURCE ONLY, NOT installed or OAuth-authorized on Vast.ai.

## Purpose
- Authenticated rclone Drive -> SSD cache -> RAM /dev/shm -> GPU consumption only by existing NOX serving route.
- SHA-256 per approved asset, manifest SHA pin, private receipts, no overwrite, no delete, STOP flags.
- Default transport 4 streams, 8 MiB buffer, 4 TPS. Adjust from observed data, not theory.
- RAM cache stage requires raw cgroup headroom >= model bytes + 4 GiB; do not count inactive_file as directly free RAM.

## Once-only authorization
1. Google Drive connector in ChatGPT does not give NOX a token.
2. On a trusted machine configure rclone Google Drive with your own Google OAuth client ID; rclone shared client ID is being retired in 2026 (see https://rclone.org/drive/).
3. Restrict to the NOX project folder (folder ID 1ewQ-R7z33fN0fKoMNNuFzv1_3rCEP96v) and a dedicated NOX identity; avoid whole-account access.
4. Securely install credentials on the actual Vast host, readable only by the service account. Never expose tokens, private keys or OAuth codes in GitHub, logs or chat.
5. Run rclone lsf noxdrive: on the host. If it fails, return NOT_CONFIGURED, not PASS.

## Approved model manifest example
{"schema":"nox.drive.prefetch.v1","remote":"noxdrive:NOX_COLD","assets":[{"name":"example.gguf","size":123456789,"sha256":"<64 lowercase hex characters>"}]}

Use real model filenames, exact bytes and SHA-256 from verified manifests. Never include S03/checkpoints/training/optimizer/database data.

## Verified copy of an inactive model

Use the owner-authorized Drive profile and an existing private receipt directory. Copy only an approved, inactive model to its approved project subfolder. The command refuses to replace differing remote content and independently streams the remote object to check byte length and SHA-256. It leaves the local file in place.

```sh
python3 -B nox-control/nox_cold_drive.py upload \
  --file /absolute/path/to/approved-model.gguf \
  --remote noxdrive:NOX_COLD \
  --receipt-dir /root/nox/private/cold-receipts
```

The upload receipt proves a model copy only. Verify S03 and optimizer/checkpoint backups independently through the owner-encrypted restore path before accepting them as recoverable.

## Staging
Precreate private 0700 directories and exact manifest in owner-only location.
Disk command: python3 nox-control/nox_drive_prefetch.py --manifest /root/nox/private/allowlist.json --manifest-sha EXPECTED_SHA256 --destination /root/nox/cache/warm-ssd --mode disk --execute
RAM command: python3 nox-control/nox_drive_prefetch.py --manifest /root/nox/private/allowlist.json --manifest-sha EXPECTED_SHA256 --destination /dev/shm/nox_models --ssd /root/nox/cache/warm-ssd --mode ram --execute
Without `--execute`, the plan reads the manifest and destination directory metadata without transferring a model or creating a lock file.

## Native gates
The new source deliberately DOES NOT replace already pinned owner_drive_ram_bridge.py, owner_native_drive.py or existing dispatcher. It cannot grant OAuth or load a model onto GPU. Only native owner/CAS, STOP, cgroup, S03 and source-hash gated installation may integrate these components.
Success criteria: authenticated rclone listing; exact SSD SHA receipt; RAM SHA + resource admission; separate GPU service readback. No PASS without each concrete receipt.

Official transport documentation: https://rclone.org/drive/ and https://rclone.org/docs/
