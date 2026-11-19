#!/usr/bin/env python3
"""One bounded read-only observation of the admitted Qwen student, never a launch."""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import time
import types

ROOT = Path('/root/nox')
STATE = ROOT / 'state'
SCRIPTS = ROOT / 'scripts'
OUTPUT = ROOT / 'lora/qwen35_9b/6907283384'
CORPUS = STATE / 'qwen_corpus/6907283384'
PROC = Path('/proc')
CGROUP = Path('/sys/fs/cgroup')
REQUEST = '6907283384'
SOURCE = '2a0d18d8c4434c4798335868df4b28be0e507ed5'
INSTALL_SHA = '2336a33272f75d9fc56efd74172ccf09bba5067cceb1f67b6a966812d9a70262'
ADMISSION_SHA = 'c82b6d4eadabf973ad184f87b120243b74acf78c52565b17440a19f5566c3a33'
WRAPPER_SHA = '9bc41d32abbdb245dcc03f1611c28e27f5423d3a59819093c0394c59c56f4da5'
PINS = {
    'qwen_student_training_entry.py': '259ac097f3ceec5be217748667a421ab5c39ebb56b9b2817fd1368d278f99cb0',
    'owner_qwen_training_contract.py': '7108da4d4949887414f33f5693fe901e3eb5fc63eb97f2b98d1371fed912f50a',
    'owner_qwen_memfd.py': '938335009efe691a9cef7b41daa7c55f3c8d3d8618a10a5eb5db125fd45afa82',
    'owner_qwen_corpus.py': '1509c31789c2c39507d726515ca1c24a5de5545d8c305c7de0ddbba82058b7eb',
    'qwen35_9b_manifest.json': '2275fc88370ca8ba409a791819e13c8ab7d4e38cce4576a13170b05bcb8b839b',
}
DATA_PINS = {
    'train.jsonl': 'b041525f2e980c14a8d50cbf71025c110affde4f1f41b384ca98fa563f745f5a',
    'holdout.jsonl': '8e5997480578bfa82aee39bce2d428293ff48a1a5bf15303043f52661c388c11',
    'corpus_manifest.json': '28e0eb7148d55ac54919cf853bccf1d7dc046f823f04b602aa50b09702884897',
}
SERVICE = 'nox-train-volta-t866u'
SHA = re.compile('[a-f0-9]{64}')
NAME = re.compile('checkpoint-u[0-9]{8}-a[0-9]{8}-g[0-9]{20}')
REQUIRED = {'adapter_model.safetensors', 'adapter_config.json', 'optimizer.pt', 'scheduler.pt',
            'scaler.pt', 'rng_state.pt', 'python_rng.json', 'student_state.json', 'lineage.json'}


