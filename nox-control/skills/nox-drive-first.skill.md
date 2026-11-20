# NOX Drive-first skill (v2 · receipt-driven operational learning)

Use the **existing NOX native queue only**, for owner-approved model-weight transfer via Google Drive. The model may propose, but cannot approve or execute. No separate dispatcher, external paid API, shadow queue, training weight mutation or deletion.

## Deterministic action selection
- **ingest**: owner-reviewed HTTPS model URL, publisher-proven SHA-256 and size → Drive DOWNLOADS via streaming rclone; never spool whole model on SSD.
- **offload**: an owner-approved INACTIVE local .gguf/.safetensors, exact full SHA and size → Drive WARM. Never delete local source or active weights.
- **restore_ssd**: one approved Drive WARM asset → private SSD cache with full SHA-256; RAM/GPU loading is a separate approved admission. Never claim the model is loaded from a staged file.
- For any other request, do not invent a Drive operation or run model-written shell commands.

## Admission order (fail closed, not blind retries)
1. Valid authenticated owner, exact manifest path+SHA, current owner/CAS lease, immutable TaskID and idempotency key.
2. On the ACTUAL Vast host, a trusted `noxdrive` OAuth config with the pinned project-root folder and a successful Google read; ChatGPT Drive authorization is separate.
3. The host MUST have registered `nox.drive.first.native.v1` in the live native dispatcher. Installing a Python file is NOT registration. The observed 2026-11-20 dispatcher uses a STATIC `HANDLERS` dict (21 entries), not a `register_handler()` hot API. Require an owner-approved exact-source integration and a verified live receipt before emitting executable jobs.
4. STOP/maintenance clear, foreground chat idle, current native claim/CAS valid, IO_LIGHT cgroup/SSD admission; keep the strict transport 384 MiB raw cgroup safety threshold unless an owner-reviewed change is independently approved.
5. Request the existing queue; `QUEUED_NOT_EXECUTED` is not success. Verify full SHA/size of STAGING, immutable promotion and a SECOND remote SHA/size readback, with a private receipt.

## Learn from outcomes without unsafe self-modification
- After a real owner-native attempt, read only its verified private receipt. Store/reuse the **normalized status code, TaskID, source SHA, cause and next action** in existing private task/skills memory; never copy OAuth tokens, private model content, signed URLs or personal S03 into a training corpus.
- `CONFIG_MISSING` or `HOLD_GOOGLE_OAUTH_REQUIRED`: stop new remote attempts until real host authorization changes. Do not loop and burn retries.
- `HOLD_NATIVE_REGISTRATION`: complete reviewed live static-handler binding; do not create another worker, queue or fake `register_handler()` callback.
- `DEFERRED_OWNER_OR_CHAT` or low cgroup headroom: yield to chat and wait for a FRESH resource/lease proof. Never bypass STOP.
- SHA/size drift, unknown source, or invalid manifest: HOLD, preserve originals and require owner approval of a new exact manifest.
- If a task already has a queued or running idempotency key, reconcile its terminal receipt before proposing again. One failed owner command is not permission for automatic duplicate submission.
- Update knowledge from successful **full remote readback** only, with source link and timestamp. Learning here means improved planner/tool decisions, NOT a claim of LoRA/QLoRA training or new neural weights.

## Operational safety
The official rclone `noxchunks:` 1Gi chunker is logical and transparent; never read physical pieces as model files. Persist STAGING on failed transfer pending owner-reviewed cleanup. Preserve current model, C01–C08 persona, S03, optimizer, checkpoints and active GPU chat. STOP always wins.

## Acceptance levels
`SOURCE_INSTALLED` ≠ `HANDLER_REGISTERED` ≠ `GOOGLE_READ_CONNECTED` ≠ `GOOGLE_WRITE_READBACK_SHA` ≠ `VERIFIED_SSD_STAGE` ≠ `GPU_LOADED`.
Do not report DONE or original295 acceptance without the corresponding native job, owner/CAS receipt and physical operation proof.

Executable references: `nox-control/NOX_DRIVE_FIRST.md`, `nox-control/NOX_DRIVE_NATIVE_BINDING.md`, `nox_drive_first.py`, `nox_drive_prefetch.py`, `nox_drive_native_binding.py`.
