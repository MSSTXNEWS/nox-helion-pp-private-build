# NOX storage streaming repair — shared patch, not a native deployment

instructions_version 0.0.6. Source origin is the existing `main:nox-control/nox_cold_drive.py`, blob `a2455fca402e7994b41287e2f040849f6e76b0c8`. The helper was missing from the common feature branch at `4eaeda2f`. No second backend, scheduler, memory store or chat was created.

## Verified in this run

37/37 local source tests, including a six-OS-process transfer/readback fixture. The fake transport exists only inside `test_nox_cold_drive.py`; production code calls actual `rclone`. GPU/server/Drive changes are **not verified**. Server bytes moved/deleted in this run: **0**.

The original upload CLI was unreachable: `getattr(args, 'reserve_gib', 0) < 1` rejects every upload. Also the allegedly streaming verification downloaded another full model copy to SSD. Both defects are repaired. Symlink/hardlink and training-state protections, content-addressed remote destinations, fresh active/protected manifests, bounded readback, cgroup-aware RAM admission and no-replace warm publication are included.

## Native use after authorized OneHost access

Use the existing OneHost maintenance/writer lease so another executor, model loader or trainer cannot change the inventory during deletion. This utility's file lock coordinates its own instances only; it does not replace the OneHost lease. Preserve a rollback copy of the native helper and the complete HF model's config/tokenizer/index assets. This helper moves explicitly listed weight files; it is not a full HF bundle packager or an end-to-end training resume validator.

`python nox-control/test_nox_cold_drive.py`

Single-file copy (no deletion): `python nox-control/nox_cold_drive.py upload --file /ABSOLUTE/INACTIVE.gguf --remote EXISTING_REMOTE:NOX_COLD --receipt-dir /ABSOLUTE/RECEIPTS`

Batch copy: `python nox-control/nox_cold_drive.py batch --manifest /ABSOLUTE/FILES.json --remote EXISTING_REMOTE:NOX_COLD --receipt-dir /ABSOLUTE/RECEIPTS --workers 6`

`FILES.json` must contain `files`, an explicit list of objects with exactly `path` (absolute local path) and `sha256` (lowercase 64 hex). No directory sweep or inferred deletion. All copies must verify before batch eviction can begin.

`--evict` additionally requires `--active-manifest /ABSOLUTE/LIVE.json`. LIVE.json has `generated_at` as Unix seconds, `active_paths`, `protected_paths` and `evict_paths` arrays. Age at deletion must be at most 300 seconds; refresh the inventory after long uploads. The native caller must hold the shared writer lease. Unreadable process activity, an open/mapped model, changed identity/hash, or missing permission keeps the source. Delete is exact-file only, not recursive.

Warm loading: `python nox-control/nox_cold_drive.py load --remote EXISTING_REMOTE:NOX_COLD/SHA/NAME.gguf --ram-dir /dev/shm/nox_models --sha256 EXPECTED_SHA --reserve-gib 12`. Use the actual destination recorded in the receipt. It verifies bytes and preserves an existing target. RAM is ephemeral and is never the only backup.

## Next real result

Run this exact helper in the existing authorized native maintenance session, prove configured storage authentication without logging credentials, obtain actual remote SHA readback, and then record observed disk-free delta. Do not convert local tests, a repository commit, or historical read-only SSH into a claim of installed accelerators, migrated weights, stopped processes or faster chat. Native credential workflows remain manual owner-gated.

The companion download_manifest.json records the latest owner-approved combined LoRA → merge + periodic full-parameter distillation policy and compatible candidates. It is a reconciliation list, not a claim that the packages were downloaded or installed.
