"""Cooperative safe-point control for the existing, admitted single-rank trainer.

No service, signal, GPU allocation or authorization is created here. The owner
dispatcher holds this controller and supplies fresh signed admission on resume.
Pause retains resident tensors: it releases compute, NOT reserved GPU memory.
Restart recovery continues to use verified_resume.admit_resume, including the
independent restore gate. These callbacks never bypass that gate.
"""
from __future__ import annotations
import json
import os
import threading
import copy
from pathlib import Path
from .verified_resume import checkpoint_tree_sha256


class TrainerResourceControl:
    def __init__(self, task_id, resume_admission):
        if not isinstance(task_id, str) or not task_id or not callable(resume_admission):
            raise ValueError('HOLD_RESOURCE_CONTROL_BINDING')
        self.task_id = task_id
        self._admit = resume_admission
        self._cv = threading.Condition()
        self._state = 'RUNNING'
        self._receipt = None
        self._request = None

    def request_soft_yield(self, task_id, safe_boundary, checkpoint_sha256, cursor):
        """Compatible with owner_autonomy_pool's existing native callback.

        The supplied old checkpoint/cursor are request provenance, never proof
        of the new safe point. The callback below produces its actual receipt.
        """
        if task_id != self.task_id or safe_boundary != 'optimizer_step':
            return False
        with self._cv:
            if self._state not in ('RUNNING', 'REQUESTED'):
                return False
            self._request = dict(task_id=task_id, safe_boundary=safe_boundary,
                                 previous_checkpoint_sha256=checkpoint_sha256,
                                 previous_cursor=cursor)
            self._state = 'REQUESTED'
            return True

    def observation(self):
        with self._cv:
            return json.loads(json.dumps(dict(state=self._state,
                yield_completed=self._state == 'PAUSED',
                vram_released=False, receipt=self._receipt)))

    def request_resume(self, task_id, checkpoint_sha256):
        # Admission may involve I/O; never hold the pause condition while doing it.
        with self._cv:
            if (task_id != self.task_id or self._state != 'PAUSED'
                    or checkpoint_sha256 != self._receipt['checkpoint_sha256']):
                return False
            receipt = copy.deepcopy(self._receipt)
        # Trusted existing owner code authenticates a *fresh* resource snapshot;
        # a browser flag or unverified caller-provided bool is not an admission.
        if self._admit(copy.deepcopy(receipt)) is not True:
            return False
        if checkpoint_tree_sha256(Path(receipt['checkpoint'])) != checkpoint_sha256:
            raise RuntimeError('HOLD_SAFE_POINT_CHANGED_BEFORE_RESUME')
        with self._cv:
            if self._state != 'PAUSED' or self._receipt != receipt:
                return False
            self._state = 'RESUMING'
            self._cv.notify_all()
            return True

    def callback(self, TrainerCallback, stop_check):
        owner = self
        class SafePointCallback(TrainerCallback):
            def on_train_end(self, args, state, control, **kwargs):
                with owner._cv:
                    owner._state = 'FINISHED'
                    owner._cv.notify_all()
                return control

            def on_step_end(self, args, state, control, **kwargs):
                stop_check()
                with owner._cv:
                    if owner._state == 'REQUESTED':
                        control.should_save = True
                return control

            def on_save(self, args, state, control, **kwargs):
                stop_check()
                with owner._cv:
                    if owner._state != 'REQUESTED':
                        return control
                    owner._state = 'SAVING'
                try:
                    step = getattr(state, 'global_step', None)
                    if type(step) is not int or step < 1:
                        raise RuntimeError('HOLD_SAFE_POINT_CURSOR')
                    checkpoint = Path(args.output_dir) / f'checkpoint-{step}'
                    saved_state = checkpoint / 'trainer_state.json'
                    tree_sha = checkpoint_tree_sha256(checkpoint)
                    if saved_state.stat().st_size > 2_000_000:
                        raise RuntimeError('HOLD_SAFE_POINT_TRAINER_STATE')
                    saved = json.loads(saved_state.read_text('utf8'))
                    names = {p.name for p in checkpoint.rglob('*') if p.is_file()}
                    if (saved.get('global_step') != step
                            or not any(n.endswith('optim_states.pt') for n in names)
                            or not any(n.endswith('model_states.pt') for n in names)
                            or not any(n == 'rng_state.pth' or n.startswith('rng_state_') and n.endswith('.pth') for n in names)):
                        raise RuntimeError('HOLD_SAFE_POINT_INCOMPLETE_STATE')
                    # ZeRO optimizer checkpoint contains optimizer/scheduler/scaler;
                    # Trainer state+RNG preserve its deterministic sampler cursor.
                    # Presence/hash are source checks, not an offsite restore proof.
                    if getattr(args, 'ignore_data_skip', False) is not False:
                        raise RuntimeError('HOLD_SAFE_POINT_DATA_SKIP_DISABLED')
                    record = dict(schema='NOX_TRAINER_SAFE_POINT_V1',
                        task_id=owner.task_id, checkpoint=str(checkpoint),
                        checkpoint_sha256=tree_sha, cursor=dict(global_step=step,
                            epoch=saved.get('epoch'), seed=args.seed,
                            gradient_accumulation_steps=args.gradient_accumulation_steps),
                        safe_boundary='optimizer_step', optimizer_checkpoint_present=True,
                        rng_checkpoint_present=True, native_restore_verified=False,
                        vram_released=False, request=owner._request)
                    # Receipt is outside checkpoint: hashing cannot self-reference.
                    target = Path(args.output_dir) / f'nox-safe-point-{step}.json'
                    with target.open('x', encoding='utf8') as f:
                        os.chmod(target, 0o600)
                        json.dump(record, f, sort_keys=True, allow_nan=False)
                        f.write('\n'); f.flush(); os.fsync(f.fileno())
                    with owner._cv:
                        owner._receipt = record
                        owner._state = 'PAUSED'
                        owner._cv.notify_all()
                        while owner._state == 'PAUSED':
                            owner._cv.wait(timeout=.25)
                            stop_check()
                        if owner._state != 'RESUMING':
                            raise RuntimeError('HOLD_SAFE_POINT_STATE')
                        # Same-process continuation keeps exact in-memory model,
                        # optimizer, scaler, RNG and iterator. No replay/skip/reset.
                        owner._state = 'RUNNING'
                    return control
                except BaseException:
                    with owner._cv:
                        owner._state = 'FAILED'
                        owner._cv.notify_all()
                    raise
        return SafePointCallback()
