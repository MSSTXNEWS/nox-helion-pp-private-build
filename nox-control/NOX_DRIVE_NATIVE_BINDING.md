# NOX Drive-first: integration with the existing native task dispatcher

## Available behavior

The existing NOX Drive-first **source** is already installed on Vast at:
`/root/nox/ops/drive-auth/nox_drive_first.py`. The owner-pinned
`drive_reconnect_install` additionally stages:
`nox_drive_native_binding.py`, `nox_drive_prefetch.py` and the exact
`skills/nox-drive-first.skill.md` in the same server path.

The bridge exposes:
- `capability_descriptor()` — public model-facing, bounded tool instructions.
- `NativeDriveBridge.propose(...)` — exact owner-approved job to the **existing** queue; no transfer inline.
- `NativeDriveBridge.worker(payload,cancel=...)` — executes a claimed and leased job after fresh owner, STOP, foreground/chat and IO_LIGHT resource checks.
- `NativeDriveBridge.register_to_existing_dispatcher(register_handler,actor=...)` — explicit, existing owner-approved callback; only a host that actually supports the new handler may register it.

The handler ID is `nox.drive.first.native.v1`. It is **not** an existing approved native handler yet. Installing files or an instruction file cannot change an active dispatcher process and must never be claimed as registration.

## Scope and learning

The owner-reviewed planner must expose the native tool descriptor from
`capability_descriptor()`. The model's choices are:
- `ingest`: a new verified public HTTPS model to Google Drive DOWNLOADS, without storing a full local model
- `offload`: an owner-verified inactive local weight to Drive WARM (no local deletion)
- `restore_ssd`: Drive WARM → verified SSD, **not** RAM/GPU loaded.

The model is **not** the approver. NOX's existing authenticated owner must
approve a private manifest under `/root/nox/ops/drive-auth/private/drive-tasks` (mode 0600) and its exact SHA-256.
TaskID is bound into the manifest for ingest/offload; for restore_ssd one asset
and remote `noxchunks:WARM` are required. These are only proposed, not executed,
until the existing dispatcher takes a real owner/CAS lease and claims the job.

Callbacks required from the **already-installed native dispatcher**:

    is_owner(actor)           # existing owner authentication
    stop_active()            # existing STOP
    lease_current()          # existing owner writer/CAS lease
    foreground_active()      # existing chat priority
    resource_admission(kind)  # existing IO_LIGHT memory/disk admission
    enqueue(handler,payload,idempotency_key) # existing native enqueue

Bind only using reviewed real host callback methods; do not invent substitutes
or make a shadow queue. The callback registration must be compatible with the
actual running dispatcher version and done through its owner-review transaction.
No arbitrary model-generated shell commands are allowed.

## Native acceptance evidence

1. Server installed SHA readback of `nox_drive_native_binding.py` plus
   `nox_drive_first.py`, exact source/skill pin and no process side effects.
2. Host callback registration receipt for `nox.drive.first.native.v1`.
3. Existing queue job-id, actual native claim/lease/STOP/IO resource acceptance.
4. Real Google OAuth: valid `noxdrive` config, approved root, authenticated read.
5. A real small authorized upload and readback, complete SHA/size, staged and promoted.
6. `restore_ssd` readback on demand; separately admit RAM/GPU via existing NOX loader.

**Current known blocker:** owner-host Google Drive OAuth was `CONFIG_MISSING`
in prior Vast native probe, and native handler registration has not been
proved. `QUEUED_NOT_EXECUTED` or source tests are never DONE. Never delete
models, S03, training/checkpoints, or override STOP to force completion.

References:
- [Source and owner guide](https://github.com/MSSTXNEWS/nox-helion-pp-private-build/blob/main/nox-control/NOX_DRIVE_FIRST.md)
- [rclone chunker](https://rclone.org/chunker/)
- [rclone Google Drive](https://rclone.org/drive/)
