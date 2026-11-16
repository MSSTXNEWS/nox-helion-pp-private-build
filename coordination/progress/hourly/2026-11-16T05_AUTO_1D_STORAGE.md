# AUTO 1D · cold storage safety · 2026-11-16 05:45 МСК

instructions_version: 0.0.6
accepted_head: bd7dd72c7fad7e214acca235d488902f0714d822
scope: source-only, no native OneHost lease
error_id: NOX-P0-COLD-EVICTION-WITHOUT-INDEPENDENT-RESTORE-20261116

PROVEN SOURCE DEFECT: Original nox-control/nox_cold_drive.py evict_verified() permitted deleting a verified source model after a streaming remote rclone cat SHA, without independently restoring the complete remote model to an isolated mount. The source had no independent restore prerequisite.
PATCH: --evict now requires --restore-test-dir; before unlink, retrieve full remote file again into a separate existing filesystem using rclone copyto, compare exact length and SHA256, remove the temporary copy, reverify source identity, active manifest and open process maps. RAM/cgroup or SSD free reserves gate recovery. No separate backend or trainer.
VALIDATION: exact-commit source workflow and readback must be checked after CAS; synthetic positive tests are not physical owner backup evidence.
1. Drive vs OneHost installed/ZIP/META/duplicates: HOLD (Drive metadata discovery does not provide current authenticated OneHost file inventory).
2. Offsite cold SHA/read access: HOLD (Tigris credentials and original OneHost cloud rclone current success not authenticated in this run; cannot infer from old receipt).
3. Coherent S03/config/checkpoint/optimizer snapshot: HOLD (no current exact owner PID/STOP/single-writer host lease).
4. Independent offsite restore: NATIVE HOLD (no current cloud credential and separately mounted native recovery sandbox; new guard is source-only).
5. RAM-cache/SSD cleanup: NATIVE HOLD (no independent native restore or active-reference readback; 0 files deleted, freed_bytes_verified=0).
Source readback SHA, workflow result and final commit: see following GitHub commit and CI. Do not equate model source fixture with deployment.
LESSON: A remote whole-file hash is necessary but not equivalent to a successful independent restore; safely fail closed before unlink.
NEXT: Read only original host inventory, owner lease/STOP and exact remote S03+optimizer restore evidence; then run native staged restore with SHA and ownership before any deletion.


## Final exact-source acceptance and handoff

- Primary fix commit: `35463e7fc8a32e9634d54e763fd9147ff5fe8684`; exact source candidate CI [#43795097110](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43795097110) **FAILED 40/41**. No false PASS: original six-process batch test had six `FileNotFoundError` after a prior test changed temporary fake-rclone PATH.
- Second stable error_id: `NOX-P0-COLD-FORKSERVER-STALE-RCLONE-PATH-20261116`; root cause: default persistent Python forkserver process pool reused stale environment across sequential 6-worker test batches. Source fixed to explicit multiprocessing `spawn` per batch. Failure was only in offline fixture, no proof of native provider transfer.
- Final source/test commit: `49bc255f85ed23be5a1c47f06b79374ec79e809d`. [Exact-source workflow #43795550177](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/actions/runs/43795550177) completed SUCCESS: `python3 -m py_compile`, unittest **41/41 PASS** including tmpfs independent restoration and rejection of corrupt bytes, same-mount restoration, missing restored copy, protected active references, six clean workers and no-deletion incomplete batch. Original production OneHost untouched.
- Git readback source blobs: cold module `eea01a2885833ddcecc3d62df0f379db95acdfc5`, test `6faa5690c3ae00bce629b5a1080a52adb1db306d`, dedicated workflow `1a1d759c7d89ca45c2a0d37699d39d63c8f3ef9d`. Latest observed sibling branch head includes both source blobs; no need for another deployment.
- Drive owner metadata read (NOT native remote SHA): canonical WEB V29.3 frozen ZIP `NOX_HELION_WEB_V29_3_FROZEN_20261113.zip` remains present, size `85,218,272` B at [Google Drive](https://drive.google.com/file/d/1mRWUd7zwHNdJqTGelX7o0uSRSoNXyh01/view). Drive project exports folder listed 100 entries, of which 46 ZIPs, listing may be partial; candidate ZIP names and file sizes alone do **not** establish bytewise duplicates or OneHost installed equivalence. The `NOX_COLD_WEIGHTS_OFFSITE_20261115` Drive folder presently contains three listed metadata/media items, not an independently restored S03/optimizer/model backup. The `NOX_SELECTED_DOWNLOADS_AND_STORAGE_20261116.json` is a planning/inventory record, not live server proof.
- Final native receipt: `OWNER_NATIVE_READBACK=HOLD`; `S03_CONFIG_CHECKPOINT_OPTIMIZER_CONSISTENT_SNAPSHOT=HOLD`; `INDEPENDENT_OWNER_OFFSITE_RESTORE=HOLD`; `GPU_STOP_LEASE=UNKNOWN`; installed native paths `[]`; deleted obsolete paths `[]`; `freed_bytes_verified=0`. Selftest success is strictly SOURCE_TESTED, never LIVE_VERIFIED.
- Lesson: first require full separate-filesystem recovery and accurate process ownership before deletion; secondly each parallel pool must use a fresh environment rather than a forkserver stale after prior fixture teardown.
- **One next action → AUTO 2D/owner OneHost**: obtain current authenticated native OneHost snapshot/STOP+writer lease, protected S03/config/optimizer checkpoint backup, and independent SHA restore on a separate readback mount; only then compare exact duplicates and safely consider deletion.
