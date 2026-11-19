#!/usr/bin/env python3
"""Qwen-only adapter for the existing media controller and existing six-worker queue.

No daemon or trainer is created. An exact completed window6 admits media only;
an exact window1000 additionally admits checkpointed pause and queued handback.
"""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import types

ROOT = Path('/root/nox')
CONFIG = ROOT / 'config/owner_qwen_media_handoff.json'
CONFIG_SCHEMA = 'NOX_QWEN_MEDIA_HANDOFF_CONFIG_V1'
REVISION_CONFIG_SCHEMA = 'NOX_QWEN_MEDIA_HANDOFF_REVISION_CONFIG_V1'
REVISION_VERIFIER_SHA = 'd3b2905c568d088cde2d8267f02f9e913f9fe1d3e46f590992c3a7fcb138ae14'
DEPENDENCIES = {
    'owner_media_training_handoff.py': '36db3c363ffddfc144c6127e1a9407132bbe39d38996233bf3dd64e5b3cb6ec8',
    'owner_qwen_window_entry.py': 'fb9b9dd403f7b1e5d94b8192ce7ad63394ba8a6b3988cc298fc90a195aa191a7',
    'owner_qwen_install_entry.py': '864fe6b0e1567931f94d0b0be55651227ee00fd9106abc4c82e09c13601975d7',
    'owner_qwen_training_observe.py': 'f2dc6c155b682bdeb663bc383f1aa1db70895f815939099690d898262a3d986a',
}
MEDIA_SHA = 'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5'
INSTALLER_SHA = 'e66a5b743deb0dfaa7e1e846e11b2d06190962d9ba0ba4abb67abeca54c02ca5'
ACCEPTED_SIX_SHA = '2076f7050169692e0333747d07abb5c290b429c1b30d56fd55928fc215edfc00'
SERVICE = 'nox-train-volta-t866u'
SCHEMA = 'NOX_QWEN_MEDIA_HANDBACK_V1'
SCOPE = 'QWEN_CHECKPOINT_RESTORED_TRAINER_ADMISSION_ONLY'
BLOCKERS = ['OPTIMIZER_PROGRESS_AFTER_RESUME_NOT_PROVEN', 'MODEL_PROMOTION_NOT_AUTHORIZED']
HEAVY = ('nox-distill-worm-t811u', 'nox-self-improve-t846u', 'nox-self-learning-loop',
         'nox-teacher-serve-t811u', 'nox-offload-t850u', 'nox-downloads-t802u',
         'nox-watch-swap-t845u', 'nox-agent-architect-t859u', 'nox-agent-tuner-t858u')
SHA = re.compile('[a-f0-9]{64}')
BOUND = None


class QwenHold(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise QwenHold(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, limit=2 * 1024 ** 2):
    path = Path(path)
    require(not any(p.is_symlink() for p in (*path.parents, path)), 'HOLD_QWEN_HANDOFF_SYMLINK')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= limit, 'HOLD_QWEN_HANDOFF_FILE_BOUND')
        raw = stream.read(limit + 1)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(len(raw) == before.st_size and identity(before) == identity(os.fstat(stream.fileno()))
                == identity(path.stat(follow_symlinks=False)), 'HOLD_QWEN_HANDOFF_READ_RACE')
        return raw


