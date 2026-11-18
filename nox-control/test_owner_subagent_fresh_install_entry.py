"""Isolated installation/rollback proofs; no native process, GPU or model calls."""
from contextlib import ExitStack, redirect_stdout
from pathlib import Path
import base64
import copy
import io
import json
import os
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

import owner_subagent_fresh_install_entry as entry


def configuration():
    titles = {'runtime': 'Проверить текущие ресурсы и dispatcher',
              'memory': 'Проверить исходную S03 и подтверждения задач',
              'weights': 'Отделить факты старого обучения от новых весов'}
    catalog = {'schema': 'NOX_AUTONOMY_PROCESS_POOL_V1', 'tasks': [
        {'id': 'owner.native.v06.' + role + '.84780aaf911a', 'title': titles[role],
         'handler': entry.HANDLER, 'deps': [], 'priority': 'P1',
         'resource': 'CPU_LIGHT', 'source_sha256': entry.POLICY_SHA,
         'params': {'role': role}} for role in titles]}
    return {'schema': 'NOX_NATIVE_SUBAGENT_BINDING_V1', 'policy_id': 'NOX_WEB_WEIGHTS_V06',
            'policy': {'path': '/root/nox/state/dispatcher/policies/NOX_WEB_WEIGHTS_V06.md',
                       'sha256': entry.POLICY_SHA}, 'catalog': catalog,
            'catalog_sha256': entry.digest(entry.encoded(catalog)), 'instance_id': 60509551,
            'mode': 'NORMAL', 'target': 3, 'owner_authorized': True,
            'owner_request': '6906985850',
            'owner_source_sha': '41fbe63b5e57b1172956f8264c403aefa338aa6d',
            'module_pins': dict(entry.OLD_DEPENDENCIES)}


def history():
    tasks, jobs, admissions, readbacks = {}, [], {}, {}
    for index, task_id in enumerate(sorted(entry.TASKS)):
        claim = {'nonce': str(index) * 24, 'pid': 123, 'worker': str(index)}
        record = {'source_sha256': entry.OLD_CALLBACK, 'task_id': task_id,
                  'claim': claim, 'kind': 'result'}
        admission = {'task_id': task_id, 'kind': 'admission'}
        result_proof = {'receipt_sha256': entry.digest(entry.encoded(record)),
                        's03_item_id': 'S03-result-' + str(index)}
        admission_proof = {'receipt_sha256': entry.digest(entry.encoded(admission)),
                           's03_item_id': 'S03-admission-' + str(index)}
        tasks[task_id] = {'id': task_id, 'handler': entry.HANDLER, 'status': 'done',
                          'owner_claim': claim, 'native_admission': admission,
                          'result': {'receipt': record,
                                     'receipt_sha256': result_proof['receipt_sha256']}}
        jobs.append({'task_id': task_id, 'claim': claim, 's03': result_proof})
        admissions[task_id] = admission_proof
        readbacks[(task_id, 'result')] = result_proof
        readbacks[(task_id, 'admission')] = admission_proof
    callback = Mock()
    callback.s03_readback.side_effect = lambda value: copy.deepcopy(
        readbacks.get((value['task_id'], value['kind'])))
    return {'tasks': tasks}, {'jobs': jobs, 'admission_records_before': admissions}, callback


def training(generation='current'):
    return {'files': {'admission': {'sha256': entry.digest(generation.encode())}},
            'flags': {'TRAIN_HOLD.flag': {'present': False},
                      'TRAIN_PAUSE_REQUEST.flag': {'present': False}},
            'student_profile_sha256': 'd' * 64,
            'service': {'state': 'RUNNING', 'pid': 555},
            'process': {'pid': 555, 'pgrp': 555, 'ppid': 1, 'starttime': 888}}


