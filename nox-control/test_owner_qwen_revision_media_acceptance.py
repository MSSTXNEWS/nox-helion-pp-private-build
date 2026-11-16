import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location('qwen_revision_media_acceptance_tested',
    Path(__file__).with_name('owner_qwen_revision_media_acceptance.py'))
m = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(m)
REF = {'request': '1234', 'source_sha': 'a' * 40, 'receipt_sha256': 'b' * 64}
BOOT = '12345678-1234-1234-1234-123456789abc'
JOB = 'c' * 32


class Client:
    def __init__(self, directory, error=None):
        self.directory, self.error, self.calls = directory, error, []

    def json(self, path, **kwargs):
        self.calls.append((path, kwargs))
        assert (self.directory / 'intent.json').is_file()
        if self.error:
            raise self.error
        return {'id': JOB, 'state': 'QUEUED', 'request': dict(m.FIXTURE)}


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.area = Path(self.temporary.name) / 'acceptance'; self.area.mkdir(mode=0o700)
        self.patch = mock.patch.object(m, 'AREA', self.area); self.patch.start(); self.addCleanup(self.patch.stop)
        self.directory = self.area / REF['request']; self.directory.mkdir(mode=0o700)

    def test_single_post_has_verified_durable_intent_and_sealed_submission(self):
        client = Client(self.directory); activity = {'generation_post_attempts': 0}
        row, sealed = m.submit_once(client, self.directory, REF, '5678', 'd' * 40, {}, activity)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0][1]['method'], 'POST')
        self.assertEqual(activity['generation_post_attempts'], 1)
        self.assertEqual(m.read_submission(REF, sealed), row)
        self.assertEqual((self.directory / 'intent.json').stat().st_mode & 0o777, 0o600)

    def test_ambiguous_post_keeps_intent_and_blocks_second_submission(self):
        client = Client(self.directory, TimeoutError('private response'))
        with self.assertRaises(TimeoutError):
            m.submit_once(client, self.directory, REF, '5678', 'd' * 40, {})
        self.assertTrue((self.directory / 'intent.json').is_file())
        self.assertFalse((self.directory / 'submission.json').exists())
        with self.assertRaises(FileExistsError):
            m.submit_once(client, self.directory, REF, '5678', 'd' * 40, {})
        self.assertEqual(len(client.calls), 1)
        with self.assertRaisesRegex(RuntimeError, 'PRIOR_INTENT_REQUIRES_OBSERVATION'):
            m.prepare_directory(REF)

    def test_intent_readback_failure_never_posts(self):
        client = Client(self.directory); activity = {'generation_post_attempts': 0}
        with mock.patch.object(m, 'read', return_value=b'corrupted'):
            with self.assertRaisesRegex(RuntimeError, 'PRIVATE_RECEIPT_READBACK'):
                m.submit_once(client, self.directory, REF, '5678', 'd' * 40, {}, activity)
        self.assertEqual(client.calls, [])
        self.assertEqual(activity['generation_post_attempts'], 0)

    def test_missing_intent_pin_does_not_disable_expected_sha(self):
        client = Client(self.directory)
        row, sealed = m.submit_once(client, self.directory, REF, '5678', 'd' * 40, {})
        row['intent_sha256'] = None
        raw = m.encoded(row) + b'\n'; (self.directory / 'submission.json').write_bytes(raw)
        sealed['receipt_sha256'] = m.digest(raw)
        with self.assertRaisesRegex(RuntimeError, 'SEALED_SUBMISSION'):
            m.read_submission(REF, sealed)

    def test_foreign_reference_cannot_use_same_submission(self):
        row, sealed = m.submit_once(Client(self.directory), self.directory, REF, '5678', 'd' * 40, {})
        changed = dict(REF, source_sha='f' * 40)
        with self.assertRaisesRegex(RuntimeError, 'SEALED_SUBMISSION'):
            m.read_submission(changed, sealed)


