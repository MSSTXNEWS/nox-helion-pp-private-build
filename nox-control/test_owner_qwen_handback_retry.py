"""Real inherited queue-race regression and bounded single-task retry gates."""
import ast
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).parent


def load(name):
    spec = importlib.util.spec_from_file_location('_handback_test_' + name.removesuffix('.py'), HERE / name)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result); return result


O = load('owner_qwen_handback_retry.py')
E = load('owner_qwen_handback_retry_entry.py')


class QueueRaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base = load('owner_media_training_handoff.py')
        self.assertEqual(hashlib.sha256((HERE / 'owner_media_training_handoff.py').read_bytes()).hexdigest(),
                         '36db3c363ffddfc144c6127e1a9407132bbe39d38996233bf3dd64e5b3cb6ec8')
        self.base.ROOT = Path(self.tmp.name); self.base.TASK_SOURCE = 'owner_qwen_media_handoff'
        self.queue = self.base.ROOT / 'state/dispatcher/state.json'; self.queue.parent.mkdir(parents=True)
        self.task = {'id': 'owner.media.resume.' + '9' * 32, 'handler': 'owner_media_resume',
            'source': 'owner_qwen_media_handoff', 'class': 'training', 'locks': ['gpu1'], 'deps': [],
            'params': {'job_id': '9' * 32}, 'status': 'running', 'claimed_by': 'nox-agent-01',
            'owner_claim_epoch': time.time(), 'owner_claim': {'worker': 'nox-agent-01', 'pid': os.getpid(),
            'nonce': '1' * 24, 'at': '2026-11-16T00:00:00Z'}}
        self.row = {'tasks': {self.task['id']: self.task}, 'unrelated_tick': 0}
        self.queue.write_text(json.dumps(self.row))
        self.handback = object.__new__(self.base.Handback); self.handback.ns = {'STATE': self.queue}
        self.original_read = self.base.read; self.original_fstat = os.fstat
        self.calls = 0; self.replacements = 0
        self.queue_patch = patch.object(O, 'QUEUE', self.queue); self.queue_patch.start(); self.addCleanup(self.queue_patch.stop)
        self.sleep_patch = patch.object(O.time, 'sleep'); self.sleep_patch.start(); self.addCleanup(self.sleep_patch.stop)

    def atomic_at_second_fstat(self, path, *, repeat=False, changed_claim=False):
        def hooked(fd):
            saved = self.original_fstat(fd); self.calls += 1
            if self.calls % 2 == 0 and (repeat or self.replacements == 0):
                row = copy.deepcopy(self.row); row['unrelated_tick'] = self.replacements + 1
                if changed_claim: row['tasks'][self.task['id']]['owner_claim']['nonce'] = '2' * 24
                temporary = path.with_name('next-snapshot.json'); temporary.write_text(json.dumps(row))
                os.replace(temporary, path); self.replacements += 1
            return saved
        return hooked

    def bind(self): self.base.read = O.queue_reader(self.original_read, self.base.HandoffHold)

    def test_exact_original_claim_rejects_unrelated_atomic_tick(self):
        with patch.object(os, 'fstat', self.atomic_at_second_fstat(self.queue)):
            with self.assertRaisesRegex(self.base.HandoffHold, '^HOLD_MEDIA_HANDBACK_FILE_CHANGED$'):
                self.handback.claim(self.task)
        self.assertEqual(json.loads(self.queue.read_text())['tasks'][self.task['id']], self.task)

    def test_bounded_retry_rechecks_complete_persisted_claim(self):
        self.bind()
        with patch.object(os, 'fstat', self.atomic_at_second_fstat(self.queue)):
            self.assertEqual(self.handback.claim(self.task), self.task['owner_claim'])
        self.assertEqual(self.calls, 4)

    def test_changed_nonce_is_not_authorized_by_successful_reread(self):
        self.bind()
        with patch.object(os, 'fstat', self.atomic_at_second_fstat(self.queue, changed_claim=True)):
            with self.assertRaisesRegex(self.base.HandoffHold, '^HOLD_MEDIA_HANDBACK_PERSISTED_CLAIM$'):
                self.handback.claim(self.task)

    def test_continuing_race_returns_wait_after_exactly_three_reads(self):
        self.bind()
        with patch.object(os, 'fstat', self.atomic_at_second_fstat(self.queue, repeat=True)):
            with self.assertRaisesRegex(self.base.HandoffHold, '^WAIT_QUEUE_SNAPSHOT_CHANGED$'):
                self.handback.claim(self.task)
        self.assertEqual((self.replacements, self.calls), (3, 6))

    def test_other_path_error_and_queue_symlink_remain_hold(self):
        other = self.base.ROOT / 'immutable.json'; other.write_text(json.dumps(self.row)); self.bind()
        with patch.object(os, 'fstat', self.atomic_at_second_fstat(other)):
            with self.assertRaisesRegex(self.base.HandoffHold, '^HOLD_MEDIA_HANDBACK_FILE_CHANGED$'):
                self.base.read(other)
        self.assertEqual(self.calls, 2)
        self.queue.unlink(); self.queue.symlink_to(other)
        with self.assertRaisesRegex(self.base.HandoffHold, '^HOLD_MEDIA_HANDBACK_SYMLINK$'):
            self.handback.claim(self.task)

    def test_queue_schema_failure_is_not_transient(self):
        self.bind(); self.queue.write_text('{"tasks":{},"tasks":{}}')
        with self.assertRaisesRegex(self.base.HandoffHold, '^HOLD_MEDIA_HANDBACK_DUPLICATE_KEY$'):
            self.handback.claim(self.task)