class Hold(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise Hold('HOLD_QWEN_OBSERVE_' + code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(info):
    return tuple(getattr(info, key) for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def read(path, maximum=2 * 1024 ** 2, *, expected=None, keep=True, deadline=None):
    path = Path(path)
    require(not any(p.is_symlink() for p in (*path.parents, path)), 'SYMLINK')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= maximum, 'FILE_BOUND')
        h, chunks, total = hashlib.sha256(), [], 0
        while True:
            require(deadline is None or time.monotonic() < deadline, 'READ_DEADLINE')
            block = stream.read(min(1024 * 1024, maximum + 1 - total))
            if not block:
                break
            total += len(block)
            require(total <= maximum, 'FILE_BOUND')
            h.update(block)
            if keep:
                chunks.append(block)
        after, named = os.fstat(stream.fileno()), path.stat(follow_symlinks=False)
        require(total == before.st_size and identity(before) == identity(after) == identity(named), 'READ_RACE')
    value = h.hexdigest()
    require(expected is None or value == expected, 'FILE_SHA')
    return b''.join(chunks), {'bytes': total, 'sha256': value, 'mtime_ns': before.st_mtime_ns}


def strict_pairs(rows):
    result = {}
    for key, value in rows:
        require(key not in result, 'JSON_DUPLICATE')
        result[key] = value
    return result


def document(path, expected=None):
    raw, meta = read(path, expected=expected)
    value = json.loads(raw, object_pairs_hook=strict_pairs,
                       parse_constant=lambda _: require(False, 'NONFINITE_JSON'))
    require(isinstance(value, dict), 'DOCUMENT')
    return value, meta


def code(exc):
    message = str(exc)
    return message if re.fullmatch('HOLD_[A-Z0-9_]{1,100}', message) else type(exc).__name__


def integer(value):
    return type(value) is int and 0 <= value <= 10 ** 12


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def load_contract():
    path = SCRIPTS / 'owner_qwen_training_contract.py'
    raw, _ = read(path, expected=PINS[path.name])
    module = types.ModuleType('_nox_observe_qwen_contract')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def admission():
    installed, install_meta = document(STATE / ('owner_qwen_install_' + REQUEST + '.json'), INSTALL_SHA)
    require(installed.get('schema') == 'NOX_QWEN_INITIAL_OWNER_INSTALL_V1'
            and installed.get('request') == REQUEST and installed.get('source_sha') == SOURCE
            and installed.get('state') == 'NEW_STUDENT_STARTED_ACCEPTANCE_PENDING'
            and installed.get('source_installed') is True and installed.get('source_pins') == PINS,
            'INSTALL_RECEIPT')
    pointer, pointer_meta = document(STATE / 'owner_training_admission.json', ADMISSION_SHA)
    expected_sources = {str(SCRIPTS / name): pin for name, pin in PINS.items() if name.endswith('.py')}
    profile = pointer.get('student_profile')
    require(pointer.get('schema') == 'NOX_OWNER_TRAINING_ADMISSION_V1'
            and pointer.get('request') == REQUEST and pointer.get('source_sha') == SOURCE
            and pointer.get('sources') == expected_sources and profile == installed.get('student_profile'), 'ADMISSION')
    sources = {name: read(SCRIPTS / name, expected=pin)[1] for name, pin in PINS.items()}
    wrapper, wrapper_meta = read(SCRIPTS / 'run_train_volta_t866u.sh', expected=WRAPPER_SHA)
    command_lines = [line[:-2] for line in wrapper.decode().splitlines()
                     if line.startswith('/root/venv_volta/bin/python -u ') and line.endswith(' &')]
    require(len(command_lines) == 1, 'WRAPPER_COMMAND')
    argv = shlex.split(command_lines[0])
    require(argv[:3] == ['/root/venv_volta/bin/python', '-u', str(SCRIPTS / 'qwen_student_training_entry.py')]
            and '--resume' not in argv and argv[-2:] == ['--successful-updates', '5'], 'WRAPPER_GOAL')
    return installed, pointer, argv, {'installation': install_meta, 'admission': pointer_meta,
                                    'wrapper': wrapper_meta, 'sources': sources}


def lineage_proof(value, contract, profile):
    expected_base = {'model_id': contract.MODEL_ID, 'revision': contract.REVISION,
                     'manifest_sha256': contract.MANIFEST_SHA, 'verified_files': 16,
                     'verified_bytes': 19_329_393_661, 'full_base_sha256_verified': True}
    require(value.get('schema') == contract.SCHEMA and value.get('base') == expected_base
            and value.get('entry_sha256') == PINS['qwen_student_training_entry.py']
            and value.get('contract_sha256') == PINS['owner_qwen_training_contract.py']
            and value.get('memfd_source_sha256') == PINS['owner_qwen_memfd.py'], 'LINEAGE_SOURCE')
    require(value.get('train_sha256') == DATA_PINS['train.jsonl']
            and value.get('holdout_sha256') == DATA_PINS['holdout.jsonl']
            and value.get('dataset_manifest_sha256') == DATA_PINS['corpus_manifest.json']
            and value.get('runtime_versions') == profile['runtime_versions'], 'LINEAGE_CORPUS')
    require(value.get('target_names') == list(contract.text_projection_names())
            and value.get('targets', {}).get('tensors') == 2 * len(contract.text_projection_names())
            and integer(value.get('targets', {}).get('parameters'))
            and value['targets']['parameters'] > 0 and value['targets'].get('dtype') == 'float32'
            and value.get('precision') == 'NF4_FP16_FP32_LORA'
            and value.get('optimizer') == 'AdamW_UNFUSED_FP32'
            and value.get('accumulation') == 8 and value.get('sequence_length') == 512
            and value.get('planned_updates') == 50_000, 'LINEAGE_TRAINING_CONTRACT')
    return {'lineage_sha256': contract.canonical_sha(value), 'full_model_load_evidence_verified': True,
            'base_files_verified_by_native_loader': 16, 'base_bytes_verified_by_native_loader': 19_329_393_661,
            'base_files_rehashed_by_observer': False, 'trainable_tensors': value['targets']['tensors'],
            'trainable_parameters': value['targets'].get('parameters'), 'precision': value['precision'],
            'evidence_scope': 'PINNED_TRAINER_LINEAGE_AFTER_FULL_BASE_LOAD_AND_INITIAL_HOLDOUT'}


def update_chain(state, contract):
    good, attempted, skipped = (state.get(key) for key in ('successful_total', 'attempted_total', 'skipped_total'))
    updates = state.get('update_evidence')
    require(all(integer(value) for value in (good, attempted, skipped)) and good <= 1000
            and attempted == good + skipped and isinstance(updates, list) and len(updates) == good,
            'UPDATE_COUNTERS')
    before = None
    for index, row in enumerate(updates):
        contract.validate_update_evidence(row)
        require(row['optimizer_step_before'] == index and row['optimizer_step_after'] == index + 1
                and (before is None or before == row['adapter_sha_before']), 'UPDATE_CHAIN')
        before = row['adapter_sha_after']
    if good >= 5:
        require(len({item for row in updates[:5] for item in row['training_example_sha256']}) >= 40,
                'FIRST_FIVE_EXAMPLE_DIVERSITY')
    require(number(state.get('initial_holdout_loss')) and number(state.get('last_holdout_loss'))
            and integer(state.get('holdout_evaluated_successful_total'))
            and state['holdout_evaluated_successful_total'] <= good, 'HOLDOUT_VALUES')
    current = state['holdout_evaluated_successful_total'] == good
    return {'successful_optimizer_steps': good, 'attempted_steps': attempted, 'skipped_steps': skipped,
            'positive_optimizer_updates_verified': good > 0, 'adapter_tensor_sha256': before,
            'finite_gradient_and_tensor_delta_chain_verified': good > 0,
            'holdout_current': current, 'holdout_loss': state['last_holdout_loss'],
            'initial_holdout_loss': state['initial_holdout_loss'],
            'holdout_threshold_pass': current and state['last_holdout_loss'] <= state['initial_holdout_loss'] * 1.05 + 0.01}


def checkpoint_proof(contract, lineage, deadline):
    pointer, pointer_meta = document(OUTPUT / 'latest_checkpoint.json')
    name = pointer.get('directory', '')
    require(isinstance(name, str) and NAME.fullmatch(name)
            and isinstance(pointer.get('manifest_sha256'), str) and SHA.fullmatch(pointer['manifest_sha256']), 'CHECKPOINT_POINTER')
    directory = OUTPUT / name
    manifest, manifest_meta = document(directory / 'checkpoint_manifest.json', pointer['manifest_sha256'])
    files = manifest.get('files_sha256')
    require(isinstance(files, dict) and REQUIRED <= files.keys() and len(files) <= 32
            and all(re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,95}', key) and key != 'checkpoint_manifest.json'
                    and isinstance(pin, str) and SHA.fullmatch(pin) for key, pin in files.items()), 'CHECKPOINT_FILES')
    require(manifest.get('schema') == 'NOX_QWEN35_9B_CHECKPOINT_V1' and manifest.get('directory') == name
            and manifest.get('lineage_sha256') == contract.canonical_sha(lineage), 'CHECKPOINT_LINEAGE')
    require(not directory.is_symlink() and set(p.name for p in directory.iterdir()) == set(files) | {'checkpoint_manifest.json'},
            'CHECKPOINT_CONTENTS')
    rows, total = {}, 0
    for filename, expected in sorted(files.items()):
        _, meta = read(directory / filename, 2 * 1024 ** 3 - total, expected=expected, keep=False, deadline=deadline)
        total += meta['bytes']; rows[filename] = meta
    saved_lineage, _ = document(directory / 'lineage.json', files['lineage.json'])
    require(saved_lineage == lineage, 'SAVED_LINEAGE')
    state, _ = document(directory / 'student_state.json', files['student_state.json'])
    proof = update_chain(state, contract)
    require(manifest.get('successful_total') == proof['successful_optimizer_steps']
            and manifest.get('attempted_total') == proof['attempted_steps']
            and manifest.get('holdout_evaluated_successful_total') == state['holdout_evaluated_successful_total']
            and manifest.get('holdout_loss') == state['last_holdout_loss']
            and (proof['successful_optimizer_steps'] == 0 or manifest.get('adapter_tensor_sha256') == proof['adapter_tensor_sha256']),
            'CHECKPOINT_STATE')
    read(directory / 'checkpoint_manifest.json', expected=manifest_meta['sha256'])
    after, after_meta = document(OUTPUT / 'latest_checkpoint.json')
    # A concurrent checkpoint publisher may advance this pointer while we hash
    # the old 500 MiB checkpoint. Never present a stale version as CURRENT.
    require(after_meta['sha256'] == pointer_meta['sha256'] and after == pointer,
            'CHECKPOINT_POINTER_CHANGED')
    proof.update(directory=name, manifest_sha256=manifest_meta['sha256'], files=rows, verified_bytes=total,
                 all_manifest_files_sha256_verified=True, required_files=9,
                 latest_pointer_unchanged=True)
    return proof, manifest, state


def terminal_proof(path, contract, lineage, manifest, state, *, acceptance=False):
    row, meta = document(path)
    require(row.get('schema') == contract.PROOF_SCHEMA
            and row.get('lineage_sha256') == contract.canonical_sha(lineage)
            and row.get('base_manifest_sha256') == contract.MANIFEST_SHA
            and row.get('checkpoint') == str(OUTPUT / manifest['directory'])
            and row.get('checkpoint_manifest_sha256') == digest(read(OUTPUT / manifest['directory'] / 'checkpoint_manifest.json')[0])
            and row.get('update_evidence') == state['update_evidence']
            and row.get('successful_optimizer_steps') == state['successful_total']
            and row.get('attempted_steps') == state['attempted_total']
            and row.get('skipped_steps') == state['skipped_total']
            and row.get('final_adapter_tensor_sha256') == manifest['adapter_tensor_sha256']
            and row.get('process_identity') == manifest.get('process_identity'), 'TERMINAL_BINDING')
    current = state['holdout_evaluated_successful_total'] == state['successful_total']
    holdout_ok = current and state['last_holdout_loss'] <= state['initial_holdout_loss'] * 1.05 + 0.01
    require(row.get('holdout_finite') is current and row.get('independent_holdout_accepted') is holdout_ok
            and row.get('initial_holdout_loss') == state['initial_holdout_loss']
            and row.get('final_holdout_loss') == state['last_holdout_loss']
            and row.get('holdout_evaluated_successful_total') == state['holdout_evaluated_successful_total'], 'TERMINAL_HOLDOUT')
    state_name = row.get('state')
    require(isinstance(state_name, str) and re.fullmatch('[A-Z][A-Z0-9_]{0,120}', state_name), 'TERMINAL_STATE')
    if acceptance:
        require(state_name == 'STUDENT_RESTART_AND_UPDATES_VERIFIED' and row.get('reload_verified') is True, 'RESTART_ACCEPTANCE')
        contract.verify_proof(row, lineage=lineage, minimum_updates=6)
    return {'state': state_name, 'receipt_sha256': meta['sha256'], 'reload_verified': row.get('reload_verified') is True,
            'successful_optimizer_steps': state['successful_total'], 'holdout_current': current,
            'independent_holdout_accepted': holdout_ok, 'restart_acceptance_verified': acceptance,
            'quality_scope': 'DISJOINT_NEXT_TOKEN_LOSS_NOT_GENERAL_IQ'}


def proc_bytes(path, maximum=32768):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        require(stat.S_ISREG(os.fstat(stream.fileno()).st_mode), 'PROC_TYPE')
        raw = stream.read(maximum + 1)
        require(len(raw) <= maximum, 'PROC_BOUND')
        return raw


def process(pid):
    try:
        raw = proc_bytes(PROC / str(pid) / 'stat', 4096)
        fields = raw[raw.rindex(b')') + 2:].split()
        return {'pid': pid, 'ppid': int(fields[1]), 'start_ticks': int(fields[19]),
                'state': fields[0].decode('ascii'), 'threads': int(fields[17])}
    except (OSError, ValueError, IndexError, Hold):
        return None


def service():
    try:
        child = subprocess.run(['supervisorctl', 'status', SERVICE], capture_output=True, timeout=4)
        raw = child.stdout[:4096]
        match = re.match(rb'nox-train-volta-t866u\s+(RUNNING|STARTING|STOPPED|EXITED|FATAL|BACKOFF|STOPPING|UNKNOWN)\b', raw)
        pid = re.search(rb'\bpid ([0-9]{1,10}),', raw)
        return {'state': match[1].decode() if match else 'UNKNOWN', 'pid': int(pid[1]) if pid else None}
    except Exception as exc:
        return {'state': 'UNKNOWN', 'reason': code(exc), 'pid': None}


def trainers(argv, supervisor):
    found, scanned = [], 0
    script = str(SCRIPTS / 'qwen_student_training_entry.py').encode()
    for item in PROC.iterdir():
        if not item.name.isdecimal():
            continue
        scanned += 1
        require(scanned <= 8192, 'PROCESS_SCAN_BOUND')
        try:
            parts = proc_bytes(item / 'cmdline').rstrip(b'\0').split(b'\0')
            if script not in parts:
                continue
            before = process(int(item.name))
            if before is None:
                continue
            env = proc_bytes(item / 'environ', 131072).split(b'\0')
            expected = [value.encode() for value in argv]
            ancestry, parent = [], before['ppid']
            for _ in range(8):
                row = process(parent)
                if row is None:
                    break
                ancestry.append(row['pid']); parent = row['ppid']
            after = process(before['pid'])
            if after is None or before['start_ticks'] != after['start_ticks']:
                continue
            found.append({**after, 'exact_admitted_argv': parts == expected,
                          'cuda_visible_devices_1': b'CUDA_VISIBLE_DEVICES=1' in env,
                          'supervisor_ancestry_verified': supervisor['pid'] in ancestry})
        except (OSError, Hold):
            continue
    return found


def runtime_resources():
    out = {}
    for name in ('memory.current', 'memory.max', 'memory.peak'):
        try:
            raw = proc_bytes(CGROUP / name, 128).strip()
            out[name.replace('.', '_') + '_bytes'] = int(raw) if raw.isdigit() else None
        except (OSError, Hold):
            out[name.replace('.', '_') + '_bytes'] = None
    current, maximum = out['memory_current_bytes'], out['memory_max_bytes']
    out['cgroup_headroom_bytes'] = maximum - current if type(current) is int and type(maximum) is int else None
    for name in ('cpu.stat', 'memory.events'):
        try:
            raw = proc_bytes(CGROUP / name, 4096)
            allowed = ('usage_usec', 'user_usec', 'system_usec', 'nr_throttled', 'throttled_usec') if name == 'cpu.stat' else ('low', 'high', 'max', 'oom', 'oom_kill')
            out[name.replace('.', '_')] = {key: int(value) for line in raw.decode('ascii').splitlines()
                                           for key, value in [line.split()] if key in allowed and value.isdecimal()}
        except (OSError, ValueError, Hold):
            out[name.replace('.', '_')] = None
    for label, path in (('ssd', ROOT), ('shm', Path('/dev/shm'))):
        try:
            fs = os.statvfs(path); out[label + '_free_bytes'] = fs.f_bavail * fs.f_frsize
        except OSError:
            out[label + '_free_bytes'] = None
    try:
        row = subprocess.run(['nvidia-smi', '--query-gpu=index,memory.used,memory.free,utilization.gpu', '--format=csv,noheader,nounits'], capture_output=True, timeout=4)
        out['gpus'] = []
        for line in row.stdout[:4096].decode('ascii').splitlines():
            values = [part.strip() for part in line.split(',')]
            if len(values) == 4 and all(value.isdecimal() for value in values):
                out['gpus'].append(dict(zip(('index', 'used_mib', 'free_mib', 'utilization_percent'), map(int, values))))
    except Exception as exc:
        out['gpu_observation'] = code(exc)
    return out


def flags():
    out = {}
    for name in ('TRAIN_HOLD.flag', 'TRAIN_PAUSE_REQUEST.flag'):
        path = STATE / name
        row = {'present': path.exists() or path.is_symlink()}
        if row['present']:
            try:
                raw, meta = read(path, 4096); row.update(meta)
                row['this_qwen_window_complete'] = raw == ('OWNER_QWEN_WINDOW_COMPLETE request=' + REQUEST + ' goal=5\n').encode()
                row['this_qwen_window_failed'] = raw == ('OWNER_QWEN_WINDOW_FAILED request=' + REQUEST + ' goal=5\n').encode()
            except Exception as exc:
                row['reason'] = code(exc)
        out[name] = row
    paths = [ROOT / name for name in ('STOP', 'STOP.flag', 'stop.flag', '.stop', 'program/STOP', 'state/STOP')] + [Path('/workspace/NOX_STOP')]
    out['global_stop_present'] = any(path.exists() or path.is_symlink() for path in paths)
    return out


def log_projection():
    rows = []
    for channel in ('stdout', 'stderr'):
        try:
            child = subprocess.run(['supervisorctl', 'tail', SERVICE, channel], capture_output=True, timeout=4)
            for line in child.stdout[-8192:].decode('utf-8', errors='replace').splitlines():
                error = re.match(r'^([A-Za-z][A-Za-z0-9_]{0,70}(?:Error|Exception)):', line)
                if error:
                    rows.append({'exception_class': error[1], 'channel': channel, 'current_pid_bound': False})
                    continue
                try:
                    item = json.loads(line)
                except (ValueError, TypeError):
                    continue
                state = item.get('state') if isinstance(item, dict) else None
                if not isinstance(state, str) or not re.fullmatch('(HOLD_[A-Z0-9_]{1,100}|PINNED_PUBLIC_BASE_STAGING|REAL_CORPUS_TOKENIZED_ADMISSION|STUDENT_UPDATES_CHECKPOINTED_RESTART_ACCEPTANCE_REQUIRED|STUDENT_RESTART_AND_UPDATES_VERIFIED)', state):
                    continue
                row = {'state': state, 'channel': channel, 'current_pid_bound': False}
                for key in ('bytes', 'downloaded_bytes', 'verified_bytes', 'completed_files', 'total_files', 'successful_optimizer_steps', 'attempted_steps', 'skipped_steps'):
                    if integer(item.get(key)):
                        row[key] = item[key]
                rows.append(row)
        except Exception:
            continue
    return rows[-8:]


def snapshot():
    deadline = time.monotonic() + 50
    result = {'schema': 'NOX_QWEN_TRAINING_READ_ONLY_OBSERVATION_V1', 'recorded_unix': time.time(),
              'request': REQUEST, 'source_sha': SOURCE, 'read_only': True, 'files_written': 0,
              'training_started': False, 'model_loaded_by_observer': False, 'raw_corpus_exported': False,
              'positive_optimizer_updates_verified': False, 'restart_acceptance_verified': False}
    result['service_before'] = service()
    result['resources'] = runtime_resources()
    result['flags'] = flags()
    chat = process(7637)
    result['primary_chat_identity_unchanged'] = bool(chat and chat['start_ticks'] == 149189867)
    try:
        installed, pointer, argv, source_evidence = admission()
        result['source_evidence'] = source_evidence
        contract = load_contract()
        result['processes'] = trainers(argv, result['service_before'])
        result['single_admitted_child_observed'] = len(result['processes']) == 1 and all(result['processes'][0][key] for key in
            ('exact_admitted_argv', 'cuda_visible_devices_1', 'supervisor_ancestry_verified'))
        result['corpus'] = {name: read(CORPUS / name, 32 * 1024 ** 2, expected=pin, keep=False, deadline=deadline)[1]
                            for name, pin in DATA_PINS.items()}
        result['corpus'].update(train_rows=128, holdout_rows=16, snapshot_provenance_verified=True)
        lineage_path = OUTPUT / 'owner_lineage.json'
        result['state'] = 'ADMITTED_PROCESS_RUNNING_PREPARATION_NOT_YET_PROVEN' if result['single_admitted_child_observed'] else 'NO_ADMITTED_LIVE_CHILD_OBSERVED'
        if lineage_path.exists() or lineage_path.is_symlink():
            lineage, lineage_meta = document(lineage_path)
            result['model_load'] = lineage_proof(lineage, contract, pointer['student_profile'])
            result['model_load']['lineage_file_sha256'] = lineage_meta['sha256']
            result['state'] = 'FULL_MODEL_LOADED_UPDATES_NOT_YET_CHECKPOINTED'
            if (OUTPUT / 'latest_checkpoint.json').exists():
                proof, manifest, saved_state = checkpoint_proof(contract, lineage, deadline)
                result['checkpoint'] = proof
                result['positive_optimizer_updates_verified'] = proof['positive_optimizer_updates_verified']
                result['state'] = 'POSITIVE_UPDATES_CHECKPOINTED' if result['positive_optimizer_updates_verified'] else 'CHECKPOINT_WITHOUT_POSITIVE_OPTIMIZER_UPDATES'
                if (OUTPUT / 'owner_last_result.json').exists():
                    result['terminal'] = terminal_proof(OUTPUT / 'owner_last_result.json', contract, lineage, manifest, saved_state)
                    result['state'] = result['terminal']['state']
                if (OUTPUT / 'owner_acceptance.json').exists():
                    result['acceptance'] = terminal_proof(OUTPUT / 'owner_acceptance.json', contract, lineage, manifest, saved_state, acceptance=True)
                    result['restart_acceptance_verified'] = True
            read(lineage_path, expected=lineage_meta['sha256'])
        if (OUTPUT / 'owner_progress.json').exists():
            progress, meta = document(OUTPUT / 'owner_progress.json')
            projected = {key: progress[key] for key in ('successful_optimizer_steps', 'attempted_steps', 'skipped_steps', 'pid') if integer(progress.get(key))}
            if number(progress.get('loss')):
                projected['loss'] = progress['loss']
            if number(progress.get('time')):
                projected['age_seconds'] = max(0, time.time() - progress['time'])
            result['progress_telemetry'] = dict(projected, evidence_only='NOT_AN_OPTIMIZER_PROOF', sha256=meta['sha256'])
        read(STATE / 'owner_training_admission.json', expected=ADMISSION_SHA)
        for name, pin in PINS.items():
            read(SCRIPTS / name, expected=pin)
        read(SCRIPTS / 'run_train_volta_t866u.sh', expected=WRAPPER_SHA)
        result['admission_sources_unchanged_during_observation'] = True
    except Exception as exc:
        result['state'] = 'READ_ONLY_OBSERVATION_PARTIAL'
        result['reason'] = code(exc)
        result['admission_sources_unchanged_during_observation'] = False
        result['positive_optimizer_updates_verified'] = False
        result['restart_acceptance_verified'] = False
    result['logs_unbound'] = log_projection()
    result['service_after'] = service()
    result['recorded_end_unix'] = time.time()
    return result


def main():
    value = snapshot()
    print('NOX_MAINT_REPAIR=' + json.dumps({'kind': 'qwen_training_observation', 'data': value}, separators=(',', ':'), allow_nan=False), flush=True)
    print('NOX_MAINT_REPAIR_COMPLETE=true', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