def load(name, *, alias_file=None):
    path = ROOT / 'scripts' / name
    raw = read(path)
    require(digest(raw) == DEPENDENCIES[name], 'HOLD_QWEN_HANDOFF_DEPENDENCY_PIN')
    value = types.ModuleType('_nox_qwen_handoff_' + name.removesuffix('.py'))
    value.__file__ = str(alias_file or path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value


def revision_context_shape(value):
    require(isinstance(value, dict) and set(value) == {'request', 'source_sha', 'receipt_sha256'}
            and type(value['request']) is str and re.fullmatch('[0-9]{1,24}', value['request'])
            and re.fullmatch('[a-f0-9]{40}', str(value['source_sha']))
            and SHA.fullmatch(str(value['receipt_sha256'])), 'HOLD_QWEN_HANDOFF_EXECUTION_REFERENCE')
    return dict(value)


def make_revision_media_config(previous, revision_ref, *, source_sha256):
    """Pure config transition; the ca8 media-runtime configuration is untouched."""
    keys = {'schema', 'enabled', 'resume_training_after_media', 'source_sha256', 'dependencies',
            'runtime_sha256', 'installer_sha256', 'media_config_sha256', 'window_admission'}
    require(isinstance(previous, dict) and set(previous) == keys and previous['schema'] == CONFIG_SCHEMA
            and previous['enabled'] is True and previous['resume_training_after_media'] is True
            and previous['dependencies'] == DEPENDENCIES and previous['runtime_sha256'] == MEDIA_SHA
            and previous['installer_sha256'] == INSTALLER_SHA,
            'HOLD_QWEN_HANDOFF_REVISION_CONFIG_PREIMAGE')
    require(SHA.fullmatch(str(source_sha256)) and SHA.fullmatch(str(REVISION_VERIFIER_SHA)),
            'HOLD_QWEN_HANDOFF_REVISION_CONFIG_PINS')
    value = copy.deepcopy(previous)
    value.update(schema=REVISION_CONFIG_SCHEMA, source_sha256=source_sha256,
                 window_admission=revision_context_shape(previous['window_admission']),
                 execution_revision=revision_context_shape(revision_ref),
                 execution_verifier_sha256=REVISION_VERIFIER_SHA)
    return value


def make_successor_media_config(previous, revision_ref, *, source_sha256):
    """Exact revision-to-revision handoff binding; the media runtime is unchanged."""
    predecessor = {'request': '6914959637', 'source_sha': 'a06c6a039ebccd6eaa754914624ab5477beca47b',
                   'receipt_sha256': '2f16be7a0bf648621f845c898dd2cc078a98f608fa5b01b3153890c7e3dc41d9'}
    origin = {'request': '6908281920', 'source_sha': '35931438c591a9bb5a649e851f155c4313f28562',
              'receipt_sha256': 'fa0ed9dd2088a247b2ccc94ad60f9962c0d502121c12bf00e31436c9cf487662'}
    keys = {'schema', 'enabled', 'resume_training_after_media', 'source_sha256', 'dependencies',
            'runtime_sha256', 'installer_sha256', 'media_config_sha256', 'window_admission',
            'execution_revision', 'execution_verifier_sha256'}
    require(isinstance(previous, dict) and set(previous) == keys and previous['schema'] == REVISION_CONFIG_SCHEMA
            and previous['enabled'] is True and previous['resume_training_after_media'] is True
            and previous['dependencies'] == DEPENDENCIES and previous['runtime_sha256'] == MEDIA_SHA
            and previous['installer_sha256'] == INSTALLER_SHA and SHA.fullmatch(str(previous['media_config_sha256']))
            and previous['source_sha256'] == 'e8fa87f3e84d90fad90030cff9b8e548280b4d3097bde83ba6cedd9f4bef46ce'
            and previous['execution_verifier_sha256'] == '0dbb06d3384b3436165056ccf4e35bff937fda4f85d96ab2a97ab16a6619998e'
            and previous['execution_revision'] == predecessor and previous['window_admission'] == origin,
            'HOLD_QWEN_HANDOFF_SUCCESSOR_CONFIG_PREIMAGE')
    current = revision_context_shape(revision_ref)
    require(current['request'] != predecessor['request'] and SHA.fullmatch(str(source_sha256))
            and SHA.fullmatch(str(REVISION_VERIFIER_SHA)), 'HOLD_QWEN_HANDOFF_SUCCESSOR_CONFIG_PINS')
    value = copy.deepcopy(previous)
    value.update(source_sha256=source_sha256, execution_revision=current,
                 execution_verifier_sha256=REVISION_VERIFIER_SHA)
    return value


def revision_module():
    path = ROOT / 'scripts/owner_qwen_execution_revision.py'; raw = read(path)
    require(SHA.fullmatch(str(REVISION_VERIFIER_SHA)) and digest(raw) == REVISION_VERIFIER_SHA,
            'HOLD_QWEN_HANDOFF_EXECUTION_VERIFIER_PIN')
    value = types.ModuleType('_nox_qwen_handoff_execution_verifier'); value.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), value.__dict__)
    return value


def active_execution(ctx):
    if 'execution' in ctx:
        require(ctx['_revision_verifier'].activation_status(ctx)['active'] is True,
                'WAIT_QWEN_EXECUTION_BOOTSTRAP')


def current_arguments(actions, ctx):
    return list(ctx['argv']) if 'execution' in ctx else actions.window.arguments(
        actions.h, ctx['profile'], ctx['admission']['request'], digest(ctx['raw']), 1000, resume=True)