def proof_fixture():
    ctx = {'output': Path('/root/nox/lora/qwen35_9b/6907283384')}
    name = 'checkpoint-u00000030-a00000030-g00000000000000000001'
    before = {'trainer': {'pid': 100, 'ppid': 99, 'start_ticks': 1000, 'boot_id': BOOT}}
    process = {'pid': 200, 'ppid': 199, 'start_ticks': 2000, 'boot_id': BOOT}
    paused_evidence = [{'adapter_sha_after': 'e' * 64}] * 30
    anchor = {'successful_total': 30, 'attempted_total': 30, 'skipped_total': 0, 'data_cursor': 120,
              'adapter_tensor_sha256': 'e' * 64, 'student_state_sha256': 'f' * 64,
              'update_prefix_sha256': m.digest(m.encoded(paused_evidence))}
    handback = {'receipt': {'process': {'pid': 200, 'starttime': 2000}},
                'yielded': {'checkpoint': {'manifest_sha256': '1' * 64, 'checkpoint': str(ctx['output'] / name)}}}
    identity = {'pid': 200, 'start_ticks': 2000, 'boot_id': BOOT}
    witness = {'kind': 'RESUME_RESTORE', 'process_identity': identity,
        'before': {key: anchor[key] for key in ('successful_total', 'attempted_total', 'skipped_total', 'data_cursor', 'adapter_tensor_sha256')},
        'restored_checkpoint': {'directory': name, 'manifest_sha256': '1' * 64,
            'student_state_sha256': 'f' * 64, 'successful_total': 30}}
    saved = {'successful_total': 31, 'update_evidence': paused_evidence + [{'adapter_sha_after': '2' * 64}],
             'last_evaluation_witness': witness}
    manifest = {'process_identity': identity}
    proof = {'positive_optimizer_updates_verified': True, 'adapter_tensor_sha256': '2' * 64}
    return ctx, before, handback, anchor, proof, manifest, saved, process


class ContinuityTests(unittest.TestCase):
    def test_new_pid_saved_update_is_distinct_from_handback_start(self):
        result = m.resumed_update(*proof_fixture())
        self.assertEqual(result['successful_updates_after_media_resume'], 1)
        self.assertTrue(result['same_counter_resume_evaluation_witness_present'])

    def test_same_counter_resume_evaluation_is_not_new_learning(self):
        args = list(proof_fixture()); args[6]['successful_total'] = 30
        args[6]['update_evidence'] = args[6]['update_evidence'][:30]
        with self.assertRaisesRegex(RuntimeError, 'NEW_OPTIMIZER_UPDATE_REQUIRED'):
            m.resumed_update(*args)

    def test_wrong_saved_state_hash_or_wrong_boot_rejected(self):
        for mutate in (
            lambda a: a[6]['last_evaluation_witness']['restored_checkpoint'].update(student_state_sha256='0' * 64),
            lambda a: a[7].update(boot_id='00000000-0000-0000-0000-000000000000'),
            lambda a: a[7].update(pid=100),
            lambda a: a[6]['last_evaluation_witness']['before'].update(data_cursor=121),
        ):
            args = list(proof_fixture()); mutate(args)
            with self.assertRaises(RuntimeError):
                m.resumed_update(*args)

    def test_update_history_fork_rejected(self):
        args = list(proof_fixture()); args[6]['update_evidence'][0] = {'adapter_sha_after': '9' * 64}
        with self.assertRaisesRegex(RuntimeError, 'RESTORE_WITNESS_PREFIX'):
            m.resumed_update(*args)

    def test_periodic_witness_does_not_claim_same_counter_witness_present(self):
        args = list(proof_fixture()); args[6]['last_evaluation_witness']['kind'] = 'PERIODIC'
        result = m.resumed_update(*args)
        self.assertTrue(result['new_optimizer_checkpoint_verified'])
        self.assertFalse(result['same_counter_resume_evaluation_witness_present'])

    def test_bootstrap_cannot_reach_source_or_submit_operations(self):
        shared = SimpleNamespace(current_context=lambda ref: {'context': ref},
                                 activation_status=lambda ctx: {'active': False})
        with mock.patch.object(m, 'read') as read:
            with self.assertRaisesRegex(RuntimeError, 'EXECUTION_NOT_ACTIVE'):
                m.context({'owner_qwen_execution_revision.py': shared}, REF)
            read.assert_not_called()