class FakeNative:
    """Temp-file native shell that accepts control of only the dispatcher."""
    def __init__(self, root, failure=None):
        self.ROOT = root
        self.STATE, self.SCRIPTS = root / 'state', root / 'scripts'
        self.DISPATCHER = self.SCRIPTS / 'nox_dispatcher_t855u.py'
        self.SERVICE = 'nox-dispatcher-t855u'
        self.STATE.mkdir(parents=True)
        self.SCRIPTS.mkdir()
        (self.STATE / 'owner_maintenance.lock').touch()
        self.target = self.SCRIPTS / 'owner_subagent_dispatcher.py'
        self.pool_target = self.SCRIPTS / 'owner_autonomy_pool.py'
        self.process_target = self.SCRIPTS / 'owner_subagent_processes.py'
        self.mentor_target = self.SCRIPTS / 'owner_dispatcher_mentor.py'
        self.config = root / 'config/owner_native_subagents.json'
        self.before = b'original callback fixture\n'
        self.before_pool = b'original pool fixture\n'
        self.before_process = b'original processes fixture\n'
        self.before_mentor = b'original mentor fixture\n'
        self.atomic(self.mentor_target, self.before_mentor)
        self.atomic(self.target, self.before)
        self.atomic(self.pool_target, self.before_pool)
        self.atomic(self.process_target, self.before_process)
        self.atomic(self.config, entry.encoded(configuration()))
        self.queue, self.prior, self.callback = history()
        self.commands, self.writes, self.outputs = [], [], []
        self.state, self.pid, self.starttime = 'RUNNING', 123, 456
        self.failure, self.starts = failure, 0

    def read(self, path, maximum=1048576):
        raw = Path(path).read_bytes()
        if len(raw) > maximum:
            raise AssertionError('Unbounded fixture read')
        return raw

    def atomic(self, path, raw):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        path.chmod(0o600)
        if hasattr(self, 'writes'):
            self.writes.append(path)

    def service(self):
        return {'state': self.state, 'pid': self.pid, 'rc': 0}

    def process(self, pid):
        return {'pid': pid, 'pgrp': pid, 'ppid': 1, 'starttime': self.starttime,
                'argv': ['python3', str(self.DISPATCHER)]}

    def command(self, args, timeout=10):
        if len(args) != 3 or args[0] != 'supervisorctl' or args[2] != self.SERVICE:
            raise AssertionError('Unexpected native control: ' + repr(args))
        self.commands.append(args)
        if args[1] == 'stop':
            self.state, self.pid = 'STOPPED', None
        elif args[1] == 'start':
            self.starts += 1
            if self.starts == 1 and self.failure:
                self.state, self.pid = 'FATAL', None
                if self.failure == 'foreign':
                    self.target.write_bytes(b'concurrent foreign edit\n')
                return 1, 'fixture failure'
            self.state, self.pid, self.starttime = 'RUNNING', 789, 888
            counts = {key: 3 if key == 'done' else 0 for key in
                      ('not_admitted', 'pending', 'running', 'done', 'blocked', 'failed', 'unknown')}
            view = {'queue_counts': counts, 'catalog_tasks': 3, 'owned_model_requests_active': 0,
                    'fresh_resource_check': 'BEFORE_EVERY_SUBMIT',
                    **{key: False for key in ('model_answers_authoritative',
                        'candidate_actions_applied', 'training_updates_verified', 'capacity_maximum_measured')}}
            value = {'n': 6, 'native_subexecutors': {'thread_runner_count': 6, 'target': 3,
                'workers': [], 'director': {'pid': self.pid, 'process_starttime': self.starttime},
                'observed_at': time.time(), 'review_status': view}}
            self.atomic(self.ROOT / 'status/agents_t856u.json', entry.encoded(value))
        else:
            raise AssertionError('Only owned stop/start is allowed')
        return 0, 'fixture'

    def queue_state(self):
        return copy.deepcopy(self.queue)

    def global_stop(self):
        return False

    def active_model(self):
        return dict(entry.CHAT)

    def health(self):
        return {port: 200 for port in ('8080', '8081', '8082')}

    def emit(self, kind, value):
        self.outputs.append((kind, copy.deepcopy(value)))