class Admission:
    def __init__(self, namespace, runtime):
        self.ns, self.runtime, self.admission = namespace, runtime, None
        self.resume_after_media = False
        self.execution_revision, self.historical_window = None, None
        self.window = load('owner_qwen_window_entry.py')
        raw_helper = read(ROOT / 'scripts/owner_qwen_install_entry.py')
        require(digest(raw_helper) == DEPENDENCIES['owner_qwen_install_entry.py'], 'HOLD_QWEN_HANDOFF_HELPER_PIN')
        self.window.BUNDLE = {'owner_qwen_install_entry.py': base64.b64encode(raw_helper).decode()}
        self.h = self.window.helper()
        self.obs = load('owner_qwen_training_observe.py')
        self.helper = types.SimpleNamespace(service_state=runtime.service_state, command=runtime.command)

    def configuration(self, source_pin, *, allow_disabled=False):
        raw = read(CONFIG, 32768)
        info = CONFIG.stat()
        require(info.st_uid == os.geteuid() and not info.st_mode & 0o077, 'HOLD_QWEN_HANDOFF_CONFIG_PERMISSIONS')
        config = json.loads(raw)
        keys = {'schema', 'enabled', 'resume_training_after_media', 'source_sha256', 'dependencies',
                'runtime_sha256', 'installer_sha256', 'media_config_sha256', 'window_admission'}
        revision = isinstance(config, dict) and config.get('schema') == REVISION_CONFIG_SCHEMA
        if revision:
            keys |= {'execution_revision', 'execution_verifier_sha256'}
        require(isinstance(config, dict) and set(config) == keys
                and config['schema'] in {CONFIG_SCHEMA, REVISION_CONFIG_SCHEMA}
                and config['source_sha256'] == source_pin and config['dependencies'] == DEPENDENCIES
                and config['runtime_sha256'] == MEDIA_SHA and config['installer_sha256'] == INSTALLER_SHA
                and type(config['enabled']) is bool and type(config['resume_training_after_media']) is bool,
                'HOLD_QWEN_HANDOFF_CONFIG_SCOPE')
        for name, expected in DEPENDENCIES.items():
            require(digest(read(ROOT / 'scripts' / name)) == expected, 'HOLD_QWEN_HANDOFF_DEPENDENCY_DRIFT')
        for path, expected in ((Path(__file__), source_pin), (ROOT / 'scripts/owner_media_runtime.py', MEDIA_SHA),
                (ROOT / 'scripts/owner_media_install.py', INSTALLER_SHA),
                (ROOT / 'config/owner_media_runtime.json', config['media_config_sha256'])):
            require(isinstance(expected, str) and SHA.fullmatch(expected) and digest(read(path)) == expected,
                    'HOLD_QWEN_HANDOFF_SOURCE_DRIFT')
        self.execution_revision, self.historical_window = None, None
        if config['enabled'] is False:
            require(not revision, 'HOLD_QWEN_HANDOFF_REVISION_DISABLED')
            require(config['resume_training_after_media'] is False and config['window_admission'] is None,
                    'HOLD_QWEN_HANDOFF_DISABLED_SCOPE')
            require(allow_disabled, 'WAIT_QWEN_HANDOFF_NOT_ENABLED')
            self.admission, self.resume_after_media = None, False
            return config
        context = config['window_admission']
        require(isinstance(context, dict)
                and set(context) == {'request', 'source_sha', 'receipt_sha256'}
                and re.fullmatch('[0-9]{1,24}', str(context['request']))
                and re.fullmatch('[a-f0-9]{40}', str(context['source_sha']))
                and SHA.fullmatch(str(context['receipt_sha256'])), 'HOLD_QWEN_HANDOFF_WINDOW_CONTEXT')
        self.admission = dict(context)
        self.resume_after_media = config['resume_training_after_media']
        if revision:
            require(self.resume_after_media is True
                    and config['execution_verifier_sha256'] == REVISION_VERIFIER_SHA
                    and SHA.fullmatch(str(REVISION_VERIFIER_SHA)), 'HOLD_QWEN_HANDOFF_EXECUTION_CONFIG')
            self.historical_window = revision_context_shape(context)
            self.execution_revision = revision_context_shape(config['execution_revision'])
            self.admission = dict(self.execution_revision)
        return config

    def context(self):
        require(self.admission is not None, 'WAIT_QWEN_BACKGROUND_ADMISSION_MISSING')
        if self.execution_revision is not None:
            verifier = revision_module(); ctx = verifier.current_context(self.execution_revision)
            require(ctx['context'] == self.admission
                    and ctx['origin']['window_reference'] == self.historical_window
                    and ctx['profile']['successful_updates_goal'] == 1000 and self.resume_after_media is True,
                    'HOLD_QWEN_HANDOFF_EXECUTION_CONTEXT')
            self.obs = ctx['observer']
            ctx.update(lineage_sha256=ctx['contract'].canonical_sha(ctx['lineage']),
                       certificate_sha256=ACCEPTED_SIX_SHA, mode='RUNNING_WINDOW1000', _revision_verifier=verifier)
            return ctx
        ctx = self.window.context(self.h)
        pointer = ctx['admission']
        context = self.admission
        path = self.h.STATE / ('owner_qwen_window_' + context['request'] + '.json')
        raw = read(path)
        require(digest(raw) == context['receipt_sha256'], 'HOLD_QWEN_HANDOFF_SEALED_WINDOW')
        receipt = json.loads(raw)
        accepted = receipt.get('acceptance') or {}
        goal = ctx['profile']['successful_updates_goal']
        require(goal in (6, 1000) and self.resume_after_media is (goal == 1000),
                'HOLD_QWEN_HANDOFF_WINDOW_MODE')
        require(receipt.get('schema') == 'NOX_QWEN_WINDOW_ADVANCE_V1'
                and receipt.get('state') == 'WINDOW_STARTED_ACCEPTANCE_PENDING'
                and receipt.get('request') == context['request'] == pointer.get('request')
                and receipt.get('source_sha') == context['source_sha'] == pointer.get('source_sha')
                and receipt.get('target_goal') == goal
                and receipt.get('new_admission_sha256') == digest(ctx['raw'])
                and receipt.get('wrapper_sha256') == digest(ctx['wrapper'])
                and accepted.get('previous_goal') == {6: 5, 1000: 6}[goal] and accepted.get('target_goal') == goal,
                'HOLD_QWEN_HANDOFF_BACKGROUND_SCOPE')
        lineage, _ = self.obs.document(ctx['output'] / 'owner_lineage.json')
        self.obs.lineage_proof(lineage, ctx['contract'], ctx['profile'])
        certificate, meta = self.obs.document(ctx['output'] / 'owner_acceptance.json')
        require(meta['sha256'] == ACCEPTED_SIX_SHA and certificate.get('successful_optimizer_steps') == 6
                and certificate.get('new_successful_optimizer_steps') == 1
                and certificate.get('state') == 'STUDENT_RESTART_AND_UPDATES_VERIFIED'
                and accepted.get('lineage_sha256') == ctx['contract'].canonical_sha(lineage),
                'HOLD_QWEN_HANDOFF_PRESERVED_SIX_ACCEPTANCE')
        ctx['contract'].verify_proof(certificate, lineage=lineage, minimum_updates=6)
        if goal == 1000:
            require(meta['sha256'] == accepted.get('acceptance_sha256') == accepted.get('terminal_receipt_sha256'),
                    'HOLD_QWEN_HANDOFF_PRESERVED_SIX_ACCEPTANCE')
            cp = accepted.get('checkpoint') or {}
            require(certificate.get('checkpoint') == str(ctx['output'] / str(cp.get('directory')))
                    and certificate.get('checkpoint_manifest_sha256') == cp.get('manifest_sha256')
                    and cp.get('all_checkpoint_file_sha256_verified') is True, 'HOLD_QWEN_HANDOFF_SIX_CHECKPOINT_ANCHOR')
        # For goal6, completion is proved again from actual files before media
        # admission. The configured start receipt alone proves no completion.
        ctx.update(lineage=lineage, lineage_sha256=ctx['contract'].canonical_sha(lineage), certificate=certificate,
                   certificate_sha256=meta['sha256'], mode='RUNNING_WINDOW1000' if goal == 1000 else 'COMPLETED_WINDOW6')
        return ctx

    def training_context(self):
        ctx = self.context()
        require(ctx['mode'] == 'RUNNING_WINDOW1000', 'WAIT_QWEN_COMPLETED_WINDOW_HAS_NO_HANDOFF')
        active_execution(ctx)
        return ctx['admission'], ctx['lineage_sha256']

    def trainer_process(self):
        ctx = self.context()
        require(ctx['mode'] == 'RUNNING_WINDOW1000', 'WAIT_QWEN_COMPLETED_WINDOW_HAS_NO_HANDOFF')
        active_execution(ctx)
        args = current_arguments(self, ctx)
        service = self.runtime.service_state(SERVICE)
        rows = self.obs.trainers(args, service)
        require(len(rows) == 1 and all(rows[0][key] for key in
                ('exact_admitted_argv', 'cuda_visible_devices_1', 'supervisor_ancestry_verified')),
                'WAIT_QWEN_STARTED_PROCESS_IDENTITY')
        row = rows[0]
        return {'pid': row['pid'], 'starttime': row['start_ticks'], 'ppid': row['ppid'], 'cuda': '1', 'service': SERVICE}

    def heavy_service_state(self, name):
        require(name in HEAVY, 'HOLD_QWEN_HANDOFF_SERVICE_SCOPE')
        result = self.h.command(['supervisorctl', 'status', name], 5)
        raw = result.stdout
        require(isinstance(raw, str) and len(raw) <= 4096, 'HOLD_QWEN_HANDOFF_SERVICE_OUTPUT')
        match = re.match(re.escape(name) + r'\s+(RUNNING|STARTING|STOPPED|EXITED|FATAL|BACKOFF|STOPPING)\b', raw)
        return match[1] if match else 'UNKNOWN'