class HistoricalAndPrivacyTests(unittest.TestCase):
    def test_existing_control_or_yield_blocks_new_smoke_without_clearing_it(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(m, 'STATE', Path(temp)):
            state = Path(temp); guard = SimpleNamespace(owner_stop=lambda: False)
            for name in ('TRAIN_HOLD.flag', 'TRAIN_PAUSE_REQUEST.flag', 'OWNER_MAINTENANCE.flag'):
                path = state / name; path.write_bytes(b'owner\n')
                with self.assertRaisesRegex(RuntimeError, 'TRAINING_CONTROL_PRESENT'):
                    m.idle_training_controls(guard)
                self.assertEqual(path.read_bytes(), b'owner\n'); path.unlink()
            path = state / 'media/training_yield.json'; path.parent.mkdir()
            m.private_create(path, {'active': True})
            for value in (True, None, 1, 'false'):
                path.write_bytes(m.encoded({'active': value}))
                with self.assertRaisesRegex(RuntimeError, 'PREVIOUS_MEDIA_YIELD_NOT_VERIFIED_IDLE'):
                    m.idle_training_controls(guard)
                self.assertEqual(json.loads(path.read_text())['active'], value)
            path.write_bytes(m.encoded({'active': False}))
            m.idle_training_controls(guard)
            with self.assertRaisesRegex(RuntimeError, 'OWNER_STOP'):
                m.idle_training_controls(SimpleNamespace(owner_stop=lambda: True))

    def test_exact_previous_observation_keeps_historical_scope(self):
        with tempfile.TemporaryDirectory() as temp:
            area = Path(temp); folder = area / REF['request']; folder.mkdir()
            source = {'request': '5678', 'source_sha': 'd' * 40, 'receipt_sha256': 'e' * 64}
            submission = {'job_id': JOB, 'before': {}}
            anchor = {'directory': 'checkpoint-u00000030-a00000030-g00000000000000000001',
                'successful_total': 30, 'attempted_total': 30, 'skipped_total': 0, 'data_cursor': 120,
                'full_checkpoint_files_verified': True, 'verified_files': 10, 'verified_bytes': 520000000,
                **{key: 'a' * 64 for key in ('manifest_sha256', 'student_state_sha256', 'adapter_tensor_sha256',
                                             'update_prefix_sha256', 'terminal_receipt_sha256')}}
            row = {'schema': m.SCHEMA, 'execution_revision': REF, 'submission_context': source,
                   'job_id': JOB, 'before': {}, 'artifact_verified': True, 'handback_claim_verified': True,
                   'controlled_pause': anchor, 'handback_receipt_sha256': 'b' * 64}
            pin = m.private_create(folder / 'result.json', row)
            prior = {**source, 'receipt_sha256': pin}
            with mock.patch.object(m, 'AREA', area):
                result, _ = m.prior_pause(REF, source, submission, prior)
                self.assertEqual(result['payload_read_scope'], 'HISTORICAL_FULL_SHA_IN_EXPLICIT_SEALED_OBSERVATION')
                with self.assertRaisesRegex(RuntimeError, 'FILE_SHA'):
                    m.prior_pause(REF, source, submission, {**prior, 'receipt_sha256': '0' * 64})

    def test_artifact_projection_omits_private_path_url_prompt_cookie(self):
        source = {key: True for key in ('kind', 'job_id', 'bytes', 'sha256', 'media_type', 'decode',
            'decode_verified', 'authenticated_http_verified', 'pixels_exported', 'scope')}
        source.update(path='/private', url='http://private', prompt='private prompt', cookie='secret')
        result = m.artifact_projection(source)
        self.assertFalse({'path', 'url', 'prompt', 'cookie'} & result.keys())

    def test_frozen_helper_fixture_and_no_old_entry_calls(self):
        path = Path(__file__).with_name(m.HELPER)
        self.assertEqual(m.digest(path.read_bytes()), m.HELPER_SHA)
        runtime_path = Path(__file__).with_name('owner_media_runtime.py')
        runtime = m.module(runtime_path.read_bytes(), runtime_path.name, m.PINS[runtime_path.name])
        self.assertEqual(runtime.validate_request(m.FIXTURE), m.FIXTURE)
        graph = runtime.workflow({'id': JOB, 'request': m.FIXTURE}, {'checkpoint': {'filename': 'fixture.safetensors'}})
        samplers = [node for node in graph.values() if node['class_type'] == 'KSampler']
        self.assertEqual(len(samplers), 1)
        self.assertEqual(samplers[0]['inputs']['steps'], 4)
        import ast
        tree = ast.parse(Path(m.__file__).read_text())
        calls = {node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
        self.assertFalse({'training_guard', 'wait_job', 'final_unload', 'tick', 'flock', 'create_job', 'run_media_task'} & calls)
        observe = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'observe_existing')
        self.assertFalse(any(isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                             and node.func.id in {'submit_once', 'prepare_directory', 'private_create'} for node in ast.walk(observe)))

    def test_native_handback_claim_and_qwen_yield_extension(self):
        with tempfile.TemporaryDirectory() as temp:
            state = Path(temp); directory = state / 'media/training_handback' / JOB; directory.mkdir(parents=True)
            old = {'pid': 100, 'start_ticks': 1000, 'boot_id': BOOT}
            before = {'trainer': old, 'service': {'pid': 99}, 'handoff_config_canonical_sha256': '6' * 64}
            ctx = {'context': REF, 'lineage_sha256': '7' * 64,
                   'execution': {'wrapper_sha256': '8' * 64, 'admission_sha256': '9' * 64}}
            qwen = {'pid': 100, 'starttime': 1000, 'ppid': 99, 'cuda': '1', 'service': 'nox-train-volta-t866u'}
            yielded = {'job_id': JOB, 'requested_at': 100., 'pause_token': 'NOX_MEDIA_CHECKPOINT_YIELD ' + JOB + '\n',
                'wrapper_sha256': '8' * 64, 'trainer_before': {'state': 'RUNNING', 'pid': 99},
                'qwen_student': qwen, 'qwen_admission_sha256': '9' * 64}
            ysha = m.digest(m.encoded(yielded))
            yielded.update(active=False, resume=False, resume_state='ADMITTED_EXISTING_TRAINER_RESUMED',
                           handback_source_sha256=m.PINS['owner_qwen_media_handoff.py'])
            claim = {'worker': 'nox-agent-01', 'pid': 50, 'nonce': 'a' * 24, 'at': '2026-11-16'}
            process = {'pid': 200, 'starttime': 2000, 'ppid': 199, 'cuda': '1', 'service': 'nox-train-volta-t866u'}
            request = {'schema': 'NOX_QWEN_MEDIA_HANDBACK_V1', 'stage': 'RESUMED', 'start_command_issued': True,
                'job_id': JOB, 'initial_admission': REF, 'source_sha256': m.PINS['owner_qwen_media_handoff.py'],
                'config_sha256': '6' * 64, 'yield_sha256': ysha, 'process': process, 'boot_id': BOOT,
                'baseline_step': 30, 'baseline_receipt_sha256': 'b' * 64}
            task = {'id': 'owner.media.resume.' + JOB, 'handler': 'owner_media_resume', 'status': 'done',
                'source': 'owner_qwen_media_handoff', 'class': 'training', 'locks': ['gpu1'], 'deps': [],
                'params': {'job_id': JOB}, 'owner_claim': claim, 'claimed_by': claim['worker'], 'owner_claim_epoch': 101.}
            receipt = {**request, 'state': 'ADMITTED_EXISTING_TRAINER_RESUMED', 'verified': True,
                'scope': m.HANDOFF_SCOPE, 'blockers': m.HANDOFF_BLOCKERS, 'task_id': task['id'], 'claim': claim,
                'claim_epoch': 101., 'optimizer_progress_since_resume_verified': False, 'weights_promoted': False,
                'lineage_sha256': '7' * 64}
            path = directory / ('claim-' + claim['nonce'] + '.json'); pin = m.private_create(path, receipt)
            task['result'] = {key: receipt[key] for key in ('state', 'verified', 'scope', 'blockers', 'source_sha256')}
            task['result'].update(receipt_path=str(path), receipt_sha256=pin)
            m.private_create(directory / 'request.json', request)
            ypath = state / 'media/training_yield.json'; m.private_create(ypath, yielded)
            for name, raw in {'TRAIN_PAUSE_REQUEST.flag': yielded['pause_token'],
                    'TRAIN_HOLD.flag': 'OWNER_QWEN_WINDOW_FAILED request=' + REF['request'] + ' goal=1000\n'}.items():
                path = directory / ('released-' + name); path.write_text(raw); path.chmod(0o600)
            with mock.patch.object(m, 'STATE', state):
                result = m.handback_record(ctx, {'job_id': JOB, 'before': before}, task, 50)
                self.assertEqual(result['receipt_sha256'], pin)
                yielded['qwen_student']['starttime'] = 999
                ypath.write_bytes(m.encoded(yielded))
                with self.assertRaisesRegex(RuntimeError, 'YIELD_CHAIN'):
                    m.handback_record(ctx, {'job_id': JOB, 'before': before}, task, 50)

    def test_completed_artifact_with_queued_handback_remains_pending(self):
        submission = {'job_id': JOB, 'before': {'handoff_config_sha256': 'a' * 64, 'dispatcher': {'pid': 50}}}
        task = {'status': 'done', 'owner_claim': {}}
        helper = SimpleNamespace(dispatcher_identity=lambda: {'pid': 50},
            claim_projection=lambda *a, **k: {}, verify_artifact=lambda *a: {})
        runtime = SimpleNamespace(ACTIVE={'QUEUED'}, TERMINAL={'COMPLETED'}, job_path=lambda jid: Path('/dummy'),
                                  configuration=lambda: {})
        loaded = {'owner_qwen_training_guard.py': SimpleNamespace(owner_stop=lambda: False),
                  'owner_media_runtime.py': runtime}
        job = {'schema': 'NOX_OWNER_MEDIA_JOB_V1', 'id': JOB, 'request': m.FIXTURE,
               'state': 'COMPLETED', 'generation_verified': True, 'gpu1_released': True}
        client = SimpleNamespace(json=lambda path: job)
        with mock.patch.object(m, 'context', return_value={}), \
             mock.patch.object(m, 'handoff_config', return_value=({}, 'a' * 64)), \
             mock.patch.object(m, 'document', return_value=(job, 'b' * 64)), \
             mock.patch.object(m, 'queue_rows', return_value={'media': task, 'parent': None, 'handback': None}), \
             mock.patch.object(m, 'valid_claim', return_value={}), \
             mock.patch.object(m, 'artifact_projection', return_value={'sha256': 'c' * 64}), \
             mock.patch.object(m, 'handback_record', return_value=None), \
             mock.patch.object(m.time, 'monotonic', side_effect=[0, 2, 2]), \
             mock.patch.object(m.time, 'sleep'):
            result = m.observe(helper, loaded, REF, submission, REF, client, {'bytes': 0}, 91)
        self.assertEqual(result['state'], 'MEDIA_COMPLETE_RESUME_PENDING')
        self.assertTrue(result['artifact_verified'])
        self.assertFalse(result['acceptance_verified'])
        self.assertFalse(result['optimizer_progress_after_resume_verified'])


if __name__ == '__main__':
    unittest.main()
