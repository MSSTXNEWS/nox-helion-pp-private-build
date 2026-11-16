"""Local metadata/privacy fixtures; no native process, payload or network call."""
import ast
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import time
import types
import unittest
from contextlib import redirect_stdout
from unittest.mock import Mock, patch


HERE = Path(__file__).parent


def load_file(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


o = load_file('successor_observe_v2_test_module', 'owner_qwen_successor_observe_v2.py')
fixtures = load_file('successor_observe_v2_shared_fixtures', 'test_owner_qwen_execution_successor.py')
s = fixtures.m


class MetadataTests(fixtures.Fixture):
    def setUp(self):
        super().setUp()
        self.ctx['context'] = self.ref
        self.desc['activation_issuer_sha256'] = o.INSTALLER_SHA
        self.live = {'service': {'state': 'RUNNING', 'pid': self.pid['pid']}, 'process_identity': self.pid}
        self.watcher = dict(self.pid, pid=self.pid['pid'] + 1, start_ticks=self.pid['start_ticks'] + 1)

    def progress(self, *, good=26, current=True, who=None, state='NATIVE_STUDENT_UPDATE_OBSERVED', permission=True):
        who = self.pid if who is None else who
        row = {'state': state, 'successful_optimizer_steps': good, 'attempted_steps': good,
               'skipped_steps': 0, 'holdout_evaluated_successful_total': 25,
               'loss': 1.2, 'time': time.time(), 'pid': who['pid'], 'process_identity': who,
               'adapter_tensor_sha256': 'a' * 64, 'optimizer_permission_verified': permission,
               'execution_binding': s.execution_binding(self.ctx) if current else s.predecessor_binding()}
        self.private(self.ctx['output'] / 'owner_progress.json', s.encode(row))
        return row

    def ready(self):
        row = {'schema': o.JOURNALS['watcher_ready.json'], 'execution_revision': self.ref,
               'process_identity': self.watcher, 'watcher_source_sha256': self.desc['activation_watcher_sha256'],
               'verifier_sha256': o.SHARED_SHA, 'issuer_source_sha256': o.INSTALLER_SHA,
               'armed_at': self.now - 10, 'start_capability': False}
        self.private(self.folder / 'watcher_ready.json', s.encode(row))
        return row

    def start(self):
        ready = self.ready()
        row = {'schema': o.JOURNALS['start_receipt.json'], 'execution_revision': self.ref,
               'start_command_issued': True, 'start_command_returncode': 0, 'trainer': self.live,
               'watcher_ready_sha256': s.digest(s.encode(ready)), 'started_at': self.now - 8,
               'sampled_at': self.now - 7}
        self.private(self.folder / 'start_receipt.json', s.encode(row))
        return row

    def pointer(self, manifest, raw):
        self.private(self.ctx['output'] / 'latest_checkpoint.json', s.encode({
            'directory': manifest['directory'], 'manifest_sha256': s.digest(raw)}))

    def test_historical_progress_cannot_be_current_or_new_optimization(self):
        self.progress(good=25, current=False, who=self.old_pid,
                      state='NATIVE_EXECUTION_EVALUATION_CHECKPOINTED', permission=False)
        value = o.progress_metadata(s, self.ctx, self.live)
        self.assertTrue(value['historical_predecessor'])
        self.assertFalse(value['current_execution'])
        self.assertFalse(value['current_process_bound'])
        self.assertFalse(value['current_process_optimizer_permission_reported'])
        self.assertEqual(value['new_current_process_updates_reported'], 0)
        self.assertEqual(o.observed_state(self.live, {'active': False}, value), 'RUNNING_BOOTSTRAP_OR_PERMISSION_PENDING')

    def test_current_update_is_reported_only_for_live_admitted_process(self):
        self.progress()
        for live in (dict(self.live, process_identity=self.old_pid),
                     {'service': {'state': 'FATAL', 'pid': None}, 'process_identity': None}):
            with self.subTest(live=live):
                value = o.progress_metadata(s, self.ctx, live)
                self.assertFalse(value['current_process_optimizer_permission_reported'])
                self.assertEqual(value['new_current_process_updates_reported'], 0)
        value = o.progress_metadata(s, self.ctx, self.live)
        self.assertTrue(value['current_process_bound'])
        self.assertTrue(value['current_process_optimizer_permission_reported'])
        self.assertEqual(value['new_current_process_updates_reported'], 1)
        self.assertFalse(value['full_checkpoint_files_verified'])
        self.assertEqual(o.observed_state(self.live, {'active': False}, value), 'RUNNING_BOOTSTRAP_OR_PERMISSION_PENDING')
        self.assertEqual(o.observed_state(self.live, {'active': True}, value), 'RUNNING_CURRENT_PROCESS_UPDATE_PROGRESS_RECORDED')

    def test_same_counter_fresh_evaluation_is_not_optimizer_permission(self):
        self.progress(good=25, state='NATIVE_EXECUTION_EVALUATION_CHECKPOINTED', permission=False)
        value = o.progress_metadata(s, self.ctx, self.live)
        self.assertTrue(value['current_process_bound'])
        self.assertFalse(value['current_process_optimizer_permission_reported'])
        self.assertEqual(value['new_current_process_updates_reported'], 0)

    def test_progress_rejects_foreign_binding_nonfinite_and_future_record(self):
        for change in (lambda row: row['execution_binding'].update(request='999'),
                       lambda row: row.update(time=time.time() + 100),
                       lambda row: row.update(time=self.desc['created_at'] - 1),
                       lambda row: row.update(attempted_steps=27),
                       lambda row: row.update(loss=float('nan'))):
            row = self.progress(); change(row)
            raw = json.dumps(row, allow_nan=True).encode()
            self.private(self.ctx['output'] / 'owner_progress.json', raw)
            with self.assertRaises((o.Hold, s.Hold)):
                o.progress_metadata(s, self.ctx, self.live)

    def test_ready_start_and_nullable_result_have_typed_hash_links(self):
        start = self.start()
        ready = o.journal_metadata(s, self.ctx, 'watcher_ready.json')
        observed = o.journal_metadata(s, self.ctx, 'start_receipt.json')
        self.assertEqual(observed['watcher_ready_sha256'], ready['sha256'])
        result = {'schema': o.JOURNALS['watcher_result.json'], 'execution_revision': self.ref,
                  'process_identity': self.watcher, 'watcher_source_sha256': self.desc['activation_watcher_sha256'],
                  'finished_at': time.time(), 'state': 'HOLD_QWEN_SUCCESSOR_WATCHER_DEADLINE',
                  'active': None, 'optimizer_permission_issued': None,
                  'activation_observation': 'NOT_RECHECKED_AFTER_EXCEPTION',
                  'start_receipt_sha256': s.digest(s.encode(start)),
                  'private_body': 'MUST_NOT_EXPORT'}
        self.private(self.folder / 'watcher_result.json', s.encode(result))
        value = o.journal_metadata(s, self.ctx, 'watcher_result.json')
        self.assertIsNone(value['active'])
        self.assertIsNone(value['optimizer_permission_issued'])
        self.assertEqual(value['activation_observation'], 'NOT_RECHECKED_AFTER_EXCEPTION')
        self.assertNotIn('MUST_NOT_EXPORT', json.dumps(value))

    def test_journal_absence_and_partial_json_are_explicit_without_guessing(self):
        self.assertEqual(o.journal_metadata(s, self.ctx, 'start_receipt.json'), {'present': False, 'state': 'ABSENT'})
        self.private(self.folder / 'start_receipt.json', b'{"private":')
        result = o.optional(lambda: o.journal_metadata(s, self.ctx, 'start_receipt.json'))
        self.assertEqual(result, {'state': 'UNVERIFIED', 'reason': 'HOLD_QWEN_SUCCESSOR_OBSERVE_UNVERIFIED'})
        with self.assertRaises(o.Hold):
            o.journal_metadata(s, self.ctx, '../other.json')

    def test_foreign_ready_ref_source_or_start_hash_cannot_be_accepted(self):
        for change in (lambda row: row['execution_revision'].update(request='999'),
                       lambda row: row.update(verifier_sha256='0' * 64),
                       lambda row: row.update(start_capability=True)):
            self.start(); ready, _ = s.document(self.folder / 'watcher_ready.json')
            change(ready); self.private(self.folder / 'watcher_ready.json', s.encode(ready))
            with self.assertRaises(o.Hold):
                o.journal_metadata(s, self.ctx, 'start_receipt.json')
        start = self.start(); start['watcher_ready_sha256'] = '0' * 64
        self.private(self.folder / 'start_receipt.json', s.encode(start))
        with self.assertRaises(o.Hold):
            o.journal_metadata(s, self.ctx, 'start_receipt.json')

    def test_checkpoint_reads_real_shared_metadata_but_never_tensor_payloads(self):
        manifest, state, raw, _ = self.fresh(good=30)
        self.pointer(manifest, raw)
        real_read = s.read; opened = []
        allowed = {'checkpoint_manifest.json', 'student_state.json', 'lineage.json', 'latest_checkpoint.json'}
        def read_metadata(path, *args, **kwargs):
            opened.append(Path(path).name)
            self.assertIn(Path(path).name, allowed, 'unexpected tensor/optimizer payload read')
            return real_read(path, *args, **kwargs)
        with patch.object(s, 'read', side_effect=read_metadata):
            value = o.checkpoint_metadata(s, self.ctx)
        self.assertTrue(value['current_execution'])
        self.assertFalse(value['initial_anchor'])
        self.assertEqual(value['successful_total'], 30)
        self.assertEqual(value['evaluated_at_update'], 25)
        self.assertEqual(value['new_saved_updates_recorded'], 5)
        self.assertEqual(value['recorded_files'], 10)
        self.assertTrue(value['metadata_hashes_verified'])
        self.assertFalse(value['full_checkpoint_files_verified'])
        self.assertFalse(value['new_optimizer_updates_full_verified'])
        self.assertGreater(len(opened), 3)

    def test_predecessor_checkpoint_remains_historical_and_pointer_race_is_not_promoted(self):
        raw = s.read(s.OUTPUT / s.ANCHOR['directory'] / 'checkpoint_manifest.json')
        self.pointer(self.predecessor_manifest, raw)
        value = o.checkpoint_metadata(s, self.ctx)
        self.assertTrue(value['initial_anchor'])
        self.assertFalse(value['current_execution'])
        self.assertEqual(value['new_saved_updates_recorded'], 0)
        real_read = s.read; seen = 0
        def changing_pointer(path, *args, **kwargs):
            nonlocal seen
            result = real_read(path, *args, **kwargs)
            if Path(path).name == 'latest_checkpoint.json':
                seen += 1
                if seen > 1: return result + b' '
            return result
        with patch.object(s, 'read', side_effect=changing_pointer):
            with self.assertRaisesRegex(o.Hold, 'CHECKPOINT_CHANGED'):
                o.checkpoint_metadata(s, self.ctx)

    def test_checkpoint_does_not_export_untyped_process_dictionary(self):
        manifest, _, _, _ = self.fresh()
        manifest['process_identity'] = dict(self.pid, private_text='MUST_NOT_EXPORT')
        raw = s.encode(manifest)
        self.private(s.OUTPUT / manifest['directory'] / 'checkpoint_manifest.json', raw)
        self.pointer(manifest, raw)
        result = o.optional(lambda: o.checkpoint_metadata(s, self.ctx))
        self.assertEqual(result['state'], 'UNVERIFIED')
        self.assertNotIn('MUST_NOT_EXPORT', json.dumps(result))

    def test_pointer_and_manifest_cannot_refer_to_different_directories(self):
        manifest, _, raw, _ = self.fresh()
        other = 'checkpoint-u00000025-a00000025-g00000000000000000901'
        (s.OUTPUT / other).mkdir()
        self.private(s.OUTPUT / other / 'checkpoint_manifest.json', raw)
        self.private(s.OUTPUT / 'latest_checkpoint.json', s.encode({
            'directory': other, 'manifest_sha256': s.digest(raw)}))
        with self.assertRaisesRegex(o.Hold, 'CHECKPOINT_DIRECTORY'):
            o.checkpoint_metadata(s, self.ctx)


class ScopeTests(unittest.TestCase):
    def test_telemetry_is_exact_prior_sanitizer_and_omits_text_urls_and_secrets(self):
        old = ast.parse((HERE / 'owner_qwen_transport_budget_observe.py').read_text())
        new = ast.parse((HERE / 'owner_qwen_successor_observe_v2.py').read_text())
        for name in ('transport_events', 'transport_telemetry'):
            before = next(node for node in old.body if isinstance(node, ast.FunctionDef) and node.name == name)
            after = next(node for node in new.body if isinstance(node, ast.FunctionDef) and node.name == name)
            self.assertEqual(ast.dump(before, include_attributes=False), ast.dump(after, include_attributes=False))
        row = {'state': 'PINNED_PUBLIC_BASE_STAGING', 'transport_version': 'NOX_QWEN_PUBLIC_TRANSPORT_V1',
               'stage': 'READ', 'attempt': 1, 'bytes': 1024, 'total': 100000, 'committed_offset': 1024,
               'http_status': 206, 'exception_type': 'TimeoutError', 'url': 'https://PRIVATE/token',
               'headers': {'Authorization': 'MUST_NOT_EXPORT'}, 'exception_text': 'PRIVATE'}
        events = o.transport_events(json.dumps(row).encode() + b'\n')
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['committed_offset'], 1024)
        self.assertNotIn('PRIVATE', json.dumps(events))
        self.assertNotIn('MUST_NOT_EXPORT', json.dumps(events))

    def test_source_reader_rejects_hash_drift_and_never_executes_unverified_source(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'source.py'; raw = b'raise RuntimeError("must not run")\n'
            path.write_bytes(raw); path.chmod(0o644)
            with patch.object(o, 'OWNER_UID', os.geteuid()):
                self.assertEqual(o.source(path, hashlib.sha256(raw).hexdigest()), raw)
                with self.assertRaises(o.Hold):o.source(path, '0' * 64)
                path.chmod(0o666)
                with self.assertRaises(o.Hold):o.source(path, hashlib.sha256(raw).hexdigest())

    def test_deadline_bypasses_optional_and_main_reports_only_safe_category(self):
        def interrupted():raise o.Deadline()
        with self.assertRaises(o.Deadline):o.optional(interrupted)
        output = io.StringIO()
        with patch.object(o, 'observe', side_effect=o.Deadline()), redirect_stdout(output):
            self.assertEqual(o.main(), 2)
        rows = output.getvalue().splitlines()
        value = json.loads(rows[0].removeprefix(o.PREFIX))['data']
        self.assertEqual(value['reason'], 'HOLD_QWEN_SUCCESSOR_OBSERVE_DEADLINE')
        self.assertFalse(value['services_or_flags_modified'])
        self.assertFalse(value['full_checkpoint_files_verified'])
        self.assertEqual(rows[-1], 'NOX_MAINT_REPAIR_COMPLETE=false')
        self.assertEqual(o.safe(RuntimeError('private token /path')), 'HOLD_QWEN_SUCCESSOR_OBSERVE_UNVERIFIED')

    def test_top_level_rechecks_activation_and_invalidates_changed_process(self):
        ref = {'request': '90001', 'source_sha': 'a' * 40, 'receipt_sha256': 'b' * 64}
        ctx = {'context': ref, 'execution': {'descriptor': {'activation_issuer_sha256': o.INSTALLER_SHA}}}
        before = {'service': {'state': 'RUNNING', 'pid': 11}, 'process_identity': {'pid': 11}}
        after = {'service': {'state': 'FATAL', 'pid': None}, 'process_identity': None}
        shared = types.SimpleNamespace(current_context=Mock(return_value=ctx),
            activation_status=Mock(side_effect=[{'active': False}, {'active': True, 'permit_sha256': 'f' * 64}]),
            execution_binding=Mock(return_value={'request': '90001'}), STATE=Path('/no-such-observer-state'))
        core = types.SimpleNamespace(protected=Mock(), trainer=Mock(side_effect=[before, after]))
        progress = {'current_process_bound': True, 'current_process_optimizer_permission_reported': True,
                    'new_current_process_updates_reported': 1}
        with patch.multiple(o, source=Mock(return_value=b''), load=Mock(side_effect=[shared, core]),
                journal_metadata=Mock(return_value={'present': False}), checkpoint_metadata=Mock(return_value={}),
                progress_metadata=Mock(return_value=progress), guard_metadata=Mock(return_value={}),
                transport_telemetry=Mock(return_value={}), chat_identity=Mock(return_value={}), health=Mock(return_value={})):
            value = o.observe()
        self.assertEqual(shared.activation_status.call_count, 2)
        self.assertTrue(value['activation']['active'])
        self.assertEqual(value['state'], 'TRAINER_CHANGED_DURING_OBSERVATION')
        self.assertFalse(value['progress']['current_process_bound'])
        self.assertEqual(value['progress']['new_current_process_updates_reported'], 0)
        self.assertFalse(value['full_checkpoint_files_verified'])

    def test_fixed_health_requests_do_not_follow_redirects_or_read_bodies(self):
        responses = []
        class Response:
            status = 200
            def __enter__(self):return self
            def __exit__(self, *_):pass
            def read(self, *_):raise AssertionError('health response body must not be read')
        def open_fixed(url, timeout):
            self.assertEqual(timeout, 2); responses.append(url); return Response()
        handlers = []
        def build(*items):handlers.extend(items); return types.SimpleNamespace(open=open_fixed)
        with patch.object(o.urllib.request, 'build_opener', side_effect=build):
            self.assertEqual(o.health(), {'8080': 200, '8081': 200, '8082': 200})
        self.assertEqual(responses, ['http://127.0.0.1:8080/health', 'http://127.0.0.1:8081/health', 'http://127.0.0.1:8082/health'])
        redirect = next(item for item in handlers if isinstance(item, o.urllib.request.HTTPRedirectHandler))
        self.assertIsNone(redirect.redirect_request(None, None, 302, '', {}, 'https://external.invalid'))

    def test_no_write_control_model_or_full_checkpoint_call_in_observer(self):
        tree = ast.parse((HERE / 'owner_qwen_successor_observe_v2.py').read_text())
        forbidden = {'write_bytes', 'write_text', 'chmod', 'unlink', 'replace', 'rename', 'Popen', 'run',
                     'full_checkpoint', 'finalize_same_process', 'owned_pause', 'tick', 'create', 'atomic_json', 'snapshot'}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                self.assertNotIn(node.func.attr, forbidden)
        self.assertEqual(hashlib.sha256((HERE / 'owner_qwen_execution_successor.py').read_bytes()).hexdigest(), o.SHARED_SHA)
        self.assertEqual(hashlib.sha256((HERE / 'owner_qwen_successor_install_v2.py').read_bytes()).hexdigest(), o.INSTALLER_SHA)


if __name__ == '__main__':unittest.main()
