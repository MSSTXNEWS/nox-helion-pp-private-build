#!/usr/bin/env python3
"""One reviewed retry of the unchanged step5 checkpoint with in-place LoRA restore.

The old calibration entry is immutable. This revision preserves its admission,
checkpoint, resource and actual-positive-update gates, and observes for120s so
the existing owner-action queue can continue while the trainer is running.
"""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import types

try: BUNDLE = __NOX_BUNDLE_JSON__
except NameError: BUNDLE = {}
ROOT = Path('/root/nox')
SCRIPTS = ROOT / 'scripts'
STATE = ROOT / 'state'
HYBRID = SCRIPTS / 'hybrid_training_entry.py'
CALIBRATION_SHA = '516a0ce2c0753bd3813a4d319a96d182197180e627d9bb318f00760d920991ea'
OLD_HYBRID_SHA = 'f2ba60d6556ba3662713db0e503773f2361b82b6c83391be4e56a506aad8c0af'
NEW_HYBRID_SHA = 'c576e63b4b8f63bf12b4f1453de5b8e1763d42685991af96ec765bce35264a75'
PREFLIGHT_SHA = 'adf78f15fcdd30c52e97c89ac2bf6027f96086e0f45f64b84ce803f19af13df4'
CONFIG_PREFLIGHT_SHA = '0f38d420bebd382cdf422381c0ca5028208f15b37527a306057fa9cdd1d01501'
FAILED = {'request': '6906626126', 'source_sha': 'c88d33ed8fbacaf58238921f600ec7641782b516',
          'receipt_sha256': '8981703e8b6e65a23b4556d2eac06a851561a3cc8159716d6d740c32bcf10d2c'}
FAILED_POINTER_SHA = '7f5267361133b8c128418619429c3fb5b174622df4556abb3dc62c0ea6c29c26'
OBSERVATION_SECONDS = 120
STOP_PATHS = (ROOT/'STOP', ROOT/'STOP.flag', ROOT/'stop.flag', ROOT/'.stop',
              ROOT/'program/STOP', STATE/'STOP', Path('/workspace/NOX_STOP'))


