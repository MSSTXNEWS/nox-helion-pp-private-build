"""Bounded installation/source-transition tests; no native control operations."""
import base64
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
spec = importlib.util.spec_from_file_location('qwen_media_entry_tests', HERE / 'owner_qwen_media_handoff_entry.py')
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_exact_current_dispatcher_addition_preserves_every_existing_binding(self):
        raw = Path('/tmp/nox_native_sources/nox_dispatcher_admitted_a409.py').read_bytes()
        self.assertEqual(M.digest(raw), 'a4097dae395f4289a7c67faa0047c0027dc128a9607f3f8189b4270bc5f7426b')
        anchor = b'if __name__ == "__main__":\n    main()'
        native = raw.replace(anchor, b'# NOX_NATIVE_SUBAGENTS_BIND_V1\nimport owner_subagent_dispatcher\nowner_subagent_dispatcher.bind_dispatcher(globals())\n\n' + anchor)
        self.assertEqual(M.digest(native), M.DISPATCHER_BEFORE)
        after = M.patch_dispatcher(native)
        self.assertEqual(after.replace(M.BINDING.encode(), b'', 1), native)
        self.assertLess(after.index(M.MARKER.encode()), after.index(b'# NOX_OWNER_TASK_LIFECYCLE_BIND_V1'))
        self.assertEqual(after.count(b'owner_subagent_dispatcher.bind_dispatcher(globals())'), 1)
        with self.assertRaisesRegex(RuntimeError, 'DISPATCHER_PREIMAGE'):
            M.patch_dispatcher(after)

    def test_completed_six_and_future_resume_configuration_are_explicit(self):
        context = {'request': '123', 'source_sha': 'a' * 40, 'receipt_sha256': 'b' * 64}
        six = M.configuration(context, 'c' * 64)
        self.assertTrue(six['enabled']); self.assertFalse(six['resume_training_after_media'])
        self.assertEqual(six['dependencies'], M.DEPS)
        later = M.configuration(context, 'c' * 64, resume_training_after_media=True)
        self.assertTrue(later['resume_training_after_media'])
        with self.assertRaisesRegex(RuntimeError, 'CONFIG_SCOPE'):
            M.configuration(context, 'c' * 64, resume_training_after_media=1)
        with self.assertRaisesRegex(RuntimeError, 'SEALED_CONTEXT'):
            M.configuration({**context, 'assumed_complete': True}, 'c' * 64)

    def test_exact_bundle_loads_only_reviewed_control_definitions(self):
        paths = {name: HERE / name for name in {M.ADAPTER, *M.DEPS, *M.CONTROLS}}
        paths.update({'owner_qwen_window_entry.py': Path('/tmp/nox_qwen_window_entry_4d5.py'),
            'owner_qwen_install_entry.py': Path('/tmp/nox_qwen_owner_qwen_install_entry.py'),
            'owner_subagent_install_entry.py': Path('/tmp/nox_subagent_review_b022334/owner_subagent_install_entry.py')})
        data = {name: base64.b64encode(path.read_bytes()).decode() for name, path in paths.items()}
        with patch.object(M, 'BUNDLE', data):
            assets = M.bundle()
            fresh = M.module('owner_subagent_fresh_install_entry.py', assets['owner_subagent_fresh_install_entry.py'])
            helper, recovery, candidate = fresh.load_helpers()
        self.assertEqual(helper.SERVICE, 'nox-dispatcher-t855u')
        self.assertEqual(M.digest(candidate), M.CONTROLS['owner_subagent_dispatcher_fresh.py'])
        self.assertTrue(callable(recovery.owned_group))

    def helpers(self):
        def atomic(path, raw):
            path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
        return types.SimpleNamespace(read=lambda path: path.read_bytes(), atomic=atomic)

    def test_rollback_refuses_foreign_target_before_restoring_anything(self):
        a, b = self.root / 'a.py', self.root / 'b.py'
        a.write_bytes(b'our a'); b.write_bytes(b'foreign b')
        with self.assertRaisesRegex(RuntimeError, 'ROLLBACK_FOREIGN_WRITE'):
            M.restore(self.helpers(), {a: b'old a', b: b'old b'},
                      {a: M.digest(b'our a'), b: M.digest(b'our b')}, self.root / 'backup')
        self.assertEqual(a.read_bytes(), b'our a'); self.assertEqual(b.read_bytes(), b'foreign b')

    def test_rollback_preserves_modes_and_archives_only_owned_new_files(self):
        old, new, missing = self.root / 'old.py', self.root / 'new.py', self.root / 'missing.py'
        old.write_bytes(b'our replacement'); new.write_bytes(b'our new')
        written = {old: M.digest(b'our replacement'), new: M.digest(b'our new'), missing: M.digest(b'not written')}
        M.restore(self.helpers(), {old: b'original', new: None, missing: None}, written,
                  self.root / 'backup', {old: 0o700, new: 0o644, missing: 0o644})
        self.assertEqual(old.read_bytes(), b'original'); self.assertEqual(old.stat().st_mode & 0o777, 0o700)
        self.assertFalse(new.exists()); self.assertFalse(missing.exists())
        archive = self.root / 'backup/failed_new' / str(new).lstrip('/')
        self.assertEqual(archive.read_bytes(), b'our new')

    def test_timed_out_stop_cannot_be_treated_as_an_untouched_running_controller(self):
        for state in ('STOPPING', 'STARTING', 'UNKNOWN'):
            with self.subTest(state=state), self.assertRaisesRegex(RuntimeError, 'ROLLBACK_CONTROLLER_UNSETTLED'):
                M.rollback_controller_plan(state, False)
        self.assertEqual(M.rollback_controller_plan('RUNNING', False), {'stop_first': False, 'restart': False})
        self.assertEqual(M.rollback_controller_plan('STOPPED', False), {'stop_first': False, 'restart': True})

    def test_idle_heartbeat_must_follow_maintenance_acquisition(self):
        folder = self.root / 'status'; folder.mkdir()
        path = folder / 'agents_t856u.json'
        value = {'n': 6, 'workers': [{'id': 'nox-agent-%02d' % i, 'current_task': None, 'status': 'idle'} for i in range(1, 7)],
                 'native_subexecutors': {'director': {'pid': 7, 'process_starttime': 99}}}
        path.write_text(json.dumps(value)); stamp = path.stat().st_mtime
        h = types.SimpleNamespace(read=lambda path, limit: path.read_bytes(), service=lambda: {'state': 'RUNNING', 'pid': 7},
                                  process=lambda pid: {'starttime': 99})
        with patch.object(M, 'ROOT', self.root):
            with self.assertRaisesRegex(RuntimeError, 'FRESH_IDLE_WORKERS'):
                M.workers(h, stamp + .01)
            self.assertEqual(M.workers(h, stamp - .01)['busy'], 0)
            value['workers'][2]['current_task'] = {'id': 'active-task'}
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(RuntimeError, 'FRESH_IDLE_WORKERS'):
                M.workers(h, stamp - .01)

    def test_blocked_projection_exports_no_prompt_or_raw_result(self):
        state = self.root / 'state'; jobs = state / 'media/jobs'; jobs.mkdir(parents=True)
        jid = M.JOBS[0]
        value = {'schema': 'NOX_OWNER_MEDIA_JOB_V1', 'id': jid, 'state': 'BLOCKED',
                 'reason': 'HOLD_RESUMABLE_TRAINER_WRAPPER_REQUIRED', 'request': {'prompt': 'PRIVATE_FIXTURE'},
                 'outputs': [], 'secret': 'PRIVATE_FIXTURE'}
        (jobs / (jid + '.json')).write_text(json.dumps(value))
        row = {'status': 'blocked', 'owner_plan_id': 'a' * 24, 'owner_claim': {'nonce': 'private'},
               'result': {'state': 'HOLD_EXACT_CAUSE', 'raw_error': 'PRIVATE_FIXTURE'}}
        h = types.SimpleNamespace(read=lambda path, limit: path.read_bytes(),
                                 queue_state=lambda: {'tasks': {'owner.media.' + jid: row}})
        with patch.object(M, 'STATE', state):
            result = M.blocked_projection(h)
        self.assertNotIn('PRIVATE_FIXTURE', json.dumps(result))
        self.assertFalse(result['queue_file_edited']); self.assertEqual(result['tasks_requeued'], 0)
        self.assertEqual(result['jobs'][0]['media_job']['failure_reason'], 'HOLD_RESUMABLE_TRAINER_WRAPPER_REQUIRED')


if __name__ == '__main__':
    unittest.main()
