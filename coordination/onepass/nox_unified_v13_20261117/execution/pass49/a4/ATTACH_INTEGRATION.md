# Existing trainer attachment, stage only

Task6A03 / runNOX-49-20261117. Extends source commit35d92ce6838703056526a5ce8b57751d176bf2ae without a second trainer, process, queue, scheduler or claim mechanism.

The original trainer Git blobc2e7b231d5af8b9493ec3578144f95e60ff31c7c has only its STOP and holdout callbacks. The reviewed replacement adds resource_control at the existing run() and Trainer.add_callback() points.

To prepare a new local overlay (does not import the trainer, start training, or modify the supplied source tree):

```sh
python stage_existing_trainer.py --source-root /path/to/exact/source --stage-dir /path/to/new/local/stage
```

All three old blobs must match exactly; the new payloads must match both source receipts. Existing destinations, source-nested output, symlinks and /root/nox destinations are refused. Readback of all staged payloads is checked. This overlays the existing project only; it is not a standalone replacement runtime.

The existing owner handler, in its already claimed execution context, creates:

```python
from nox_runpod.teacher_mesh.v135.resource_native_binding import ExistingTrainerBinding
binding = ExistingTrainerBinding(task_id, existing_args, owner_read_fresh_admission)
# Existing native callback wiring points to these methods:
# request_soft_yield -> binding.request_soft_yield
# request_resume -> binding.request_resume
# observation -> binding.observation
# Only the existing admitted owner claim handler calls:
# binding.run_existing()
```

Construction/import do not launch training. run_existing() calls the existing run(args, resource_control=...) exactly once in the same process; lock+PID guard prevent double entry/fork reuse. Durable cross-process claims remain in the original dispatcher under its existing native_subagents.lock. No separate lockfile or task producer is introduced.

owner_read_fresh_admission(receipt) returns exactly {native, approval}; credentials remain in the existing HMAC environment. The binding invokes the real existing verify_owner, preserving action/instance/TTL/signature and fullbase resource/backup/model gates. Signed native evidence must also bind resource_pause_task_id, resource_pause_checkpoint_sha256, resource_pause_step to the actual pause receipt. Base identity, train/dev/holdout hashes and shard bytes must stay unchanged. Original native launch metadata is checked again before entry. Resume still uses conservative startup fullbase resource headroom, so resident allocations may cause HOLD; this source package does not claim freed memory or solve native resource eligibility.

Exact native blocker: current final dispatcher integration has no assignment to _nox_owner_autonomy_native (HOLD_NATIVE_POOL_CALLBACKS). The root lease holder must bind the original owner adapter and this object, keep its one durable claim owner, provide fresh signed admissions, and verify native pause/checkpoint/resume after backup restoration, storage admission, optimization and exact trainable-model admission. No server changes or native training were performed here.

Acceptance:12 source tests PASS (actual HMAC verification with isolated policy/handler fixtures, expiry/signature/model/checkpoint denials, concurrent single entry, PID guard, stage conflict/symlink/mismatch denial). The staging executable also completed against all three exact original blobs, reading back five overlay files. Previous unchanged safe-point10 tests were not rerun. No native card acceptance.