def completed_six(actions):
    """Allow free-GPU media while preserving the completed six-update window."""
    ctx = actions.context(); obs = actions.obs
    require(ctx['mode'] == 'COMPLETED_WINDOW6' and not actions.h.owner_stop(),
            'WAIT_QWEN_COMPLETED_SIX_REQUIRED')
    before = actions.runtime.service_state(SERVICE)
    require(before['state'] in ('STOPPED', 'EXITED'), 'WAIT_QWEN_SIX_TRAINER_NOT_COMPLETE')
    args = actions.window.arguments(actions.h, ctx['profile'], ctx['admission']['request'], digest(ctx['raw']), 6, resume=True)
    require(not obs.trainers(args, before), 'WAIT_QWEN_EXISTING_TRAINER_PROCESS')
    expected = actions.window.completion_hold(ctx['admission']['request'], 6)
    require(read(ROOT / 'state/TRAIN_HOLD.flag', 4096) == expected
            and not (ROOT / 'state/TRAIN_PAUSE_REQUEST.flag').exists()
            and not (ROOT / 'state/TRAIN_PAUSE_REQUEST.flag').is_symlink(), 'HOLD_QWEN_SIX_COMPLETION_FLAGS')
    proof, manifest, state = obs.checkpoint_proof(ctx['contract'], ctx['lineage'], time.monotonic() + 45)
    accepted = obs.terminal_proof(ctx['output'] / 'owner_acceptance.json', ctx['contract'], ctx['lineage'],
                                  manifest, state, acceptance=True)
    terminal, terminal_meta = obs.document(ctx['output'] / 'owner_last_result.json')
    require(proof['successful_optimizer_steps'] == 6 and proof['latest_pointer_unchanged']
            and terminal == ctx['certificate'] and terminal_meta['sha256'] == ctx['certificate_sha256']
            and accepted['receipt_sha256'] == ctx['certificate_sha256']
            and actions.runtime.service_state(SERVICE) == before
            and read(actions.h.ADMISSION) == ctx['raw']
            and read(ROOT / 'state/TRAIN_HOLD.flag', 4096) == expected,
            'HOLD_QWEN_SIX_COMPLETION_CHANGED')
    return {'active': False, 'resume': False, 'qwen_completed_window': 6,
            'admission_sha256': digest(ctx['raw']), 'acceptance_sha256': ctx['certificate_sha256'],
            'checkpoint_manifest_sha256': proof['manifest_sha256'], 'checkpoint_files_verified': len(proof['files']),
            'checkpoint_bytes_verified': proof['verified_bytes'], 'completion_hold_sha256': digest(expected),
            'training_service_started': False}


