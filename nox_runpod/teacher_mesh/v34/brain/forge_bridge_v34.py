"""Safe native FORGE admission: only the existing NOX scheduler may train.

Source-side adapter; does not create a new trainer or a second model. It admits a
real requested optimizer job only with existing OneHost owner grant, correct ABI,
required space, trusted GPU telemetry and verified prepared training data.
Every step is independently rechecked by the native FORGE process.
"""
from __future__ import annotations
import math
import re
from dataclasses import dataclass
from typing import Callable

SHA = re.compile(r'^[0-9a-f]{64}$')

@dataclass(frozen=True)
class RequiredResources:
    minimum_vram_free_gb: float = 5.0
    minimum_ram_free_gb: float = 7.0
    minimum_disk_free_gb: float = 45.0
    safe_hotspot_c: float = 70.0
    max_consecutive_hot_readings: int = 3


def hold(reason):
    return {'state': 'HOLD', 'reason': reason, 'training_started': False,
            'student_weights_changed': False, 'active_student_promoted': False}


class ExistingForgeBridge:
    def __init__(self, *, owner_authorize: Callable, native_stop: Callable,
                 native_telemetry: Callable, native_submit: Callable,
                 resources: RequiredResources = RequiredResources()):
        if not all(callable(x) for x in (owner_authorize, native_stop, native_telemetry, native_submit)):
            raise TypeError('EXISTING_ONEHOST_FORGE_CALLBACKS_REQUIRED')
        self.auth, self.stop = owner_authorize, native_stop
        self.telemetry, self.submit, self.res = native_telemetry, native_submit, resources

    def admit(self, *, tenant, principal, chat_id, owner_approval_receipt,
              student, dataset, objective, expected_training_steps=100):
        """Submit ONLY a bounded native job. Return native queue receipt (not PASS).

        The owner_authorize callback MUST check signed approval for THIS scope,
        student SHA, dataset SHA and objective; a text boolean is not approval.
        """
        if self.stop() is not False:
            return hold('NATIVE_STOP_ACTIVE_OR_UNAVAILABLE')
        if objective not in ('association', 'student_sft', 'student_dpo', 'continued_pretraining'):
            return hold('UNAPPROVED_OBJECTIVE')
        if not isinstance(student, dict) or not isinstance(dataset, dict):
            return hold('STUDENT_DATASET_METADATA_REQUIRED')
        if not (SHA.fullmatch(str(student.get('weights_sha256',''))) and
                SHA.fullmatch(str(student.get('tokenizer_sha256',''))) and
                SHA.fullmatch(str(student.get('architecture_sha256',''))) and
                SHA.fullmatch(str(dataset.get('sha256',''))) and
                dataset.get('source_disjoint') is True and
                dataset.get('license_and_privacy_reviewed') is True):
            return hold('WEIGHTS_ABI_OR_DATA_PROVENANCE_HOLD')
        if type(expected_training_steps) is not int or not 1 <= expected_training_steps <= 50_000:
            return hold('UNBOUNDED_STEPS')
        try:
            grant = self.auth(tenant, principal, chat_id, owner_approval_receipt,
                              student['weights_sha256'], dataset['sha256'], objective)
        except Exception:
            return hold('OWNER_AUTH_CALLBACK_FAILED')
        if grant is not True:
            return hold('SIGNED_NATIVE_OWNER_GRANT_REQUIRED')
        try:
            t = self.telemetry()
        except Exception:
            return hold('LIVE_GPU_TELEMETRY_UNAVAILABLE')
        if not isinstance(t, dict) or t.get('stop_active') is not False or t.get('hotspot_sensor_valid') is not True:
            return hold('STOP_OR_HOTSPOT_SENSOR_NOT_VERIFIED')
        numeric = ('vram_free_gb', 'ram_free_gb', 'disk_free_gb', 'hotspot_c')
        if any(type(t.get(k)) not in (int, float) or not math.isfinite(t[k]) or t[k] < 0 for k in numeric):
            return hold('INVALID_GPU_OR_STORAGE_TELEMETRY')
        if t['hotspot_c'] >= self.res.safe_hotspot_c:
            return hold('HOTSPOT_AT_OR_ABOVE_70')
        if t.get('hotspot_consecutive_high', 0) >= self.res.max_consecutive_hot_readings:
            return hold('SAFE70_CONSECUTIVE_HIGH')
        if (t['vram_free_gb'] < self.res.minimum_vram_free_gb or
                t['ram_free_gb'] < self.res.minimum_ram_free_gb or
                t['disk_free_gb'] < self.res.minimum_disk_free_gb):
            return hold('RESOURCE_RESERVE_NOT_MET')
        if self.stop() is not False:
            return hold('STOP_BEFORE_NATIVE_SUBMIT')
        request = {
            'student_sha256': student['weights_sha256'],
            'tokenizer_sha256': student['tokenizer_sha256'],
            'architecture_sha256': student['architecture_sha256'],
            'dataset_sha256': dataset['sha256'],
            'objective': objective,
            'max_optimizer_steps': expected_training_steps,
            'required_host_gates': ['STOP', 'SAFE70', 'CHECKPOINT', 'ABI', 'HOLDOUT', 'ROLLBACK'],
            'override_active_nox': False,
            'recheck_owner_grant_at_execution': True,
        }
        try:
            receipt = self.submit(tenant, principal, chat_id, request)
        except Exception:
            return hold('NATIVE_FORGE_SUBMIT_FAILED')
        if not isinstance(receipt, dict) or receipt.get('state') != 'ACCEPTED_BY_EXISTING_FORGE' or not receipt.get('job_id'):
            return hold('UNVERIFIED_NATIVE_JOB_RECEIPT')
        if self.stop() is not False:
            return hold('STOP_AFTER_NATIVE_SUBMIT_RECHECK_JOB')
        return {'state': 'NATIVE_FORGE_JOB_SUBMITTED_NOT_TRAINED', 'job_id': receipt['job_id'],
                'student_weights_changed': False, 'training_started': False,
                'active_student_promoted': False,
                'requires_native_optimizer_and_checkpoint_receipt': True,
                'dataset_sha256': dataset['sha256']}
