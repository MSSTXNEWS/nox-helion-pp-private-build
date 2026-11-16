# Qwen execution revision: preserve checkpoint25 and repair evaluation scheduling

## Problem and observed state

The running student saved a checkpoint every five successful updates. The same
`last_save` clock was also used to schedule holdout evaluation, so frequent
checkpoint saves postponed the evaluation indefinitely. The existing guard
correctly paused the old process at update25 with the last evaluation at10.

Native observation `6910931182`, Actions run `43828903713`, verified the complete
10-file checkpoint25 (519,902,179 bytes), 25 successful updates, no skipped
updates, and the `EVALUATION_STALE` guard. The old main chat model remained live.
This document describes the replacement execution protocol, not a claim that a
native installation or further optimizer updates have already passed.

## Preserved evidence

The original `qwen_student_training_entry.py`, training contract, RAM transport,
corpus, scientific lineage, accepted-six certificate and checkpoint25 remain
unchanged. The new runtime has a separate native filename,
`qwen_student_training_entry_revision.py`. Historical source proofs use the
exact archived admission, wrapper and entry preimages; they never label the
new executable as the old source.

The descriptor separately records the current runtime, shared verifier, six
consumers, dispatcher and finite activation issuer. No current source hash is
silently substituted into the historical scientific lineage.

## Runtime behavior

- Evaluation has its own completion clock, independent of checkpoint saves.
- Evaluation is due at the training goal, after 300 seconds, or after ten new
  successful updates, whichever applies first.
- The existing guard's stale threshold remains15. Its disk and quality policy
  values remain unchanged.
- Resume restores the optimizer, scheduler, scaler, adapter and RNG state.
- Sixteen actual holdout examples run with model mode and CPU/CUDA/Python RNG
  restored in `finally`, including interruption and exception paths.
- A witness binds counters, data cursor, adapter tensors, optimizer, scheduler,
  scaler and RNG signatures before and after evaluation.
- The first revised process saves a fresh checkpoint at the same update25
  before it can perform optimizer26. The checkpoint still has ten manifest
  payload files; the witness is nested in `student_state.json`.
- Subsequent media resumes restore and evaluate their actual checkpoint. The
  initial process permit is not reused as an identity claim for a later PID.

## Finite installation and activation

`owner_qwen_revision_install.py` uses the existing controller, maintenance and
training locks, in that order. It accepts only the exact stopped checkpoint25,
known old sources/configurations, and exact guard-owned pause/HOLD files. It
verifies all checkpoint payload hashes and records private native preimages.

The installer updates the existing guard, status reader, media handoff, media
guard, handback retry and Hermes hydration consumers as one source graph. The
existing dispatcher and idle proxy reload; the main chat model does not reload.
Only the known old flags are archived. Quality history is preserved while the
guard reports `BOOTSTRAP_EVALUATION` with optimizer permission closed.

The existing supervisor trainer slot is started once. After the actual fresh
same-counter evaluation is durably saved, the finite issuer verifies the full
checkpoint and its process-bound witness. Under the maintenance lock it applies
the unchanged quality/disk policy to that real result, then creates an immutable
activation receipt. It releases the lock and waits for the existing dispatcher
to publish a fresh matching `MONITORING` sample. The student requires both the
activation and that ordinary guard sample before its next optimizer step.

If model loading exceeds the finite first wait, the result is explicitly
`BOOTSTRAP_LOADING_PENDING`. `finalize_current()` can continue only that same
already admitted process; it contains no supervisor start call. Neither path
manually calls the guard tick or creates a background scheduler.

Before the trainer starts, rollback restores only exact owned file changes and
archived flags. Stop intentions are recorded before supervisor commands;
unsettled or foreign service states are not blindly restarted. After the
trainer starts, failure requests a checkpoint-aware pause rather than rolling
source code back beneath a live optimizer.

## Readback and scope

`owner_qwen_revision_observe.py` is a separate bounded read-only observation.
It verifies the current source graph, complete latest checkpoint, update chain,
evaluation witness, live trainer identity, guard and chat-status reader. It
reports new successful updates since25 and distinguishes them from the earlier
accepted-six checkpoint.

These proofs establish source provenance, resume continuity and actual
training/evaluation activity. They do not establish a general intelligence
improvement, consciousness, a successful merge into the main35B chat model, or
distillation of all teachers.

## Storage remains Drive/RAM based

The PC bridge is deferred. The verified builder adapter remains on server SSD
with its existing Drive copy. Hermes remains in server RAM with a pinned public
rehydration source; the RAM copy is not a durable backup. The revised hydration
consumer preserves the public weight identity, 72GiB RAM admission reserve,
3GiB tmpfs reserve and the existing downloader integration.

## Validation before native activation

Focused suites cover the independent evaluation timer, exact restore path,
same-counter permission barrier, evaluation-state continuity, source/lineage
separation, current/historical checkpoint bindings, guard/media/status
consumers, unchanged policy, exact flag archival and no-clobber writes. Native
execution must be reported separately with its actual Actions run and receipt.
