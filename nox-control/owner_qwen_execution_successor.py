#!/usr/bin/env python3
"""Read-only proof of one explicit successor to the unactivated Qwen revision.

Historical installation evidence and current execution are separate namespaces.
No training import, process start, file write, flag clear, or policy rearm occurs
here. Checkpoint helpers hash metadata only; their results never assert that all
tensor payloads were read. The installer and native checkpoint loader own that
separate proof. The predecessor and both retained anchors are exact; no old checkpoint is relabeled.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import time
import types

ROOT = Path('/root/nox')
STATE = ROOT / 'state'
SCRIPTS = ROOT / 'scripts'
OUTPUT = ROOT / 'lora/qwen35_9b/6907283384'
AREA = STATE / 'owner_qwen_execution_revisions'
CONFIG = ROOT / 'config/owner_qwen_execution_revision.json'
ADMISSION = STATE / 'owner_training_admission.json'
WRAPPER = SCRIPTS / 'run_train_volta_t866u.sh'
GUARD_CONFIG = ROOT / 'config/owner_qwen_training_guard.json'
GUARD_STATUS = STATE / 'owner_qwen_training_guard.json'
ENTRY = 'qwen_student_training_entry_revision.py'
SELF = 'owner_qwen_execution_revision.py'
CONFIG_SCHEMA = 'NOX_QWEN_EXECUTION_REVISION_CONFIG_V1'
DESCRIPTOR_SCHEMA = 'NOX_QWEN_EXECUTION_SUCCESSOR_DESCRIPTOR_V1'
RECEIPT_SCHEMA = 'NOX_QWEN_EXECUTION_SUCCESSOR_ADMISSION_V1'
BINDING_SCHEMA = 'NOX_QWEN_EXECUTION_BINDING_V1'
WITNESS_SCHEMA = 'NOX_QWEN_EVALUATION_WITNESS_V1'
ACTIVATION_SCHEMA = 'NOX_QWEN_EXECUTION_ACTIVATION_V1'
SHA = re.compile('[a-f0-9]{64}')
SOURCE = re.compile('[a-f0-9]{40}')
REQUEST = re.compile('[0-9]{1,24}')
NAME = re.compile('checkpoint-u[0-9]{8}-a[0-9]{8}-g[0-9]{20}')
MIB = 1024 ** 2
OWNER_UID = 0
CONSUMERS = {'owner_qwen_training_guard.py', 'owner_training_status.py', 'owner_qwen_media_handoff.py',
             'owner_qwen_media_guard.py', 'owner_qwen_handback_retry.py', 'owner_hermes_hydrate.py',
             'nox_dispatcher_t855u.py'}
HISTORICAL = {
    'owner_qwen_install_entry.py': '864fe6b0e1567931f94d0b0be55651227ee00fd9106abc4c82e09c13601975d7',
    'owner_qwen_window_entry.py': 'fb9b9dd403f7b1e5d94b8192ce7ad63394ba8a6b3988cc298fc90a195aa191a7',
    'owner_qwen_training_observe.py': 'f2dc6c155b682bdeb663bc383f1aa1db70895f815939099690d898262a3d986a',
}
ORIGINAL_SOURCES = {
    'qwen_student_training_entry.py': '259ac097f3ceec5be217748667a421ab5c39ebb56b9b2817fd1368d278f99cb0',
    'owner_qwen_training_contract.py': '7108da4d4949887414f33f5693fe901e3eb5fc63eb97f2b98d1371fed912f50a',
    'owner_qwen_memfd.py': '938335009efe691a9cef7b41daa7c55f3c8d3d8618a10a5eb5db125fd45afa82',
    'owner_qwen_corpus.py': '1509c31789c2c39507d726515ca1c24a5de5545d8c305c7de0ddbba82058b7eb',
    'qwen35_9b_manifest.json': '2275fc88370ca8ba409a791819e13c8ab7d4e38cce4576a13170b05bcb8b839b',
}
ORIGIN_WINDOW = {'request': '6908281920', 'source_sha': '35931438c591a9bb5a649e851f155c4313f28562',
                 'receipt_sha256': 'fa0ed9dd2088a247b2ccc94ad60f9962c0d502121c12bf00e31436c9cf487662'}
ORIGIN = {
    'window': ORIGIN_WINDOW,
    'lineage_sha256': '14c92849840ed3ef982a4a443656fdc0f9183ec7967106b42ce8d0719bb25190',
    'lineage_file_sha256': '19345f9992a8a4a0537c9b9f84ffb086164e1c898eb0207c53569469645f3cb0',
    'acceptance_sha256': '2076f7050169692e0333747d07abb5c290b429c1b30d56fd55928fc215edfc00',
    'previous_admission_sha256': '9116c9ffbca959ba7afe80dbb66c36a356a922b87ecd839469d17413bb450499',
    'previous_wrapper_sha256': '5bef568fd965f17151b252d8b8d25f00c9b67dd756feef9e30c54cd5b419cd96',
    'previous_entry_sha256': ORIGINAL_SOURCES['qwen_student_training_entry.py'],
}
ORIGINAL_ANCHOR = {
    'directory': 'checkpoint-u00000025-a00000025-g01794816279192913655',
    'pointer_sha256': '1676132e4716aedec8308e71069bf53746a9363343bc767d241ded9bd80fe714',
    'manifest_sha256': 'ba101a2c7125e352cfd17319d8ff8b228b6b43ef9490c99788928c4275fc2dbf',
    'student_state_sha256': '1051539e76d29ee0f8a035fa8b6b4e60dd141e19c8ecc8fd5f4d2a872ba85258',
    'successful_total': 25, 'attempted_total': 25, 'skipped_total': 0,
    'evaluated_successful_total': 10, 'verified_files': 10, 'verified_bytes': 519902179,
}
ANCHOR = {
    'directory': 'checkpoint-u00000025-a00000025-g01794828669565488412',
    'pointer_sha256': '42978e0fc35580f744dcb97e3bbc85a8f8d0ff12bce75ed722026248363e10e2',
    'manifest_sha256': 'c206cd9e7a1bacdc5d6dae261d7d775f41bd8f8d2a4986c7464a1b60cacdbf49',
    'student_state_sha256': 'f5c1a30c1afe092a01d46c533692968efc54f38ce96dda4a956c48074ee55f7a',
    'successful_total': 25, 'attempted_total': 25, 'skipped_total': 0,
    'evaluated_successful_total': 25, 'verified_files': 10, 'verified_bytes': 519905811,
}
PREDECESSOR = {
    'reference': {'request': '6914959637', 'source_sha': 'a06c6a039ebccd6eaa754914624ab5477beca47b',
        'receipt_sha256': '2f16be7a0bf648621f845c898dd2cc078a98f608fa5b01b3153890c7e3dc41d9'},
    'descriptor_sha256': '9d3c9ce7bc612d5c9fc5db361ee36248bb50a6f1d6935702fdc80c244bc72470',
    'admission_sha256': 'c9cec88d003a4174b5d4ca5ec1d29a8dc4f7bb80038b5bd7a4dee18eea789080',
    'runtime_entry_sha256': 'ce7dcbef53c61c63ebab96553ef4c48d9f138a3c426008fa329eb5fd66ee041c',
    'verifier_sha256': '0dbb06d3384b3436165056ccf4e35bff937fda4f85d96ab2a97ab16a6619998e',
    'activation_issuer_sha256': '711912d596ce6c8e806d4ee16d9d5a1fae41c89b527825b13cf2c6788a17975a',
}
WATCHER = 'owner_qwen_successor_watch.py'
PREDECESSOR_HOLD_SHA = '536ba522ae83bfb052998a175993e94701c1cbc24d93a92f0107377858644d38'
SCHEDULER = {'interval_seconds': 300, 'maximum_update_gap': 10, 'guard_update_gap': 15}
GUARD_POLICY = {'poll_seconds': 5, 'state_max_age_seconds': 30, 'stale_successful_updates': 15,
    'regression_patience': 2, 'regression_absolute_delta': 0.01, 'regression_relative_delta': 0.01,
    'native_disk_floor_bytes': 10 * 1024 ** 3, 'disk_margin_bytes': 256 * MIB,
    'disk_urgent_margin_bytes': 64 * MIB, 'disk_debounce_seconds': 5}
OLD_HOLD_SHA = '2e104be136236c5ce7a9a6327904bc8c5c091c959085192e9b6c1c1152417ae4'
OLD_PAUSE_SHA = '013cb1ff2dfc3fd8555b51609bcf7a9abe3aa8dbb7a4cac1a229c52a8b89a94e'
INITIAL_RECEIPT_SHA = '2336a33272f75d9fc56efd74172ccf09bba5067cceb1f67b6a966812d9a70262'
REQUIRED = {'adapter_model.safetensors', 'adapter_config.json', 'optimizer.pt', 'scheduler.pt',
            'scaler.pt', 'rng_state.pt', 'python_rng.json', 'student_state.json', 'lineage.json'}
COUNTERS = {'successful_total', 'attempted_total', 'skipped_total', 'data_cursor', 'optimizer_step'}
SIGNATURE_HASHES = {'adapter_tensor_sha256', 'optimizer_state_sha256', 'scheduler_state_sha256',
                    'scaler_state_sha256', 'rng_state_sha256'}


class Hold(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise Hold('HOLD_QWEN_REVISION_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode()


def sha(value):
    return isinstance(value, str) and bool(SHA.fullmatch(value))


def integer(value):
    return type(value) is int and 0 <= value <= 10 ** 12


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def identity(value):
    return tuple(getattr(value, name) for name in (
        'st_dev', 'st_ino', 'st_size', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_mtime_ns', 'st_ctime_ns'))


def plain(path):
    path = Path(path)
    require(path.is_absolute() and not any(p.is_symlink() for p in (*path.parents, path)), 'PATH')
    return path


def read(path, maximum=2 * MIB, *, expected=None, private=False):
    path = plain(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= maximum, 'FILE_BOUND')
        if private:
            require(before.st_uid == OWNER_UID and stat.S_IMODE(before.st_mode) == 0o600 and before.st_nlink == 1, 'PRIVATE_FILE')
        raw = stream.read(maximum + 1)
        require(len(raw) == before.st_size and identity(before) == identity(os.fstat(stream.fileno()))
                == identity(path.stat(follow_symlinks=False)), 'FILE_CHANGED')
    require(expected is None or sha(expected) and digest(raw) == expected, 'FILE_SHA')
    return raw


def strict_pairs(rows):
    value = {}
    for key, item in rows:
        require(key not in value, 'DUPLICATE_JSON_KEY')
        value[key] = item
    return value


def parse(raw):
    def finite_float(value):
        number = float(value)
        require(math.isfinite(number), 'NONFINITE_JSON')
        return number
    value = json.loads(raw, object_pairs_hook=strict_pairs,
                       parse_constant=lambda _: require(False, 'NONFINITE_JSON'), parse_float=finite_float)
    require(isinstance(value, dict), 'JSON_OBJECT')
    return value


def document(path, maximum=2 * MIB, **kwargs):
    raw = read(path, maximum, **kwargs)
    return parse(raw), raw


def validate_reference(value):
    require(isinstance(value, dict) and set(value) == {'request', 'source_sha', 'receipt_sha256'}
            and isinstance(value['request'], str) and REQUEST.fullmatch(value['request'])
            and isinstance(value['source_sha'], str) and SOURCE.fullmatch(value['source_sha'])
            and sha(value['receipt_sha256']), 'REFERENCE')
    return dict(value)


def descriptor(value):
    require(isinstance(value, dict) and set(value) == {'schema', 'request', 'source_sha', 'created_at', 'origin',
        'runtime_sources', 'consumer_sources', 'activation_issuer_sha256', 'anchor', 'scheduler', 'bootstrap',
        'predecessor', 'retained_anchors', 'activation_watcher_sha256'}, 'DESCRIPTOR_FIELDS')
    require(value['schema'] == DESCRIPTOR_SCHEMA and isinstance(value['request'], str)
            and REQUEST.fullmatch(value['request']) and value['request'] != PREDECESSOR['reference']['request']
            and isinstance(value['source_sha'], str) and SOURCE.fullmatch(value['source_sha'])
            and finite(value['created_at']) and value['created_at'] > 0, 'DESCRIPTOR_IDENTITY')
    require(value['origin'] == ORIGIN and value['anchor'] == ANCHOR and value['scheduler'] == SCHEDULER
            and value['predecessor'] == PREDECESSOR
            and value['retained_anchors'] == [ORIGINAL_ANCHOR, ANCHOR], 'IMMUTABLE_ORIGIN_ANCHOR_POLICY')
    require(isinstance(value['runtime_sources'], dict) and set(value['runtime_sources']) == {ENTRY, SELF}
            and all(sha(pin) for pin in value['runtime_sources'].values()), 'RUNTIME_SOURCES')
    require(isinstance(value['consumer_sources'], dict) and set(value['consumer_sources']) == CONSUMERS
            and all(sha(pin) for pin in value['consumer_sources'].values())
            and sha(value['activation_issuer_sha256']) and sha(value['activation_watcher_sha256']), 'CONSUMER_SOURCES')
    b = value['bootstrap']
    require(isinstance(b, dict) and set(b) == {'expires_at', 'hold_sha256', 'pause_sha256'}
            and finite(b['expires_at']) and value['created_at'] < b['expires_at'] <= value['created_at'] + 3600
            and b['hold_sha256'] == PREDECESSOR_HOLD_SHA and b['pause_sha256'] is None, 'BOOTSTRAP_SCOPE')
    return copy.deepcopy(value)


def predecessor_binding():
    return {'schema': BINDING_SCHEMA, 'execution_revision': copy.deepcopy(PREDECESSOR['reference']),
        'descriptor_sha256': PREDECESSOR['descriptor_sha256'], 'admission_sha256': PREDECESSOR['admission_sha256'],
        'runtime_entry_sha256': PREDECESSOR['runtime_entry_sha256'], 'verifier_sha256': PREDECESSOR['verifier_sha256'],
        'origin_lineage_sha256': ORIGIN['lineage_sha256']}


def retained_anchors(ctx):
    desc = descriptor(ctx['execution']['descriptor'])
    return copy.deepcopy(desc['retained_anchors'])


def make_admission(previous, desc, descriptor_sha256, created_at):
    desc = descriptor(desc)
    require(sha(descriptor_sha256) and finite(created_at) and created_at >= desc['created_at'], 'NEW_ADMISSION_TIME')
    ref = PREDECESSOR['reference']
    require(previous.get('request') == ref['request'] and previous.get('source_sha') == ref['source_sha']
            and previous.get('student_profile', {}).get('successful_updates_goal') == 1000
            and previous.get('execution_revision') == {'schema': 'NOX_QWEN_EXECUTION_REFERENCE_V1',
                'request': ref['request'], 'source_sha': ref['source_sha'],
                'descriptor_sha256': PREDECESSOR['descriptor_sha256']}, 'PREVIOUS_ADMISSION')
    value = copy.deepcopy(previous)
    value.update(request=desc['request'], source_sha=desc['source_sha'], created_at=created_at,
                 previous_request=previous['request'], previous_admission_sha256=PREDECESSOR['admission_sha256'],
                 predecessor_execution_revision=copy.deepcopy(ref))
    value['sources'] = dict(previous['sources'])
    value['sources'].update({str(SCRIPTS / name): pin for name, pin in desc['runtime_sources'].items()})
    value['execution_revision'] = {'schema': 'NOX_QWEN_EXECUTION_REFERENCE_V1', 'request': desc['request'],
        'source_sha': desc['source_sha'], 'descriptor_sha256': descriptor_sha256}
    return value


def predecessor_evidence(folder, origin):
    """Read immutable predecessor evidence, never an old view of live sources."""
    ref = PREDECESSOR['reference']; old_folder = plain(AREA / ref['request'])
    old, _ = document(old_folder / 'admission_receipt.json', expected=ref['receipt_sha256'], private=True)
    old_desc, _ = document(old_folder / 'descriptor.json', expected=PREDECESSOR['descriptor_sha256'], private=True)
    require(old_desc.get('schema') == 'NOX_QWEN_EXECUTION_REVISION_DESCRIPTOR_V1'
            and old_desc.get('request') == ref['request'] and old_desc.get('source_sha') == ref['source_sha']
            and old_desc.get('origin') == ORIGIN and old_desc.get('anchor') == ORIGINAL_ANCHOR
            and old_desc.get('scheduler') == SCHEDULER
            and old_desc.get('runtime_sources') == {ENTRY: PREDECESSOR['runtime_entry_sha256'], SELF: PREDECESSOR['verifier_sha256']}
            and old_desc.get('activation_issuer_sha256') == PREDECESSOR['activation_issuer_sha256'], 'PREDECESSOR_DESCRIPTOR')
    require(old.get('schema') == 'NOX_QWEN_EXECUTION_REVISION_ADMISSION_V1'
            and old.get('state') == 'EXECUTION_REVISION_INSTALLED_EVALUATION_REQUIRED'
            and old.get('request') == ref['request'] and old.get('source_sha') == ref['source_sha']
            and old.get('descriptor_sha256') == PREDECESSOR['descriptor_sha256']
            and old.get('previous_admission_sha256') == ORIGIN['previous_admission_sha256']
            and old.get('new_admission_sha256') == PREDECESSOR['admission_sha256']
            and old.get('origin_window') == ORIGIN_WINDOW and old.get('origin_lineage_sha256') == ORIGIN['lineage_sha256']
            and old.get('anchor_checkpoint_manifest_sha256') == ORIGINAL_ANCHOR['manifest_sha256']
            and old.get('runtime_sources') == old_desc['runtime_sources'] and sha(old.get('wrapper_sha256')), 'PREDECESSOR_RECEIPT')
    previous, raw = document(folder / 'predecessor_admission.json', 64000,
                             expected=PREDECESSOR['admission_sha256'], private=True)
    old_expected = copy.deepcopy(origin['admission'])
    old_expected.update(request=ref['request'], source_sha=ref['source_sha'], created_at=previous.get('created_at'),
                        previous_request=ORIGIN_WINDOW['request'], previous_admission_sha256=ORIGIN['previous_admission_sha256'])
    old_expected['sources'] = dict(origin['admission']['sources'])
    old_expected['sources'].update({str(SCRIPTS / name): pin for name, pin in old_desc['runtime_sources'].items()})
    old_expected['execution_revision'] = {'schema': 'NOX_QWEN_EXECUTION_REFERENCE_V1', 'request': ref['request'],
        'source_sha': ref['source_sha'], 'descriptor_sha256': PREDECESSOR['descriptor_sha256']}
    require(previous == old_expected and finite(previous.get('created_at'))
            and previous['created_at'] >= old_desc['created_at'], 'PREDECESSOR_ADMISSION')
    wrapper = read(folder / 'predecessor_wrapper.sh', expected=old['wrapper_sha256'], private=True)
    require(wrapper == make_wrapper(previous, digest(raw)), 'PREDECESSOR_WRAPPER')
    permit = old_folder / 'activation.json'
    require(not permit.exists() and not permit.is_symlink(), 'PREDECESSOR_ALREADY_ACTIVATED')
    return {'reference': copy.deepcopy(ref), 'descriptor': old_desc, 'receipt': old,
            'admission': previous, 'raw': raw, 'wrapper': wrapper, 'execution_binding': predecessor_binding()}


def make_argv(admission, admission_sha256):
    require(sha(admission_sha256), 'ARGV_ADMISSION_SHA')
    p = admission['student_profile']; corpus = STATE / 'qwen_corpus/6907283384'
    require(p['successful_updates_goal'] == 1000, 'ARGV_GOAL')
    return ['/root/venv_volta/bin/python', '-u', str(SCRIPTS / ENTRY), '--request', admission['request'],
        '--admission-sha256', admission_sha256, '--base-directory', p['base_directory'], '--base-transport', 'sealed-memfd',
        '--manifest', str(SCRIPTS / 'qwen35_9b_manifest.json'), '--output-directory', p['output_directory'],
        '--train-jsonl', str(corpus / 'train.jsonl'), '--train-sha256', p['train_sha256'],
        '--holdout-jsonl', str(corpus / 'holdout.jsonl'), '--holdout-sha256', p['holdout_sha256'],
        '--dataset-manifest', str(corpus / 'corpus_manifest.json'), '--dataset-manifest-sha256', p['dataset_manifest_sha256'],
        '--successful-updates', '1000', '--resume']


def module(name, pin):
    path = SCRIPTS / name; raw = read(path, expected=pin)
    value = types.ModuleType('_nox_execution_' + name.removesuffix('.py'))
    value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value, raw


def make_wrapper(admission, admission_sha256):
    helper, _ = module('owner_qwen_install_entry.py', HISTORICAL['owner_qwen_install_entry.py'])
    raw = helper.wrapper(make_argv(admission, admission_sha256), admission['request'])
    require(raw.count(br' goal=5\n') == 1, 'WRAPPER_TEMPLATE')
    return raw.replace(br' goal=5\n', br' goal=1000\n', 1)


def historical_context(folder):
    """Only these three canonical reads may use pinned private preimages."""
    preimages = {
        ADMISSION: read(folder / 'previous_admission.json', 64000, expected=ORIGIN['previous_admission_sha256'], private=True),
        WRAPPER: read(folder / 'previous_wrapper.sh', expected=ORIGIN['previous_wrapper_sha256'], private=True),
        SCRIPTS / 'qwen_student_training_entry.py': read(folder / 'previous_entry.py',
            expected=ORIGIN['previous_entry_sha256'], private=True),
    }
    helper, _ = module('owner_qwen_install_entry.py', HISTORICAL['owner_qwen_install_entry.py'])
    window, _ = module('owner_qwen_window_entry.py', HISTORICAL['owner_qwen_window_entry.py'])
    observer, observer_raw = module('owner_qwen_training_observe.py', HISTORICAL['owner_qwen_training_observe.py'])
    def historical_read(path, maximum=2 * MIB):
        path = Path(path)
        raw = preimages[path] if path in preimages else read(path, maximum)
        require(len(raw) <= maximum, 'HISTORICAL_READ_BOUND')
        return raw
    helper.read = historical_read
    original_contract = window.source_contract
    def bounded_source_contract(h):
        contract = original_contract(h)
        corpus = STATE / 'qwen_corpus/6907283384'
        allowed = {corpus / name for name in ('train.jsonl', 'holdout.jsonl', 'corpus_manifest.json')}
        def corpus_sha(path, chunk=MIB):
            require(Path(path) in allowed, 'HISTORICAL_CORPUS_SCOPE')
            return digest(read(path, 32 * MIB))
        contract.sha256_file = corpus_sha
        return contract
    window.source_contract = bounded_source_contract
    document(STATE / 'owner_qwen_install_6907283384.json', expected=INITIAL_RECEIPT_SHA)
    ctx = window.context(helper)
    require(ctx['admission']['request'] == ORIGIN_WINDOW['request']
            and ctx['profile']['successful_updates_goal'] == 1000, 'HISTORICAL_WINDOW')
    sealed, _ = document(STATE / ('owner_qwen_window_' + ORIGIN_WINDOW['request'] + '.json'),
                         expected=ORIGIN_WINDOW['receipt_sha256'])
    accepted = sealed.get('acceptance') or {}
    require(accepted.get('acceptance_sha256') == ORIGIN['acceptance_sha256']
            and accepted.get('terminal_receipt_sha256') == ORIGIN['acceptance_sha256']
            and accepted.get('lineage_sha256') == ORIGIN['lineage_sha256'], 'HISTORICAL_ACCEPTANCE')
    lineage, _ = document(OUTPUT / 'owner_lineage.json', expected=ORIGIN['lineage_file_sha256'])
    certificate, _ = document(OUTPUT / 'owner_acceptance.json', expected=ORIGIN['acceptance_sha256'])
    observer.lineage_proof(lineage, ctx['contract'], ctx['profile'])
    require(ctx['contract'].canonical_sha(lineage) == ORIGIN['lineage_sha256'], 'ORIGIN_LINEAGE')
    ctx['contract'].verify_proof(certificate, lineage=lineage, minimum_updates=6)
    require(certificate.get('successful_optimizer_steps') == 6, 'ACCEPTED_SIX')
    # This reviewed current-process scanner uses the new script basename. It
    # does not relabel old module bytes as a newly installed observer source.
    import ast
    tree = ast.parse(observer_raw)
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'trainers')
    scanner = ast.get_source_segment(observer_raw.decode(), node)
    old = "script = str(SCRIPTS / 'qwen_student_training_entry.py').encode()"
    require(scanner.count(old) == 1, 'CURRENT_SCANNER_TEMPLATE')
    scanner = scanner.replace(old, "script = str(SCRIPTS / '" + ENTRY + "').encode()", 1)
    exec(compile(scanner, '<reviewed-current-qwen-process-scanner>', 'exec'), observer.__dict__)
    ctx.update(lineage=lineage, certificate=certificate, observer=observer,
               helper=helper, window=window, historical_source_view=True)
    return ctx


def current_context(reference=None):
    config, config_raw = document(CONFIG, 32768, private=True)
    require(set(config) == {'schema', 'enabled', 'source_sha256', 'execution_revision'}
            and config['schema'] == CONFIG_SCHEMA and config['enabled'] is True and sha(config['source_sha256']), 'CONFIG')
    ref = validate_reference(config['execution_revision'])
    require(reference is None or validate_reference(reference) == ref, 'CONFIG_REFERENCE')
    read(SCRIPTS / SELF, expected=config['source_sha256'])
    folder = plain(AREA / ref['request'])
    receipt, receipt_raw = document(folder / 'admission_receipt.json', expected=ref['receipt_sha256'], private=True)
    require(receipt.get('schema') == RECEIPT_SCHEMA
            and receipt.get('state') == 'EXECUTION_REVISION_INSTALLED_EVALUATION_REQUIRED'
            and receipt.get('request') == ref['request'] and receipt.get('source_sha') == ref['source_sha'], 'SEALED_RECEIPT')
    desc, desc_raw = document(folder / 'descriptor.json', expected=receipt.get('descriptor_sha256'), private=True)
    desc = descriptor(desc); desc_sha = digest(desc_raw)
    require(desc['request'] == ref['request'] and desc['source_sha'] == ref['source_sha']
            and desc['runtime_sources'][SELF] == config['source_sha256'], 'DESCRIPTOR_REFERENCE')
    origin = historical_context(folder)
    predecessor = predecessor_evidence(folder, origin)
    require(desc['created_at'] > predecessor['descriptor']['created_at'], 'SUCCESSOR_TIME')
    pointer, raw = document(ADMISSION, 64000, private=True)
    require(pointer == make_admission(predecessor['admission'], desc, desc_sha, pointer.get('created_at')), 'CURRENT_ADMISSION')
    wrapper = read(WRAPPER)
    require(wrapper == make_wrapper(pointer, digest(raw)), 'CURRENT_WRAPPER')
    for name, pin in {**ORIGINAL_SOURCES, **desc['runtime_sources'], **desc['consumer_sources']}.items():
        read(SCRIPTS / name, expected=pin)
    read(SCRIPTS / 'owner_qwen_revision_install.py', expected=desc['activation_issuer_sha256'])
    read(SCRIPTS / WATCHER, expected=desc['activation_watcher_sha256'])
    require(receipt.get('previous_admission_sha256') == PREDECESSOR['admission_sha256']
            and receipt.get('predecessor_execution_revision') == PREDECESSOR['reference']
            and receipt.get('predecessor_descriptor_sha256') == PREDECESSOR['descriptor_sha256']
            and receipt.get('new_admission_sha256') == digest(raw) and receipt.get('wrapper_sha256') == digest(wrapper)
            and receipt.get('origin_window') == ORIGIN_WINDOW
            and receipt.get('origin_lineage_sha256') == ORIGIN['lineage_sha256']
            and receipt.get('anchor_checkpoint_manifest_sha256') == ANCHOR['manifest_sha256']
            and receipt.get('activation_watcher_sha256') == desc['activation_watcher_sha256']
            and receipt.get('runtime_sources') == desc['runtime_sources'], 'RECEIPT_BINDINGS')
    execution = {'reference': ref, 'descriptor': desc, 'descriptor_sha256': desc_sha,
        'admission_sha256': digest(raw), 'wrapper_sha256': digest(wrapper),
        'runtime_entry_sha256': desc['runtime_sources'][ENTRY], 'verifier_sha256': desc['runtime_sources'][SELF],
        'receipt': receipt, 'receipt_sha256': digest(receipt_raw), 'directory': folder}
    result = {'origin': {'lineage': origin['lineage'], 'certificate': origin['certificate'],
        'window_reference': dict(ORIGIN_WINDOW), 'historical_admission': origin['admission'],
        'historical_raw': origin['raw'], 'historical_wrapper': origin['wrapper']}, 'execution': execution,
        'predecessor': predecessor, 'retained_anchors': copy.deepcopy(desc['retained_anchors']),
        'admission': pointer, 'raw': raw, 'wrapper': wrapper, 'profile': pointer['student_profile'],
        'output': OUTPUT, 'argv': make_argv(pointer, digest(raw)), 'context': ref,
        'contract': origin['contract'], 'observer': origin['observer'], 'lineage': origin['lineage'],
        'certificate': origin['certificate'], 'helper': origin['helper'], 'window': origin['window'],
        'lineage_sha256': ORIGIN['lineage_sha256'], 'admission_sha256': digest(raw),
        'wrapper_sha256': digest(wrapper), 'config_sha256': digest(config_raw)}
    require(read(CONFIG, 32768) == config_raw and read(ADMISSION, 64000) == raw and read(WRAPPER) == wrapper,
            'CURRENT_CONTEXT_CHANGED')
    return result


def resolve_origin_lineage(recomputed, ctx):
    origin = ctx['lineage']
    current = copy.deepcopy(recomputed)
    require(current.get('entry_sha256') == ctx['execution']['runtime_entry_sha256']
            and current.get('contract_sha256') == ORIGINAL_SOURCES['owner_qwen_training_contract.py']
            and current.get('memfd_source_sha256') == ORIGINAL_SOURCES['owner_qwen_memfd.py'], 'RECOMPUTED_RUNTIME_SOURCE')
    current['entry_sha256'] = ORIGIN['previous_entry_sha256']
    require(current == origin, 'RECOMPUTED_SCIENTIFIC_PROFILE')
    return copy.deepcopy(origin)


def execution_binding(ctx):
    e = ctx['execution']
    return {'schema': BINDING_SCHEMA, 'execution_revision': dict(e['reference']),
        'descriptor_sha256': e['descriptor_sha256'], 'admission_sha256': e['admission_sha256'],
        'runtime_entry_sha256': e['runtime_entry_sha256'], 'verifier_sha256': e['verifier_sha256'],
        'origin_lineage_sha256': ORIGIN['lineage_sha256']}


def process_identity_valid(value):
    return (isinstance(value, dict) and set(value) == {'pid', 'start_ticks', 'boot_id'}
            and integer(value['pid']) and value['pid'] > 1 and integer(value['start_ticks']) and value['start_ticks'] > 0
            and isinstance(value['boot_id'], str) and bool(re.fullmatch('[a-f0-9-]{36}', value['boot_id'])))


def _evaluation_witness_for_binding(ctx, witness, expected_binding):
    require(isinstance(witness, dict) and set(witness) == {'schema', 'execution_binding', 'kind', 'process_identity',
        'evaluated_successful_total', 'started_at', 'finished_at', 'holdout_examples', 'holdout_loss',
        'restored_checkpoint', 'before', 'after'}, 'EVALUATION_WITNESS_FIELDS')
    require(witness['schema'] == WITNESS_SCHEMA and witness['execution_binding'] == expected_binding
            and witness['kind'] in {'BOOTSTRAP_RESTORE', 'RESUME_RESTORE', 'PERIODIC', 'GOAL'}
            and process_identity_valid(witness['process_identity']), 'EVALUATION_WITNESS_BINDING')
    require(finite(witness['started_at']) and finite(witness['finished_at'])
            and 0 < witness['started_at'] <= witness['finished_at'] <= time.time() + 5
            and finite(witness['holdout_loss']) and witness['holdout_loss'] >= 0, 'EVALUATION_TIME_OR_LOSS')
    splits = ctx['lineage']['tokenized_corpus']['splits']
    holdout = [row for row in splits if row.get('split') == 'holdout']
    require(len(holdout) == 1 and witness['holdout_examples'] == holdout[0]['accepted_rows'], 'EVALUATION_CORPUS')
    before, after = witness['before'], witness['after']
    require(isinstance(before, dict) and set(before) == COUNTERS | SIGNATURE_HASHES and after == before
            and all(integer(before[key]) for key in COUNTERS)
            and all(sha(before[key]) for key in SIGNATURE_HASHES)
            and before['optimizer_step'] == before['successful_total'] == witness['evaluated_successful_total']
            and before['attempted_total'] == before['successful_total'] + before['skipped_total'], 'EVALUATION_CHANGED_TRAINING_STATE')
    restored = witness['restored_checkpoint']
    require(isinstance(restored, dict) and set(restored) == {'directory', 'manifest_sha256', 'student_state_sha256', 'successful_total'}
            and isinstance(restored['directory'], str) and NAME.fullmatch(restored['directory'])
            and sha(restored['manifest_sha256']) and sha(restored['student_state_sha256'])
            and integer(restored['successful_total']) and 25 <= restored['successful_total'] <= before['successful_total'] <= 1000,
            'EVALUATION_RESTORE_REFERENCE')
    return copy.deepcopy(witness)


def evaluation_witness(ctx, witness):
    return _evaluation_witness_for_binding(ctx, witness, execution_binding(ctx))


def checkpoint_binding(ctx, manifest, state, allow_initial_anchor=False):
    require(isinstance(manifest, dict) and isinstance(state, dict)
            and manifest.get('schema') == 'NOX_QWEN35_9B_CHECKPOINT_V1'
            and manifest.get('lineage_sha256') == ORIGIN['lineage_sha256']
            and isinstance(manifest.get('directory'), str) and NAME.fullmatch(manifest['directory']), 'CHECKPOINT_SCOPE')
    path = OUTPUT / manifest['directory']
    actual, raw = document(path / 'checkpoint_manifest.json', 65536)
    require(actual == manifest, 'CHECKPOINT_MANIFEST_OBJECT')
    files = manifest.get('files_sha256')
    require(isinstance(files, dict) and len(files) == 10 and REQUIRED <= set(files)
            and all(isinstance(name, str) and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', name)
                    and sha(pin) for name, pin in files.items()), 'CHECKPOINT_FILES')
    actual_state, state_raw = document(path / 'student_state.json', expected=files['student_state.json'])
    require(actual_state == state, 'CHECKPOINT_STATE_OBJECT')
    saved_lineage, _ = document(path / 'lineage.json', expected=files['lineage.json'])
    require(saved_lineage == ctx['lineage'], 'CHECKPOINT_ORIGIN_LINEAGE')
    proof = ctx['observer'].update_chain(state, ctx['contract'])
    require(state['update_evidence'][:6] == ctx['certificate']['update_evidence']
            and manifest.get('successful_total') == state['successful_total']
            and manifest.get('attempted_total') == state['attempted_total']
            and manifest.get('holdout_evaluated_successful_total') == state['holdout_evaluated_successful_total']
            and manifest.get('holdout_loss') == state['last_holdout_loss']
            and manifest.get('adapter_tensor_sha256') == proof['adapter_tensor_sha256'], 'CHECKPOINT_COUNTER_CHAIN')
    initial = (allow_initial_anchor is True and manifest['directory'] == ANCHOR['directory']
               and digest(raw) == ANCHOR['manifest_sha256'] and digest(state_raw) == ANCHOR['student_state_sha256'])
    if initial:
        binding = predecessor_binding()
        require(manifest.get('execution_binding') == binding and state.get('execution_binding') == binding,
                'PREDECESSOR_CHECKPOINT_BINDING')
        witness = _evaluation_witness_for_binding(ctx, state.get('last_evaluation_witness'), binding)
        require((state['successful_total'], state['attempted_total'], state['skipped_total'],
                 state['holdout_evaluated_successful_total']) == (25, 25, 0, 25)
                and witness['kind'] == 'BOOTSTRAP_RESTORE'
                and witness['restored_checkpoint'] == {key: ORIGINAL_ANCHOR[key] for key in
                    ('directory', 'manifest_sha256', 'student_state_sha256', 'successful_total')}
                and manifest.get('process_identity') == witness['process_identity']
                and ctx['execution']['descriptor']['created_at'] > witness['finished_at'], 'PREDECESSOR_EVALUATION_ANCHOR')
    else:
        binding = execution_binding(ctx)
        require(manifest.get('execution_binding') == binding and state.get('execution_binding') == binding,
                'CHECKPOINT_EXECUTION_BINDING')
        witness = evaluation_witness(ctx, state.get('last_evaluation_witness'))
    require(witness['evaluated_successful_total'] == state['holdout_evaluated_successful_total']
            and witness['holdout_loss'] == state['last_holdout_loss']
            and witness['evaluated_successful_total'] <= state['successful_total'], 'CHECKPOINT_EVALUATION_BINDING')
    evaluated = witness['evaluated_successful_total']; before = witness['before']
    require(evaluated >= 25 and before['adapter_tensor_sha256']
            == state['update_evidence'][evaluated - 1]['adapter_sha_after']
            and all(before[key] <= state[key] for key in ('attempted_total', 'skipped_total', 'data_cursor'))
            and (evaluated != state['successful_total'] or before['data_cursor'] == state['data_cursor']),
            'EVALUATION_TENSOR_OR_COUNTER_CHAIN')
    return {'verified': True, 'scope': 'HASH_BOUND_CHECKPOINT_METADATA_NOT_FULL_TENSOR_READ',
        'legacy_anchor': False, 'initial_anchor': initial, 'current_execution': not initial,
        'anchor_kind': 'PREDECESSOR_EVALUATION' if initial else None,
        'predecessor_reference': copy.deepcopy(PREDECESSOR['reference']) if initial else None,
        'manifest_sha256': digest(raw), 'student_state_sha256': digest(state_raw),
        'successful_total': state['successful_total'], 'evaluated_successful_total': state['holdout_evaluated_successful_total'],
        'witness': witness, 'full_tensor_files_verified': False}


def bootstrap_evaluation_proof(ctx, manifest, state):
    value = checkpoint_binding(ctx, manifest, state)
    w = value['witness']; restored = w['restored_checkpoint']
    anchor = descriptor(ctx['execution']['descriptor'])['anchor']
    require(w['kind'] == 'BOOTSTRAP_RESTORE' and w['evaluated_successful_total'] == state['successful_total'] == 25
            and state['attempted_total'] == 25 and state['skipped_total'] == 0
            and restored == {key: anchor[key] for key in ('directory', 'manifest_sha256', 'student_state_sha256', 'successful_total')}
            and manifest.get('process_identity') == w['process_identity']
            and w['started_at'] >= ctx['execution']['descriptor']['created_at'], 'BOOTSTRAP_SAME_COUNTER_PROOF')
    old_manifest, old_state = anchor_metadata(ctx)
    exclusions = {'execution_binding', 'last_evaluation_witness', 'last_holdout_loss', 'holdout_evaluated_successful_total'}
    require({key: value for key, value in state.items() if key not in exclusions}
            == {key: value for key, value in old_state.items() if key not in exclusions}
            and manifest['adapter_tensor_sha256'] == old_manifest['adapter_tensor_sha256']
            == w['before']['adapter_tensor_sha256']
            and w['before']['data_cursor'] == old_state['data_cursor']
            and w['before'] == old_state['last_evaluation_witness']['after']
            and w['process_identity'] != old_manifest.get('process_identity'), 'BOOTSTRAP_CHANGED_CHECKPOINT_STATE')
    value.update(scope='HASH_BOUND_EVALUATION_METADATA_NOT_FULL_TENSOR_READ', optimizer_updates_during_bootstrap=0)
    return value


def anchor_metadata(ctx):
    """Exact predecessor CP25 metadata; no relabeling or tensor payload proof."""
    anchor = descriptor(ctx['execution']['descriptor'])['anchor']
    path = OUTPUT / anchor['directory']
    manifest, _ = document(path / 'checkpoint_manifest.json', 65536, expected=anchor['manifest_sha256'])
    state, _ = document(path / 'student_state.json', expected=anchor['student_state_sha256'])
    checkpoint_binding(ctx, manifest, state, allow_initial_anchor=True)
    return manifest, state


def activation_status(ctx):
    path = ctx['execution']['directory'] / 'activation.json'
    desc = descriptor(ctx['execution']['descriptor'])
    deadline = desc['bootstrap']['expires_at']
    anchor = desc['anchor']
    if not path.exists() and not path.is_symlink():
        return {'active': False, 'bootstrap_pending': time.time() <= deadline, 'deadline': deadline,
            'permit_sha256': None, 'initial_process_identity': None, 'baseline_successful_total': 25,
            'reason': 'WAIT_QWEN_REVISION_EVALUATION' if time.time() <= deadline else 'HOLD_QWEN_REVISION_BOOTSTRAP_EXPIRED'}
    value, raw = document(path, 131072, private=True)
    require(set(value) == {'schema', 'state', 'execution_binding', 'issuer_source_sha256', 'issued_at',
        'initial_process_identity', 'checkpoint', 'evaluation_witness', 'preserved_guard_policy_sha256',
        'guard_state_sha256', 'previous_flags_archived'}, 'ACTIVATION_FIELDS')
    require(value['schema'] == ACTIVATION_SCHEMA and value['state'] == 'FRESH_EVALUATION_ACCEPTED_OPTIMIZER_ADMITTED'
            and value['execution_binding'] == execution_binding(ctx)
            and value['issuer_source_sha256'] == ctx['execution']['descriptor']['activation_issuer_sha256']
            and value['previous_flags_archived'] is True and sha(value['preserved_guard_policy_sha256'])
            and sha(value['guard_state_sha256']) and finite(value['issued_at'])
            and ctx['execution']['descriptor']['created_at'] <= value['issued_at'] <= deadline, 'ACTIVATION_BINDING')
    witness = evaluation_witness(ctx, value['evaluation_witness'])
    require(witness['kind'] == 'BOOTSTRAP_RESTORE' and witness['evaluated_successful_total'] == 25
            and witness['before']['attempted_total'] == 25 and witness['before']['skipped_total'] == 0
            and witness['restored_checkpoint'] == {key: anchor[key] for key in ('directory', 'manifest_sha256', 'student_state_sha256', 'successful_total')}
            and witness['process_identity'] == value['initial_process_identity']
            and desc['created_at'] <= witness['started_at'] <= witness['finished_at'] <= value['issued_at'], 'ACTIVATION_EVALUATION')
    cp = value['checkpoint']
    require(isinstance(cp, dict) and set(cp) == {'directory', 'manifest_sha256', 'student_state_sha256',
        'verified_files', 'verified_bytes', 'full_files_sha256_verified'} and isinstance(cp['directory'], str)
        and NAME.fullmatch(cp['directory']) and sha(cp['manifest_sha256']) and sha(cp['student_state_sha256'])
        and cp['verified_files'] == 10 and integer(cp['verified_bytes']) and 0 < cp['verified_bytes'] <= 2 * 1024 ** 3
        and cp['full_files_sha256_verified'] is True, 'ACTIVATION_CHECKPOINT')
    # The immutable acceptance preserves this proof even if normal retention
    # later prunes its payload. It is not a claim of a fresh full file read.
    return {'active': True, 'bootstrap_pending': False, 'deadline': deadline, 'permit_sha256': digest(raw),
        'initial_process_identity': value['initial_process_identity'], 'baseline_successful_total': 25,
        'reason': None, 'permit': value}


def _self_process_identity():
    raw = Path('/proc/self/stat').read_bytes(); parts = raw[raw.rindex(b')') + 2:].split()
    return {'pid': os.getpid(), 'start_ticks': int(parts[19]),
            'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip()}


def stop_active():
    return any(p.exists() or p.is_symlink() for p in (
        ROOT / 'STOP', ROOT / 'STOP.flag', ROOT / 'stop.flag', ROOT / '.stop', ROOT / 'program/STOP', STATE / 'STOP',
        STATE / 'TRAIN_HOLD.flag', STATE / 'TRAIN_PAUSE_REQUEST.flag', Path('/workspace/NOX_STOP')))


def _guard_permission(ctx, manifest_sha256):
    desc = ctx['execution']['descriptor']
    read(SCRIPTS / 'owner_qwen_training_guard.py', expected=desc['consumer_sources']['owner_qwen_training_guard.py'])
    config, config_raw = document(GUARD_CONFIG, 32768, private=True)
    require(config.get('execution_revision') == ctx['execution']['reference'], 'GUARD_EXECUTION_REFERENCE')
    row, raw = document(GUARD_STATUS, 65536, private=True)
    bindings = row.get('bindings') or {}; p = row.get('policy_state') or {}; checkpoint = row.get('checkpoint') or {}
    require(bindings.get('source_sha256') == desc['consumer_sources']['owner_qwen_training_guard.py']
            and bindings.get('config_sha256') == digest(config_raw)
            and bindings.get('execution_revision') == ctx['execution']['reference']
            and bindings.get('admission_sha256') == ctx['execution']['admission_sha256']
            and bindings.get('wrapper_sha256') == ctx['execution']['wrapper_sha256']
            and bindings.get('lineage_sha256') == ORIGIN['lineage_sha256'], 'GUARD_BINDING')
    require(finite(row.get('sampled_at')) and 0 <= time.time() - row['sampled_at'] <= 30, 'GUARD_STATE_STALE')
    require(row.get('state') == 'MONITORING' and p.get('inhibit') is False and p.get('complete') is False
            and checkpoint.get('manifest_sha256') == manifest_sha256, 'GUARD_NOT_PERMISSIVE')
    policy = config.get('policy') or {}
    require(policy == GUARD_POLICY, 'GUARD_POLICY_CHANGED')
    free = os.statvfs(OUTPUT)
    require(integer(p.get('disk_early_threshold_bytes')) and free.f_bavail * free.f_frsize >= p['disk_early_threshold_bytes'],
            'GUARD_DISK_MARGIN')
    return digest(raw)


def wait_for_optimizer_permission(ctx, manifest, state, *, timeout=180.0, stop_check=None):
    require(finite(timeout) and 0 < timeout <= 300, 'WAIT_BOUND')
    proof = checkpoint_binding(ctx, manifest, state)
    witness = proof['witness']; process = _self_process_identity()
    require(witness['process_identity'] == process and witness['evaluated_successful_total'] == state['successful_total'],
            'FRESH_RESUME_EVALUATION_REQUIRED')
    require(all(witness['before'][key] == state[key] for key in ('successful_total', 'attempted_total', 'skipped_total', 'data_cursor')),
            'FRESH_RESUME_COUNTERS_CHANGED')
    end = time.monotonic() + timeout
    while True:
        require(not stop_active() and not (stop_check and stop_check()), 'OWNER_STOP')
        require(read(ADMISSION, 64000) == ctx['raw'] and read(WRAPPER) == ctx['wrapper'], 'WAIT_CONTEXT_CHANGED')
        active = activation_status(ctx)
        if active['active']:
            permit = active['permit']
            if witness['kind'] == 'BOOTSTRAP_RESTORE':
                require(active['initial_process_identity'] == process and permit['checkpoint']['manifest_sha256'] == proof['manifest_sha256']
                        and permit['evaluation_witness'] == witness, 'INITIAL_PERMIT_PROCESS_OR_CHECKPOINT')
            else:
                require(witness['kind'] == 'RESUME_RESTORE' and state['successful_total'] >= 25,
                        'LATER_RESUME_SCOPE')
            maintenance = STATE / 'OWNER_MAINTENANCE.flag'
            if maintenance.exists() or maintenance.is_symlink():
                require(time.monotonic() < end, 'WAIT_OPTIMIZER_PERMISSION_TIMEOUT')
                time.sleep(0.25)
                continue
            try:
                guard_sha = _guard_permission(ctx, proof['manifest_sha256'])
            except Hold as exc:
                if str(exc) not in {'HOLD_QWEN_REVISION_GUARD_STATE_STALE', 'HOLD_QWEN_REVISION_GUARD_NOT_PERMISSIVE'}:
                    raise
            else:
                pointer, _ = document(OUTPUT / 'latest_checkpoint.json', 16384)
                require(pointer.get('directory') == manifest['directory'] and pointer.get('manifest_sha256') == proof['manifest_sha256']
                        and not stop_active() and not (stop_check and stop_check()), 'FINAL_OPTIMIZER_GATE_CHANGED')
                return {'state': 'OPTIMIZER_PERMISSION_VERIFIED', 'optimizer_allowed': True,
                    'activation_sha256': active['permit_sha256'], 'guard_state_sha256': guard_sha,
                    'checkpoint_manifest_sha256': proof['manifest_sha256'], 'process_identity': process}
        else:
            require(active['bootstrap_pending'] is True, 'BOOTSTRAP_EXPIRED')
        require(time.monotonic() < end, 'WAIT_OPTIMIZER_PERMISSION_TIMEOUT')
        time.sleep(0.25)
