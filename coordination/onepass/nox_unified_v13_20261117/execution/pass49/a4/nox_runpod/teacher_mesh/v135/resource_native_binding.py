"""Existing owner-handler attachment; no thread, service or trainer is created.

This module runs only when the existing admitted owner handler explicitly calls
run_existing(). Merely staging/importing/constructing it cannot start training.
"""
from __future__ import annotations
import copy
import os
import threading
from pathlib import Path
from .resource_safe_point import TrainerResourceControl


class ExistingTrainerBinding:
    def __init__(self, task_id, args, read_fresh_admission):
        if not callable(read_fresh_admission):
            raise ValueError('HOLD_FRESH_ADMISSION_PROVIDER')
        from . import train_full_base_zero3 as trainer
        self._trainer = trainer
        self._args = args
        self._read_fresh = read_fresh_admission
        self._original = trainer._json(Path(args.native))
        self._ran = False
        self._entry_lock = threading.Lock()
        self._pid = os.getpid()
        self.control = TrainerResourceControl(task_id, self._readmit)

    def _readmit(self, receipt):
        # The provider obtains new signed evidence from the EXISTING owner
        # admission path. No credentials or signature are accepted from the UI.
        evidence = self._read_fresh(copy.deepcopy(receipt))
        if not isinstance(evidence, dict) or set(evidence) != {'native','approval'}:
            raise RuntimeError('HOLD_FRESH_SIGNED_ADMISSION')
        native, approval = evidence['native'], evidence['approval']
        secret = os.environ.get(self._trainer.SIGN_ENV, '').encode('utf8')
        self._trainer.verify_owner(native, approval, secret)
        # Current resource quantities may change; model/corpus identity may not.
        for field in ('student_base_sha256','student_shard_bytes',
                      'train_dataset_sha256','holdout_dataset_sha256'):
            if field not in self._original or native.get(field) != self._original[field]:
                raise RuntimeError('HOLD_READMISSION_MODEL_OR_CORPUS_CHANGED')
        if native.get('dev_dataset_sha256') != self._original.get('dev_dataset_sha256'):
            raise RuntimeError('HOLD_READMISSION_DEV_CHANGED')
        if (native.get('resource_pause_task_id') != self.control.task_id
                or native.get('resource_pause_checkpoint_sha256') != receipt['checkpoint_sha256']
                or native.get('resource_pause_step') != receipt['cursor']['global_step']):
            raise RuntimeError('HOLD_READMISSION_SAFE_POINT_BINDING')
        return True

    def request_soft_yield(self, task_id, safe_boundary, checkpoint_sha256, cursor):
        return self.control.request_soft_yield(task_id, safe_boundary, checkpoint_sha256, cursor)

    def request_resume(self, task_id, checkpoint_sha256):
        return self.control.request_resume(task_id, checkpoint_sha256)

    def observation(self):
        return self.control.observation()

    def run_existing(self):
        # Called in the existing owner handler's own execution context. Its run()
        # retains STOP, signed launch, backup/restore, storage, model and GPU gates.
        # Durable cross-process claiming belongs to the original dispatcher.
        # This lock only prevents concurrent entry into this one bound object.
        if os.getpid() != self._pid:
            raise RuntimeError('HOLD_BINDING_CROSSED_PROCESS')
        with self._entry_lock:
            if self._ran:
                raise RuntimeError('HOLD_EXISTING_TRAINER_ALREADY_ENTERED')
            self._ran = True
        if self._trainer._json(Path(self._args.native)) != self._original:
            raise RuntimeError('HOLD_INITIAL_ADMISSION_CHANGED')
        return self._trainer.run(self._args, resource_control=self.control)