class GuardTests(unittest.TestCase):
    def test_only_three_freshness_codes_become_wait(self):
        hold = type('GuardHold', (RuntimeError,), {})
        for code in O.FRESHNESS:
            wrapped = O.guard_admission(Mock(side_effect=hold(code)), hold)
            with self.assertRaisesRegex(hold, '^' + code.replace('HOLD_', 'WAIT_', 1) + '$'): wrapped()
        for code in ('HOLD_QWEN_GUARD_STATE_SCOPE', 'HOLD_QWEN_GUARD_STATE_NOT_PERMISSIVE',
                     'HOLD_QWEN_GUARD_RESUME_MARGIN_OR_QUALITY', 'HOLD_QWEN_GUARD_GOAL_ALREADY_COMPLETE',
                     'HOLD_QWEN_GUARD_SOURCE_PIN', 'HOLD_QWEN_GUARD_DISK_LOW', 'WAIT_OWNER_STOP'):
            error = hold(code); wrapped = O.guard_admission(Mock(side_effect=error), hold)
            with self.assertRaises(hold) as caught: wrapped()
            self.assertIs(caught.exception, error)
        proof = {'state': 'FRESH_GUARD_ADMITS_RESUME'}
        self.assertIs(O.guard_admission(lambda: proof, hold)(), proof)

    def test_instance_binding_changes_real_inherited_global_read_and_guard(self):
        base = load('owner_media_training_handoff.py'); handback = object.__new__(base.Handback)
        handback.source_pin = O.PINS[O.CORE]
        class Reader:
            def admission(self): return {'state': 'FRESH_GUARD_ADMITS_RESUME'}
            def resource_gate(self): return self.admission()
            def release_flags(self, *args): return self.admission()
        reader = Reader(); reader.handback = handback
        handback.resource_gate, handback.release_flags = reader.resource_gate, reader.release_flags
        core = types.SimpleNamespace(__file__=str(O.CORE), BOUND=handback)
        mod = types.SimpleNamespace(__file__=str(O.READER), BOUND=reader, GuardHold=RuntimeError)
        ns = {'WORKERS': 6, 'STATE': O.QUEUE, '_owner_media_inbox_fair_bound': True,
              '_owner_qwen_media_handoff_bound': True, '_owner_qwen_media_guard_bound': True,
              'HANDLERS': {'owner_media_resume': handback.run}}
        original = base.read
        with patch.object(O, 'BOUND', None), patch.object(O, 'checked'), patch.object(O, 'BASE', HERE / 'owner_media_training_handoff.py'):
            O.bind_dispatcher(ns, core, mod)
            self.assertIs(base.read, O.BOUND['read']); self.assertIsNot(base.read, original)
            self.assertIs(handback.claim.__func__.__globals__['read'], O.BOUND['read'])
            self.assertEqual(handback.resource_gate(), {'state': 'FRESH_GUARD_ADMITS_RESUME'})
            with self.assertRaisesRegex(RuntimeError, 'BIND_ORDER'): O.bind_dispatcher(ns, core, mod)