def fail(code):
    raise RuntimeError(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def placement_metadata():
    return {'schema': 'NOX_OWNER_ADAPTER_PLACEMENT_RECOVERY_V1',
            'failed_admission': dict(FAILED), 'previous_hybrid_sha256': OLD_HYBRID_SHA,
            'hybrid_sha256': NEW_HYBRID_SHA, 'restore_method': 'COPY_EXISTING_LORA_PARAMETERS',
            'base_redispatch': False, 'optimizer_reset': False, 'scaler_reset': False,
            'rng_reset': False, 'initial_observation_seconds': OBSERVATION_SECONDS}


def configure():
    raw = base64.b64decode(BUNDLE.get('owner_training_amp_calibration.py', ''), validate=True)
    if digest(raw) != CALIBRATION_SHA:
        fail('HOLD_PLACEMENT_CALIBRATION_PREIMAGE')
    source = raw.decode()
    replacements = (
        ("raw!=('OWNER_HYBRID_FAILED request='+ORIGIN['request']+'\\n').encode()",
         "raw!=('OWNER_HYBRID_FAILED request='+PLACEMENT_FAILED_REQUEST+'\\n').encode()"),
        ('for item in (WRAPPER,POINTER,hold):', "for item in (WRAPPER,POINTER,hold,SCRIPTS/'hybrid_training_entry.py'):"),
        ('wrapper=wrapper_source(helper,request);sources_unchanged(recovery,pointer)',
         'pointer=install_placement_revision(recovery,helper,pointer,event)\n            wrapper=wrapper_source(helper,request);sources_unchanged(recovery,pointer)'),
        ('identity=None;pointer=None;initial_context=observe_context',
         "result['adapter_placement_recovery']=placement_metadata()\n    identity=None;pointer=None;initial_context=observe_context"),
        ('deadline=time.monotonic()+430;previous=None', 'deadline=time.monotonic()+120;previous=None'),
    )
    for before, after in replacements:
        if source.count(before) != 1:
            fail('HOLD_PLACEMENT_CALIBRATION_ANCHOR')
        source = source.replace(before, after, 1)
    c = types.ModuleType('owner_training_placement_calibration')
    c.__file__ = str(SCRIPTS/'owner_training_placement_calibration.py')
    sys.modules[c.__name__] = c
    exec(compile(source, c.__file__, 'exec'), c.__dict__)
    c.BUNDLE = BUNDLE
    historical_metadata = c.calibration_metadata()
    validator_globals = dict(c.__dict__)
    original_validator = c.sources_unchanged
    historical_policy = c.policy_admission
    historical_pending = c.pending_evidence
    historical_checkpoint_proof = c.checkpoint_proof
    c.HYBRID_SHA = NEW_HYBRID_SHA
    c.FAILED_HOLD_SHA = digest(('OWNER_HYBRID_FAILED request='+FAILED['request']+'\n').encode())
    c.PLACEMENT_FAILED_REQUEST = FAILED['request']
    c.placement_metadata = placement_metadata
    c.PINS['owner_training_restore_preflight'] = PREFLIGHT_SHA
    c.PINS['owner_training_config_preflight'] = CONFIG_PREFLIGHT_SHA

    def sources_unchanged(recovery, pointer):
        pin = (pointer.get('sources') or {}).get(str(HYBRID))
        if pin not in (OLD_HYBRID_SHA, NEW_HYBRID_SHA):
            fail('HOLD_PLACEMENT_UNKNOWN_HYBRID_REVISION')
        values = {**validator_globals, 'HYBRID_SHA': pin}
        types.FunctionType(original_validator.__code__, values)(recovery, pointer)

    def policy(recovery, helper, resume):
        if any(path.exists() or path.is_symlink() for path in STOP_PATHS):
            fail('HOLD_PLACEMENT_OWNER_STOP')
        historical_policy(recovery, helper, resume)

    def pending_evidence(recovery, helper, context):
        old, pointer, process = historical_pending(recovery, helper, context)
        if (old.get('adapter_placement_recovery') != placement_metadata()
            or pointer.get('adapter_placement_recovery') != placement_metadata()):
            fail('HOLD_PLACEMENT_PENDING_TRANSITION_PROOF')
        return old, pointer, process

    def checkpoint_proof(recovery, helper, value, *, baseline=False):
        proof = historical_checkpoint_proof(recovery, helper, value, baseline=baseline)
        if not baseline:
            restored = value.get('checkpoint_restore') or {}
            original = recovery.read(c.OUTPUT/'owner_receipt_step_5.json')
            if digest(original) != c.BASELINE_RECEIPT_SHA:
                fail('HOLD_PLACEMENT_RESTORE_BASELINE_CHANGED')
            original = json.loads(original)
            if (restored.get('schema') != 'NOX_LORA_INPLACE_CHECKPOINT_RESTORE_V1'
                or restored.get('global_step') != 5 or restored.get('restored') is not True
                or restored.get('parameter_objects_preserved') is not True
                or restored.get('base_placement_preserved') is not True or restored.get('trainable_tensors') != 66
                or restored.get('restored_tensor_sha256') != c.BASELINE_TENSOR_SHA
                or restored.get('adapter_file_sha256') != original['checkpoint']['files_sha256']['adapter_model.safetensors']
                or restored.get('optimizer_scheduler_scaler_rng_restore') != 'DELEGATED_TO_HF_TRAINER'):
                fail('HOLD_PLACEMENT_RESTORE_NATIVE_PROOF')
            proof.update(checkpoint_restore_verified=True, restored_checkpoint_step=5)
        return proof

    def original_evidence(recovery, helper):
        failed_raw = recovery.read(STATE/('owner_maintenance_'+FAILED['request']+'.json'))
        if digest(failed_raw) != FAILED['receipt_sha256']:
            fail('HOLD_PLACEMENT_FAILED_RECEIPT')
        old = json.loads(failed_raw)
        pointer_raw = recovery.read(c.POINTER)
        pointer = json.loads(pointer_raw)
        if (digest(pointer_raw) != FAILED_POINTER_SHA or old.get('schema') != 'NOX_OWNER_TRAINING_RESUME_V1'
            or old.get('request') != FAILED['request'] or old.get('source_sha') != FAILED['source_sha']
            or old.get('state') != 'HOLD_TRAINING_AMP_CALIBRATION'
            or old.get('error') != 'HOLD_SINGLE_NATIVE_TRAINER_IDENTITY'
            or old.get('training_started') is not True or old.get('optimizer_steps_verified') is not False
            or old.get('amp_calibration') != historical_metadata or old.get('admission') != pointer):
            fail('HOLD_PLACEMENT_FAILED_ADMISSION_SCOPE')
        origin_raw = recovery.read(STATE/('owner_maintenance_'+c.ORIGIN['request']+'.json'))
        if digest(origin_raw) != c.ORIGIN['receipt_sha256']:
            fail('HOLD_PLACEMENT_ORIGINAL_ADMISSION')
        origin = json.loads(origin_raw)
        initial = origin.get('admission') or {}
        wrapper = c.wrapper_source(helper, FAILED['request'])
        expected = {**initial, 'request': FAILED['request'], 'source_sha': FAILED['source_sha'],
            'wrapper_request': FAILED['request'], 'max_steps': 20, 'resume': True,
            'amp_calibration': historical_metadata, 'sources': {**initial.get('sources', {}), str(c.WRAPPER): digest(wrapper)}}
        if pointer != expected or recovery.read(c.WRAPPER) != wrapper:
            fail('HOLD_PLACEMENT_UNREVIEWED_ADMISSION_DELTA')
        sources_unchanged(recovery, pointer)
        if pointer['sources'].get(str(HYBRID)) != OLD_HYBRID_SHA:
            fail('HOLD_PLACEMENT_ALREADY_TRANSITIONED')
        baseline_raw = recovery.read(c.OUTPUT/'owner_receipt_step_5.json')
        if digest(baseline_raw) != c.BASELINE_RECEIPT_SHA:
            fail('HOLD_PLACEMENT_BASELINE_RECEIPT')
        baseline = json.loads(baseline_raw)
        proof = c.checkpoint_proof(recovery, helper, baseline, baseline=True)
        entries = list(c.OUTPUT.iterdir())
        checkpoints = [path for path in entries if path.name.startswith('checkpoint-')]
        if (len(entries) > 100 or (c.OUTPUT/'owner_last_result.json').exists()
            or {path.name for path in checkpoints} != {'checkpoint-1', 'checkpoint-4', 'checkpoint-5'}
            or any(path.is_symlink() or not path.is_dir() for path in checkpoints)):
            fail('HOLD_PLACEMENT_NEW_OR_UNKNOWN_CHECKPOINT')
        if recovery.file_sha(c.OUTPUT/'training_text.jsonl', 305243573) != c.DATASET_SHA:
            fail('HOLD_PLACEMENT_CORPUS_CHANGED')
        return old, pointer, baseline, proof

    def install_revision(recovery, helper, pointer, event):
        sources_unchanged(recovery, pointer)
        raw = base64.b64decode(BUNDLE.get('hybrid_training_entry.py', ''), validate=True)
        if digest(raw) != NEW_HYBRID_SHA:
            fail('HOLD_PLACEMENT_HYBRID_BUNDLE_PIN')
        compile(raw, str(HYBRID), 'exec')
        lease = os.open(STATE/'forge_training.lock', os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(lease, fcntl.LOCK_EX|fcntl.LOCK_NB)
            config = c.load('owner_training_config_preflight').run_preflight(raw, recovery.read(SCRIPTS/'train_qlora_35b_t866u.py'))
            if (config.get('state') != 'INSTALLED_CONFIG_AND_SERIALIZATION_VERIFIED'
                or config.get('hybrid_sha256') != NEW_HYBRID_SHA or config.get('native_sha256') != c.NATIVE_SHA
                or config.get('model_loaded') is not False or config.get('optimizer_created') is not False):
                fail('HOLD_PLACEMENT_CONFIG_PREFLIGHT')
            event('installed_config_and_serialization_preflight', config)
            checked = c.load('owner_training_restore_preflight').run_preflight(raw)
        finally:
            os.close(lease)
        if (checked.get('state') != 'PINNED_INPLACE_RESTORE_ON_TINY_GPU_MODEL_VERIFIED'
            or checked.get('hybrid_sha256') != NEW_HYBRID_SHA
            or checked.get('optimizer_step_performed') is not False
            or checked.get('real_checkpoint_read') is not False
            or checked.get('checks', {}).get('seven_synthetic_files_unchanged') is not True):
            fail('HOLD_PLACEMENT_NATIVE_PREFLIGHT')
        event('adapter_placement_restore_preflight', checked)
        if recovery.document(c.POINTER) != pointer:
            fail('HOLD_PLACEMENT_POINTER_CHANGED')
        if any(path.exists() or path.is_symlink() for path in STOP_PATHS):
            fail('HOLD_PLACEMENT_OWNER_STOP')
        helper.atomic(HYBRID, raw)
        os.chmod(HYBRID, 0o700)
        if recovery.read(HYBRID) != raw:
            fail('HOLD_PLACEMENT_HYBRID_READBACK')
        pointer = {**pointer, 'sources': {**pointer['sources'], str(HYBRID): NEW_HYBRID_SHA},
                   'adapter_placement_recovery': placement_metadata()}
        sources_unchanged(recovery, pointer)
        event('adapter_placement_source_transition', placement_metadata())
        return pointer

    c.sources_unchanged = sources_unchanged
    c.policy_admission = policy
    c.pending_evidence = pending_evidence
    c.checkpoint_proof = checkpoint_proof
    c.original_evidence = original_evidence
    c.install_placement_revision = install_revision
    return c


def main(observe_context=None):
    return configure().main(observe_context)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        reason = str(exc)
        if not re.fullmatch('(HOLD|WAIT)_[A-Z0-9_]+', reason): reason = type(exc).__name__
        print('NOX_MAINT_REPAIR='+json.dumps({'kind': 'training_placement_recovery_hold', 'data': {'reason': reason}}), flush=True)
        raise SystemExit(2)
