# NOX V59 — Google Drive warm/cold weights → RAM

Status: SOURCE ONLY / NOT DEPLOYED. This is a conservative add-on to the *existing* OneHost, not a new model server or GPU scheduler.

## Architecture

- HOT: current NOX chat model and active trainer remain under their existing process/scheduler ownership.
- WARM: Google Drive is the durable source. The first request copies a verified model file into a dedicated tmpfs RAM cache. Subsequent requests reuse the verified RAM copy.
- COLD: same backing store; fetch only upon explicit need. No automatic eager prefetch at boot.
- S03, SQLite WAL, latest train checkpoints, optimizer states and the current live model remain persistent on local disk. They must have separate verified backup before any cleanup.
- NEVER run training directly over a Google Drive mount. A model pulled to RAM still needs to be loaded into CPU/GPU by the **existing** model loader. This script does not change live routing or evict VRAM.

## Manifest example (replace placeholders only with verified inventory)

```json
{
  "schema": "NOX_RAM_TIER_V1",
  "models": {
    "teacher-example": {
      "tier": "warm",
      "remote": "noxdrive:NOX_HELION/WEIGHTS/WARM/teacher.gguf",
      "bytes": 123456789,
      "sha256": "REPLACE_WITH_REAL_64_HEX_SHA256"
    }
  }
}
```

Manifest must be generated from the exact file uploaded and checked against an independent read-back. Never classify by extension alone; link every model to owner, active process / model ID and trainer reference before upload.

## Prerequisites for actual use

1. Admin establishes a dedicated private Google Drive rclone remote **named** `noxdrive:` using an approved credential channel. No secrets in GitHub, shell logs, Notion or the manifest. Server V58 reported that no working remote was configured.
2. Create a dedicated tmpfs mount with a strict size cap and permissions, e.g. mount via fstab/systemd rather than silently placing files onto an SSD fallback. Ensure system RAM, tmpfs, current process RSS and GPU memory allow the requested model. Do **not** set tmpfs to fill all RAM.
3. Upload each idle candidate from Vast to Drive without deleting the source. Compare original SHA256 to remote read-back; record lengths, immutable destination and validation timestamp in the inventory.
4. Verify existing chat, model loader, training, S03 read/write, checkpoint recovery. Only then approve an individual local original for removal. An active model or last rollback copy must never be removed.
5. Call `python3 -m nox_runpod.teacher_mesh.v59.drive_ram_cache --manifest /secure/nox-weight-manifest.json get <model-id>` from the existing NOX model resource brain. The command prints a verified RAM path; the existing loader owns GPU admission and process lifetime.
6. On insufficient RAM, rclone failure, SHA mismatch, or unavailable Google Drive: fail closed, keep running models unchanged; do not start duplicate trainers.
7. Reclaim only verified, inactive cache files, and only when there are no leases/loads using them. **Automatic eviction is intentionally NOT implemented** until integrated with existing owner/lease system.
8. For GPU0 utilization 0%, first inspect its compute processes, memory allocation, trainer rank, topology and memory reserve. Do not fill it blindly.

## Acceptance gates

- G1: remote configured and accessible (pending)
- G2: manifest entries verified source+remote hashes (pending)
- G3: RAM cache loads, restart and corruption tests pass (pending)
- G4: OneHost exact loader integration, no duplicate backend (pending)
- G5: checkpoint restore + S03 consistency + live chat tests pass (pending)
- G6: no-loss measured local disk release and safe training restart (pending)

Invariants: NO-LOSS, STOP, SAFETY / no fake PASS, no direct remote deletes, no SSD caching fallback, no training restart without read-back of checkpoints.