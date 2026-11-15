# NOX V59 — Windows / Linux Cloudflare R2 migration

State: SOURCE PREPARED, NOT INSTALLED on owner's computer or Vast. No credentials committed.

## Protected credentials

The screenshots contained exposed Cloudflare API/S3 credentials. Revoke and replace them before production. Never paste credentials into this repository, Notion, chat transcripts, PowerShell history, or publicly accessible URLs. Store the replacement S3 access key ID and secret key in a password manager/OS secrets store and inject them as process environment variables:
- `RCLONE_CONFIG_NOXR2_ACCESS_KEY_ID`
- `RCLONE_CONFIG_NOXR2_SECRET_ACCESS_KEY`

R2 endpoint: `https://6ab1503ad55d0a429062ad470c448012.r2.cloudflarestorage.com`
The `/123` URL suffix was **not** proof of bucket name: confirm the bucket in Cloudflare.

The public `r2.dev` URL is **not** an S3 API endpoint and must not be used for private models.

## Integration

Works with rclone on both Windows and Linux. Require at least rclone on PATH and Python 3.

Read-only probe:

```text
python nox_runpod/teacher_mesh/v59/r2_archive.py --bucket ACTUAL_BUCKET probe
```

Upload **one verified inactive** warm model to a private R2 object, without deleting source:

```text
python nox_runpod/teacher_mesh/v59/r2_archive.py --bucket ACTUAL_BUCKET upload MODEL.gguf --tier warm
```

Upload cold weights similarly with `--tier cold`. Result includes SHA-256, number of bytes and remote path. Persist only these metadata in the NOX weights manifest.

Restore from a recorded full object path to a **pre-existing** cache parent:

```text
python nox_runpod/teacher_mesh/v59/r2_archive.py --bucket ACTUAL_BUCKET restore --object NOX/WEIGHTS/WARM/MODEL.gguf --sha256 EXPECTED_SHA256 CACHE/MODEL.gguf
```

On Linux, `CACHE` must be a verified dedicated tmpfs if the intended target is RAM. On Windows, use a verified RAM-disk volume or use a local SSD cache with a strict size budget; Windows normal file paths do **not** imply RAM residency. Load the restored file with the existing OneHost model loader and obtain a lease before cache eviction.

## Migration and no-loss

1. Inventory models and identify active processes and training checkpoints. Do not migrate actively written files.
2. Upload only idle model files; verify **streamed readback** SHA-256 and size from R2.
3. Verify the replacement file restores and passes existing loader's acceptance.
4. Independently back up checkpoints/optimizer states and S03. Keep SQLite WAL with SQLite-aware backup, not raw copy from a live database.
5. Only then plan staged deletion of local duplicates under an owner-approved manifest, never through the upload command.
6. Keep chat hot model, latest recoverable training checkpoint, S03 and required operational files local.
7. Do not force 100% GPU/CPU/RAM utilization or restart training until checkpoint readback and STOP/rollback work.

To use on both a laptop and cloud instance, install the same code and secure credential configuration on each, but use distinct least-privilege tokens per machine. Avoid exposing a home computer as an unauthenticated file server.

Acceptance remains HOLD until read/write access, end-to-end transfer, loader resume, training restart and Windows runtime tests are verified on the real machines.
