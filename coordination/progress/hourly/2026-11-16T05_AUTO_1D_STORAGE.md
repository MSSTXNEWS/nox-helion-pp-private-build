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