def paused_checkpoint(actions, yielded):
    """Full committed state; zero new updates are valid and never called learning."""
    ctx = actions.context(); obs = actions.obs
    active_execution(ctx)
    terminal_path = ctx['output'] / 'owner_last_result.json'
    terminal, meta = obs.document(terminal_path)
    require(meta['mtime_ns'] / 1e9 >= yielded['requested_at']
            and terminal.get('state') in {'EXISTING_TRAINER_HOLD_OR_PAUSE', 'HOLD_TRAINING_STOP_REQUESTED'}
            and terminal.get('reload_verified') is True, 'HOLD_QWEN_FRESH_CONTROLLED_PAUSE_REQUIRED')
    process = terminal.get('process_identity') or {}
    previous = yielded.get('qwen_student') or {}
    require(process.get('pid') == previous.get('pid') and process.get('start_ticks') == previous.get('starttime'),
            'HOLD_QWEN_PAUSED_PROCESS_IDENTITY')
    proof, manifest, state = obs.checkpoint_proof(ctx['contract'], ctx['lineage'], time.monotonic() + 45)
    new = terminal.get('new_successful_optimizer_steps')
    good = proof['successful_optimizer_steps']
    require(6 <= good < 1000 and type(new) is int and 0 <= new <= good - 6
            and state['update_evidence'][:6] == ctx['certificate']['update_evidence']
            and proof['latest_pointer_unchanged']
            and terminal.get('lineage_sha256') == ctx['lineage_sha256']
            and terminal.get('checkpoint') == str(ctx['output'] / proof['directory'])
            and terminal.get('checkpoint_manifest_sha256') == proof['manifest_sha256']
            and terminal.get('update_evidence') == state['update_evidence']
            and terminal.get('successful_optimizer_steps') == good
            and terminal.get('attempted_steps') == proof['attempted_steps']
            and terminal.get('skipped_steps') == proof['skipped_steps']
            and terminal.get('final_adapter_tensor_sha256') == proof['adapter_tensor_sha256'],
            'HOLD_QWEN_PAUSED_CHECKPOINT_CHAIN')
    require(new == 0 or manifest.get('process_identity') == process, 'HOLD_QWEN_CURRENT_PROCESS_CHECKPOINT')
    if 'execution' in ctx:
        verifier = ctx['_revision_verifier']
        verifier.checkpoint_binding(ctx, manifest, state)
        require(terminal.get('execution_binding') == verifier.execution_binding(ctx),
                'HOLD_QWEN_PAUSED_EXECUTION_BINDING')
    obs.read(terminal_path, expected=meta['sha256'])
    return {'step': good, 'receipt_sha256': meta['sha256'], 'lineage_sha256': ctx['lineage_sha256'],
            'checkpoint': str(ctx['output'] / proof['directory']), 'manifest_sha256': proof['manifest_sha256'],
            'full_checkpoint_files_verified': True, 'verified_bytes': proof['verified_bytes'],
            'files_verified': len(proof['files']), 'new_successful_optimizer_steps_in_window': new,
            'new_update_required_for_safe_pause': False}