class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prior = load('test_owner_media_inbox_fair.py')
        cls.bundled = prior.bundle()
        cls.bundled.update({name: base64.b64encode((HERE / name).read_bytes()).decode() for name in E.PINS})
        with patch.object(E, 'BUNDLE', cls.bundled):
            cls.assets, cls.fair, cls.installer, cls.base, cls.fresh, cls.h, cls.recovery, cls.guard, cls.status = E.prepared()

    def target(self):
        return {'id': E.TASK, 'handler': 'owner_media_resume', 'source': 'owner_qwen_media_handoff', 'class': 'training',
                'params': {'job_id': E.JOB}, 'deps': [], 'locks': ['gpu1'], 'status': 'blocked', 'priority': 0,
                'retries': 1, 'max_retries': 1, 'timeout_sec': 180,
                'owner_claim': {'pid': 724331, 'nonce': 'a' * 24, 'worker': 'nox-agent-01', 'at': '2026-11-16'},
                'owner_claim_epoch': 1234, 'claimed_by': 'nox-agent-01', 'next_try': 1250,
                'result': {'state': 'HOLD_MEDIA_HANDBACK_FILE_CHANGED', 'verified': False}, 'note': 'private fixture',
                'started_at': '2026-11-16', 'mentor': {'state': 'private fixture'}}

    def test_exact_closure_and_dispatcher_insert(self):
        self.assertEqual(len(self.assets), 18)
        raw = Path('/tmp/nox_native_sources/nox_dispatcher_admitted_a409.py').read_bytes()
        anchor = b'if __name__ == "__main__":\n    main()'
        raw = raw.replace(anchor, b'# NOX_NATIVE_SUBAGENTS_BIND_V1\nimport owner_subagent_dispatcher\nowner_subagent_dispatcher.bind_dispatcher(globals())\n\n' + anchor)
        before = self.fair.patch_dispatcher(self.installer.patch_dispatcher(self.base.patch_dispatcher(raw), self.base))
        self.assertEqual(E.digest(before), E.BEFORE)
        after = E.patch_dispatcher(before)
        self.assertEqual(after.replace(E.BINDING.encode(), b'', 1), before)
        self.assertLess(after.index(b'# NOX_MEDIA_INBOX_FAIR_BIND_V1'), after.index(E.MARKER.encode()))
        self.assertLess(after.index(E.MARKER.encode()), after.index(b'# NOX_OWNER_TASK_LIFECYCLE_BIND_V1'))
        with self.assertRaisesRegex(RuntimeError, 'DISPATCHER_PREIMAGE'): E.patch_dispatcher(after)
        with patch.object(E, 'BUNDLE', dict(self.bundled, **{E.OVERLAY: base64.b64encode(b'foreign').decode()})):
            with self.assertRaisesRegex(RuntimeError, 'BUNDLE_PIN'): E.prepared()

    def test_requeue_archives_identity_preserves_retry_count_and_never_replays_claim(self):
        old = self.target(); saved = copy.deepcopy(old); pin = E.digest(E.canonical(old['owner_claim']))
        with patch.object(E, 'CLAIM_SHA', pin): new = E.pending_task(old, '42', 'f' * 40, 'c' * 64)
        self.assertEqual(old, saved); self.assertEqual(new['status'], 'pending'); self.assertEqual(new['retries'], 1)
        self.assertFalse(E.EXECUTION_FIELDS & new.keys())
        for key in ('id', 'handler', 'source', 'params', 'deps', 'locks', 'max_retries', 'timeout_sec'):
            self.assertEqual(old[key], new[key])
        self.assertEqual(new['owner_handback_repair']['archived_task_sha256'], 'c' * 64)
        with patch.object(E, 'CLAIM_SHA', pin), self.assertRaisesRegex(RuntimeError, 'TARGET_SCOPE'):
            E.pending_task(new, '42', 'f' * 40, 'c' * 64)

    def test_foreign_or_already_started_target_never_requeued(self):
        old = self.target(); pin = E.digest(E.canonical(old['owner_claim']))
        changes = [('status', 'running'), ('retries', 2), ('handler', 'owner_media'), ('locks', []),
                   ('result', {'state': 'HOLD_QUALITY_FAILURE', 'verified': False}), ('owner_claim', {'pid': 99})]
        for key, value in changes:
            candidate = copy.deepcopy(old); candidate[key] = value
            with patch.object(E, 'CLAIM_SHA', pin), self.assertRaisesRegex(RuntimeError, 'TARGET_SCOPE'):
                E.pending_task(candidate, '42', 'f' * 40, 'c' * 64)

    def test_exact_native_pick_always_reissues_claim_and_wait_does_not_increment_retries(self):
        raw = Path('/tmp/nox_native_sources/nox_dispatcher_admitted_a409.py').read_bytes()
        nodes = [n for n in ast.parse(raw).body if isinstance(n, ast.FunctionDef) and n.name in ('owner_claim_ready', 'run_one')]
        import threading
        task = self.target(); old_claim = task['owner_claim']; task['status'] = 'pending'
        ns = {'_qlock': threading.RLock(), 'ingest_architect_patch': lambda _: None, 'ingest_owner_orders': lambda _: None,
              'pick_ready': lambda *_: task, 'acquire_locks': lambda _: True, 'save_state': lambda _: None,
              'time': time, 'os': os, 'now_msk': lambda: '2026-11-16', 'HANDLERS': {'owner_media_resume': lambda _: ('wait', 'WAIT_QUEUE_SNAPSHOT_CHANGED')},
              'owner_mentor': types.SimpleNamespace(redact=str), 'ev': lambda *a, **k: None,
              'release_locks': lambda _: None, 'learn': Mock(), 'log': Mock()}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<exact-native-claim>', 'exec'), ns)
        ns['owner_claim_ready']({'tasks': {E.TASK: task}}, set(), 'nox-agent-02')
        self.assertNotEqual(task['owner_claim'], old_claim); self.assertEqual(task['owner_claim']['pid'], os.getpid())
        ns['run_one']({'tasks': {E.TASK: task}}, task)
        self.assertEqual(task['status'], 'pending'); self.assertEqual(task['retries'], 1); ns['learn'].assert_not_called()

    def test_checkpoint_replacement_is_rejected_before_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); cp = root / 'checkpoint'; cp.mkdir(); (cp / 'adapter').write_bytes(b'abc')
            (cp / 'checkpoint_manifest.json').write_bytes(b'{}')
            ctx = {'output': root}; manifest = {'directory': 'checkpoint', 'files_sha256': {'adapter': 'a' * 64}}
            before = E.checkpoint_identities(ctx, manifest)
            E.preserve_checkpoints(ctx, [manifest], [before])
            (cp / 'adapter').write_bytes(b'abd')
            with self.assertRaisesRegex(RuntimeError, 'CHECKPOINT_IDENTITY_CHANGED'):
                E.preserve_checkpoints(ctx, [manifest], [before])

    def test_unsettled_dispatcher_blocks_restore_and_unmodified_running_needs_no_restart(self):
        for state in ('STOPPING', 'STARTING', 'UNKNOWN'):
            with self.assertRaisesRegex(RuntimeError, 'ROLLBACK_CONTROLLER_UNSETTLED'):
                self.base.rollback_controller_plan(state, True)
        self.assertEqual(self.base.rollback_controller_plan('RUNNING', False), {'stop_first': False, 'restart': False})
        self.assertEqual(self.base.rollback_controller_plan('RUNNING', True), {'stop_first': True, 'restart': True})

    def test_smoke_is_import_only_and_private_stderr_is_never_returned(self):
        compile(E.SMOKE, '<smoke>', 'exec')
        result = types.SimpleNamespace(returncode=2, stdout=b'{"state":"HOLD"}', stderr=b'PRIVATE_FIXTURE')
        with patch.object(E.subprocess, 'run', return_value=result), self.assertRaisesRegex(RuntimeError, '^HOLD_QWEN_HANDBACK_REPAIR_SMOKE_FAILED$'):
            E.smoke('/usr/bin/python3')


if __name__ == '__main__':
    unittest.main()