class FreshInstallerTests(unittest.TestCase):
    def test_config_transition_updates_all_installed_module_pins(self):
        before = configuration()
        raw = entry.encoded(before)
        self.assertEqual(entry.digest(raw), entry.OLD_CONFIG)
        result = entry.checked_config(raw)
        self.assertEqual(entry.digest(result), entry.NEW_CONFIG)
        after = json.loads(result)
        self.assertEqual(after['module_pins'], entry.NEW_DEPENDENCIES)
        after['module_pins'] = entry.OLD_DEPENDENCIES
        self.assertEqual(after, before)

    def test_bundle_failure_is_before_native_operations(self):
        with patch.object(entry, 'BUNDLE', {}):
            with self.assertRaisesRegex(RuntimeError, 'BUNDLE_BOUND'):
                entry.load_helpers()

    def test_packaged_helpers_receive_bundle_without_calling_either_main(self):
        recovery = b'''import base64, types
BUNDLE = {}
def helper():
    value = types.ModuleType('fresh_test_helper')
    value.__dict__['__NOX_' + 'BUNDLE_JSON__'] = BUNDLE
    exec(base64.b64decode(BUNDLE['owner_subagent_install_entry.py']), value.__dict__)
    return value
def main():
    raise AssertionError('recovery main must not run')
'''
        helper = b'''BUNDLE = __NOX_BUNDLE_JSON__
def main():
    raise AssertionError('installer main must not run')
'''
        raws = {'owner_subagent_hash_recovery_entry.py': recovery,
                'owner_subagent_install_entry.py': helper,
                'owner_subagent_dispatcher_fresh.py': b'candidate = True\n',
                'owner_subagent_processes.py': b'processes = True\n',
                'owner_autonomy_pool.py': b'pool = True\n',
                'owner_dispatcher_mentor.py': b'mentor = True\n'}
        assets = {key: base64.b64encode(raw).decode() for key, raw in raws.items()}
        source = Path(entry.__file__).read_text().replace('__NOX_BUNDLE_JSON__', json.dumps(assets))
        packed = types.ModuleType('fresh_packaging_test')
        exec(compile(source, '<fresh-packaged>', 'exec'), packed.__dict__)
        packed.ASSETS = {key: entry.digest(raw) for key, raw in raws.items()}
        value, _, candidate = packed.load_helpers()
        self.assertEqual(value.BUNDLE, assets)
        self.assertEqual(set(candidate), set(raws))
        self.assertEqual(candidate['owner_subagent_dispatcher_fresh.py'], raws['owner_subagent_dispatcher_fresh.py'])

    def test_current_training_generation_is_preserved_without_old_pin(self):
        for generation in ('qwen-initial-five', 'later-authorized-qwen-resume'):
            before = training(generation)
            after = copy.deepcopy(before)
            after['process'] = None  # Natural exit is separate from file preservation.
            entry.preserve_training(before, after)
            after['flags']['TRAIN_HOLD.flag'] = {'present': True, 'sha256': 'e' * 64}
            with self.assertRaisesRegex(RuntimeError, 'TRAINING_IDENTITY_CHANGED'):
                entry.preserve_training(before, after)
        with self.assertRaisesRegex(RuntimeError, 'TRAINING_IDENTITY_CHANGED'):
            entry.preserve_training(training('a'), training('b'))

    def test_historical_completed_readback_never_requeues_or_remembers(self):
        state, prior, callback = history()
        before = copy.deepcopy(state)
        helper = types.SimpleNamespace(queue_state=lambda: copy.deepcopy(state))
        proof = entry.completed_proofs(helper, callback, prior)
        self.assertEqual(set(proof), entry.TASKS)
        self.assertEqual(state, before)
        callback.remember.assert_not_called()
        state['tasks'][sorted(entry.TASKS)[0]]['status'] = 'pending'
        with self.assertRaisesRegex(RuntimeError, 'HISTORICAL_DONE_TASK'):
            entry.completed_proofs(helper, callback, prior)

    def test_foreign_config_blocks_rollback_before_any_write(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            target, config = root / 'callback.py', root / 'config.json'
            target.write_bytes(b'new callback')
            config.write_bytes(b'foreign config')
            helper = Mock()
            helper.read.side_effect = lambda path: path.read_bytes()
            with self.assertRaisesRegex(RuntimeError, 'ROLLBACK_FOREIGN_CHANGE'):
                entry.rollback_files(helper, {
                    target: (b'old callback', b'new callback'),
                    config: (b'old config', b'new config'),
                })
            helper.atomic.assert_not_called()
            self.assertEqual(target.read_bytes(), b'new callback')

    def run_fixture(self, failure=None, training_changed=False, resource_checks=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        helper = FakeNative(Path(temporary.name) / 'nox', failure)
        recovery = types.SimpleNamespace(owned_group=lambda pid: [helper.process(pid)])
        assets = {
            'owner_subagent_dispatcher_fresh.py': Path(entry.__file__).with_name('owner_subagent_dispatcher_fresh.py').read_bytes(),
            'owner_autonomy_pool.py': Path(entry.__file__).with_name('owner_autonomy_pool.py').read_bytes(),
            'owner_subagent_processes.py': Path(entry.__file__).with_name('owner_subagent_processes.py').read_bytes(),
            'owner_dispatcher_mentor.py': Path(entry.__file__).with_name('owner_dispatcher_mentor.py').read_bytes(),
        }
        helper.assets = assets
        original_queue = copy.deepcopy(helper.queue)
        snapshots = [training('new-current-qwen'), training('new-current-qwen')]
        after = training('new-current-qwen')
        if training_changed:
            after['flags']['TRAIN_HOLD.flag'] = {'present': True, 'sha256': '9' * 64}
        snapshots += [after] * 8
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '1234',
                'NOX_OWNER_SOURCE_SHA': 'a' * 40}))
            stack.enter_context(patch.object(entry, 'load_helpers', return_value=(helper, recovery, assets)))
            stack.enter_context(patch.object(entry, 'check_sources'))
            resource_samples = []
            def fresh_resource_sample(_helper):
                if resource_checks is None:
                    allowed = True
                else:
                    if not resource_checks:
                        raise AssertionError('Missing fresh resource admission sample')
                    allowed = resource_checks.pop(0)
                sample = {'observed_at': time.time(), 'admission_allowed': allowed}
                resource_samples.append(sample)
                return sample['admission_allowed']
            stack.enter_context(patch.object(entry, 'resource_admission', side_effect=fresh_resource_sample))
            stack.enter_context(patch.object(entry, 'OLD_MENTOR_SHA', entry.digest(helper.before_mentor)))
            stack.enter_context(patch.object(entry, 'prior_receipt', return_value=helper.prior))
            stack.enter_context(patch.object(entry, 'old_callback', return_value=helper.callback))
            stack.enter_context(patch.object(entry, 'training_snapshot', side_effect=snapshots))
            stack.enter_context(redirect_stdout(io.StringIO()))
            rc = entry.main()
        helper.resource_admission_samples = resource_samples
        self.assertEqual(helper.queue, original_queue)
        self.assertTrue(all(args[2] == helper.SERVICE for args in helper.commands))
        self.assertFalse(any(path.name in ('TRAIN_HOLD.flag', 'TRAIN_PAUSE_REQUEST.flag',
            'owner_training_admission.json', 'run_train_volta_t866u.sh') for path in helper.writes))
        helper.callback.remember.assert_not_called()
        return rc, helper, helper.outputs[-1][1]


    def test_resource_admission_uses_reclaimable_cache_and_holds_on_bad_stats(self):
        gib = 1024 ** 3
        values = {'memory.current': str(8 * gib), 'memory.max': str(8 * gib),
                  'memory.stat': 'inactive_file ' + str(5 * gib) + '\\n'}

        class FakePath:
            def __init__(self, value):
                self.name = str(value).rsplit('/', 1)[-1]
            def read_text(self):
                return values[self.name]

        disk = types.SimpleNamespace(f_bavail=gib, f_frsize=1)
        native = types.SimpleNamespace(ROOT='/nox')
        with patch.object(entry, 'Path', FakePath), \\
                patch.object(entry.os, 'statvfs', return_value=disk):
            # Raw free is zero, but 5 GiB of inactive cache leaves 5 GiB usable.
            self.assertTrue(entry.resource_admission(native))
            values['memory.stat'] = 'inactive_file ' + str(3 * gib) + '\\n'
            self.assertFalse(entry.resource_admission(native))
            values['memory.stat'] = 'inactive_file invalid\\n'
            self.assertFalse(entry.resource_admission(native))

    def test_resource_floor_is_rechecked_after_claim_drain_before_backup_and_stop(self):
        rc, helper, result = self.run_fixture(resource_checks=[True, False])
        self.assertEqual(rc, 2)
        self.assertEqual(helper.commands, [])
        self.assertEqual(result['error'], 'HOLD_SUBAGENT_FRESH_RESOURCE_HEADROOM')
        self.assertEqual(helper.target.read_bytes(), helper.before)
        self.assertFalse((helper.ROOT/'backup/owner_subagent_fresh_gate/1234').exists())
        self.assertEqual([sample['admission_allowed'] for sample in helper.resource_admission_samples], [True, False])
        self.assertTrue(all('observed_at' in sample for sample in helper.resource_admission_samples))

    def test_install_reloads_only_dispatcher_and_accepts_zero_idle_pool(self):
        rc, helper, result = self.run_fixture()
        self.assertEqual(rc, 0)
        self.assertEqual([sample['admission_allowed'] for sample in helper.resource_admission_samples],
                         [True, True, True, True])
        self.assertEqual(len(helper.resource_admission_samples), 4)
        self.assertTrue(all('observed_at' in sample for sample in helper.resource_admission_samples))
        self.assertEqual([row[1] for row in helper.commands], ['stop', 'start'])
        self.assertEqual(result['acceptance']['thread_runners'], 6)
        self.assertEqual(result['acceptance']['reviewer_pool_actual'], 0)
        self.assertEqual(result['acceptance']['pool_state'], 'WAITING_READY_TASK')
        self.assertEqual(result['tasks_posted'], 0)
        self.assertEqual(result['tasks_requeued'], 0)
        self.assertTrue(result['source_installed'])
        self.assertEqual(helper.pool_target.read_bytes(), helper.assets['owner_autonomy_pool.py'])
        self.assertEqual(helper.process_target.read_bytes(), helper.assets['owner_subagent_processes.py'])
        self.assertEqual(helper.mentor_target.read_bytes(), helper.assets['owner_dispatcher_mentor.py'])
        self.assertEqual(result['mentor_file_readback_sha256'], entry.digest(helper.assets['owner_dispatcher_mentor.py']))
        self.assertEqual(result['mentor_reload_director_pid'], result['acceptance']['director_pid'])
        self.assertEqual(result['chat_identity_before'], entry.CHAT)
        backup = helper.ROOT/'backup/owner_subagent_fresh_gate/1234'
        before_files = {
            'owner_subagent_dispatcher.py': helper.before,
            'owner_autonomy_pool.py': helper.before_pool,
            'owner_subagent_processes.py': helper.before_process,
            'owner_dispatcher_mentor.py': helper.before_mentor,
            'owner_native_subagents.json': entry.encoded(configuration()),
        }
        for name, raw in before_files.items():
            saved = backup/name
            self.assertEqual(saved.read_bytes(), raw)
            self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
        self.assertTrue(result['training_configuration_and_flags_preserved'])
        self.assertFalse((helper.STATE / 'OWNER_MAINTENANCE.flag').exists())

    def test_failed_new_start_rolls_back_exact_owned_files(self):
        rc, helper, result = self.run_fixture('start')
        self.assertEqual(rc, 2)
        self.assertEqual([row[1] for row in helper.commands], ['stop', 'start', 'start'])
        self.assertEqual(helper.target.read_bytes(), helper.before)
        self.assertEqual(helper.pool_target.read_bytes(), helper.before_pool)
        self.assertEqual(helper.process_target.read_bytes(), helper.before_process)
        self.assertEqual(helper.mentor_target.read_bytes(), helper.before_mentor)
        self.assertEqual(entry.digest(helper.config.read_bytes()), entry.OLD_CONFIG)
        self.assertTrue(result['rollback_verified'])
        self.assertFalse(result['source_installed'])
        self.assertTrue(result['admissions_reopened'])

    def test_foreign_edit_keeps_maintenance_without_overwrite_or_second_start(self):
        rc, helper, result = self.run_fixture('foreign')
        self.assertEqual(rc, 2)
        self.assertEqual([row[1] for row in helper.commands], ['stop', 'start'])
        self.assertEqual(helper.target.read_bytes(), b'concurrent foreign edit\n')
        self.assertTrue(result['maintenance_flag_retained'])
        self.assertFalse(result['admissions_reopened'])
        self.assertTrue((helper.STATE / 'OWNER_MAINTENANCE.flag').exists())

    def test_training_flag_change_rolls_back_without_clearing_training_flag(self):
        rc, helper, result = self.run_fixture(training_changed=True)
        self.assertEqual(rc, 2)
        self.assertEqual(result['error'], 'HOLD_SUBAGENT_FRESH_TRAINING_IDENTITY_CHANGED')
        self.assertTrue(result['rollback_verified'])
        self.assertEqual([row[1] for row in helper.commands], ['stop', 'start', 'stop', 'start'])
        self.assertFalse(result['training_flags_written'])

    def test_trainer_sharing_dispatcher_group_prevents_control(self):
        with tempfile.TemporaryDirectory() as folder:
            helper = FakeNative(Path(folder) / 'nox')
            snapshot = training()
            snapshot['process']['pgrp'] = helper.pid
            recovery = types.SimpleNamespace(owned_group=lambda pid: [helper.process(pid)])
            with self.assertRaisesRegex(RuntimeError, 'TRAINER_IN_DIRECTOR_GROUP'):
                entry.dispatcher_group(helper, recovery, snapshot)
            self.assertEqual(helper.commands, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