def create_handback(base, namespace, runtime, actions):
    class QwenHandback(base.Handback):
        def configuration(self):
            return actions.configuration(self.source_pin)

        def yield_binding(self, value):
            return {**super().yield_binding(value), 'qwen_student': value['qwen_student'],
                    'qwen_admission_sha256': value['qwen_admission_sha256']}

        def no_trainer(self):
            ctx = actions.context()
            args = current_arguments(actions, ctx)
            require(not actions.obs.trainers(args, runtime.service_state(SERVICE)), 'WAIT_QWEN_EXISTING_TRAINER_PROCESS')

        def checkpoint(self, yielded, lineage):
            proof = paused_checkpoint(actions, yielded)
            require(proof['lineage_sha256'] == lineage and yielded.get('checkpoint') == proof,
                    'HOLD_QWEN_PAUSE_ACK_CHANGED')
            return proof

        def flags(self, yielded, pointer):
            acknowledgement = ('OWNER_QWEN_WINDOW_FAILED request=' + pointer['request'] + ' goal=1000\n').encode()
            require(yielded.get('hold_sha256') == digest(acknowledgement)
                    and digest(read(ROOT / 'scripts/run_train_volta_t866u.sh')) == yielded['wrapper_sha256'],
                    'HOLD_QWEN_PAUSE_FLAGS_CHANGED')
            return {'TRAIN_PAUSE_REQUEST.flag': yielded['pause_token'].encode(), 'TRAIN_HOLD.flag': acknowledgement}

        def resource_gate(self):
            active_execution(actions.context())
            require(not base.stopped(), 'WAIT_OWNER_STOP')
            require(base.plain(ROOT / 'state/train_wants_gpu1').is_file(), 'WAIT_TEACHER_RESERVATION')
            for name in HEAVY:
                require(actions.heavy_service_state(name) in ('STOPPED', 'EXITED', 'FATAL'), 'WAIT_LEGACY_HEAVY_SERVICE_ACTIVE')
            values = actions.obs.runtime_resources()
            available = values.get('cgroup_headroom_bytes')
            floor = 48 * 1024 ** 3 + 19_329_393_661
            require(type(available) is int and available >= floor, 'WAIT_QWEN_RAM_RESTAGING_HEADROOM')
            require(type(values.get('ssd_free_bytes')) is int and values['ssd_free_bytes'] >= 10 * 1024 ** 3,
                    'WAIT_QWEN_CHECKPOINT_DISK_RESERVE')
            gpu = runtime.gpu1()
            require(gpu['free_mib'] >= 30000, 'WAIT_QWEN_GPU1_HEADROOM')
            queue = runtime.queue_ids()
            require(set(queue) == {'queue_running', 'queue_pending'} and not any(queue.values()), 'WAIT_MEDIA_ENGINE_QUEUE_DRAIN')
            return {'gpu1_free_mib': gpu['free_mib'], 'cgroup_available_bytes': available,
                    'cgroup_required_bytes': floor, 'disk_free_bytes': values['ssd_free_bytes'],
                    'disk_required_bytes': 10 * 1024 ** 3, 'base_restaged_bytes': 19_329_393_661}

        def attached_process(self, record):
            deadline = time.monotonic() + 10
            while True:
                try:
                    return super().attached_process(record)
                except Exception as exc:
                    reason = str(exc)
                    if base.stopped() or time.monotonic() >= deadline or not reason.startswith('WAIT_'):
                        raise
                    time.sleep(.25)

        def prepare(self, job):
            config = actions.configuration(self.source_pin, allow_disabled=True)
            service = runtime.service_state(SERVICE)
            if config['enabled']:
                ctx = actions.context()
                if ctx['mode'] == 'COMPLETED_WINDOW6':
                    return completed_six(actions)
                active_execution(ctx)
            if service['state'] != 'RUNNING':
                return self.original_prepare(job)
            require(config['enabled'], 'WAIT_QWEN_HANDOFF_NOT_ENABLED')
            process = actions.trainer_process()
            progress, meta = actions.obs.document(ctx['output'] / 'owner_progress.json')
            process_started = time.time() - time.clock_gettime(time.CLOCK_BOOTTIME) + process['starttime'] / os.sysconf('SC_CLK_TCK')
            allowed_progress = {'NATIVE_STUDENT_UPDATE_OBSERVED'}
            if 'execution' in ctx:
                allowed_progress.add('NATIVE_EXECUTION_EVALUATION_CHECKPOINTED')
                require(progress.get('execution_binding') == ctx['_revision_verifier'].execution_binding(ctx),
                        'HOLD_QWEN_HANDOFF_PROGRESS_EXECUTION_BINDING')
            require(progress.get('state') in allowed_progress
                    and progress.get('pid') == process['pid'] and type(progress.get('time')) in (int, float)
                    and 0 <= time.time() - progress['time'] <= 600
                    and progress['time'] >= process_started - 1 and meta['mtime_ns'] / 1e9 >= process_started - 1,
                    'WAIT_QWEN_RESTORE_NOT_YET_OBSERVED')
            # This telemetry admits a pause request only. The resulting saved
            # optimizer state is proved from every checkpoint file below.
            path = ROOT / 'state/media/training_yield.json'
            if path.exists() or path.is_symlink():
                existing = base.document(path)
                if existing.get('active') is True:
                    require(existing.get('job_id') == job['id']
                            and existing.get('qwen_student') == process
                            and existing.get('qwen_admission_sha256') == digest(ctx['raw']),
                            'WAIT_QWEN_EXISTING_YIELD_REQUIRES_OWNERSHIP')
                    return existing
            yielded = self.original_prepare(job)
            if yielded.get('active'):
                require(yielded.get('job_id') == job['id'], 'HOLD_QWEN_YIELD_JOB_CHANGED')
                yielded.update(qwen_student=process, qwen_admission_sha256=digest(ctx['raw']))
                base.atomic(path, yielded)
            return yielded

        def wait(self, job, yielded):
            if not yielded.get('active'):
                if yielded.get('qwen_completed_window') == 6:
                    self.configuration()
                    ctx = actions.context()
                    latest, _ = actions.obs.document(ctx['output'] / 'latest_checkpoint.json')
                    require(ctx['mode'] == 'COMPLETED_WINDOW6' and not actions.h.owner_stop()
                            and runtime.service_state(SERVICE)['state'] in ('STOPPED', 'EXITED')
                            and digest(ctx['raw']) == yielded['admission_sha256']
                            and ctx['certificate_sha256'] == yielded['acceptance_sha256']
                            and latest.get('manifest_sha256') == yielded['checkpoint_manifest_sha256']
                            and digest(read(ROOT / 'state/TRAIN_HOLD.flag', 4096)) == yielded['completion_hold_sha256'],
                            'HOLD_QWEN_SIX_COMPLETION_CHANGED')
                return self.original_wait(job, yielded)
            self.configuration()
            deadline = time.monotonic() + 180
            while True:
                if runtime.media_stop():
                    raise runtime.MediaHold('WAIT_OWNER_STOP_OR_MAINTENANCE')
                state = runtime.service_state(SERVICE)
                if state['state'] in ('STOPPED', 'EXITED', 'FATAL'):
                    self.no_trainer()
                    ctx = actions.context()
                    require(digest(ctx['raw']) == yielded.get('qwen_admission_sha256'), 'HOLD_QWEN_YIELD_ADMISSION_CHANGED')
                    proof = paused_checkpoint(actions, yielded)
                    expected = ('OWNER_QWEN_WINDOW_FAILED request=' + ctx['admission']['request'] + ' goal=1000\n').encode()
                    require(read(ROOT / 'state/TRAIN_HOLD.flag', 4096) == expected
                            and read(ROOT / 'state/TRAIN_PAUSE_REQUEST.flag', 4096) == yielded['pause_token'].encode(),
                            'HOLD_QWEN_YIELD_FLAGS_CHANGED')
                    yielded.update(checkpoint=proof, hold_sha256=digest(expected))
                    base.atomic(ROOT / 'state/media/training_yield.json', yielded)
                    return
                require(time.monotonic() < deadline, 'WAIT_QWEN_CHECKPOINT_TIMEOUT')
                runtime.update_job(job, state='YIELDING_TRAINING')
                time.sleep(2)

    value = QwenHandback(namespace, runtime, actions, lambda *args, **kwargs: None)
    value.original_prepare, value.original_wait = runtime.prepare_training, runtime.wait_training
    return value


def bind_dispatcher(namespace, runtime):
    global BOUND
    require(BOUND is None and namespace.get('_owner_media_bound') is True
            and namespace.get('_owner_plans_bound') is True and not namespace.get('_owner_lifecycle_bound')
            and namespace.get('WORKERS') == 6 and 'owner_media_resume' not in namespace.get('HANDLERS', {})
            and Path(runtime.__file__) == ROOT / 'scripts/owner_media_runtime.py'
            and digest(read(runtime.__file__)) == MEDIA_SHA, 'HOLD_QWEN_HANDOFF_BINDING')
    # Reuse the reviewed queue/claim/archive machinery. Its public source pin is
    # this adapter, whose checked dependency map includes the unchanged engine.
    base = load('owner_media_training_handoff.py', alias_file=__file__)
    base.SCHEMA, base.SCOPE, base.BLOCKERS = SCHEMA, SCOPE, list(BLOCKERS)
    base.TASK_SOURCE = 'owner_qwen_media_handoff'
    actions = Admission(namespace, runtime)
    BOUND = create_handback(base, namespace, runtime, actions)
    def media_call(function):
        def call(*args, **kwargs):
            try:
                return function(*args, **kwargs)
            except runtime.MediaHold:
                raise
            except Exception as exc:
                text = str(exc)
                reason = text if re.fullmatch('(WAIT|HOLD)_[A-Z0-9_]{1,120}', text) else 'HOLD_QWEN_HANDOFF_UNVERIFIED'
                raise runtime.MediaHold(reason) from None
        return call
    runtime.prepare_training = media_call(BOUND.prepare)
    runtime.wait_training = media_call(BOUND.wait)
    runtime.resume_training = BOUND.callback
    namespace['ingest_owner_orders'] = BOUND.ingest
    namespace['_nox_owner_task_admitted'] = BOUND.admitted
    namespace['HANDLERS']['owner_media_resume'] = BOUND.run
    namespace['owner_mentor'].verify_success = BOUND.verify
    namespace['_owner_qwen_media_handoff_bound'] = True
