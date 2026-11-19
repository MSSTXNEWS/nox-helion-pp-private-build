import copy
import fcntl
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import time
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location('held_media_smoke_tested',
    Path(__file__).with_name('owner_qwen_held_media_smoke.py'))
m = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(m)
CORE_SPEC = importlib.util.spec_from_file_location('held_smoke_core_fixture',
    Path(__file__).with_name('owner_qwen_revision_install.py'))
core = importlib.util.module_from_spec(CORE_SPEC); CORE_SPEC.loader.exec_module(core)
REF = {'request': '1234', 'source_sha': 'a' * 40, 'receipt_sha256': 'b' * 64}
SEALED = {'request': '5678', 'source_sha': 'c' * 40, 'receipt_sha256': 'd' * 64}
JID = 'e' * 32
BEFORE = {'dispatcher': {'pid': 100, 'start_ticks': '200'}, 'flags': dict(core.FLAGS)}


class Client:
    cookie = 'private-owner-cookie'

    def __init__(self, directory=None, error=None):
        self.directory, self.error, self.calls = directory, error, []

    def json(self, path, **kwargs):
        self.calls.append((path, kwargs))
        if kwargs.get('method') == 'POST':
            assert (self.directory / 'intent.json').is_file()
            assert (self.directory / 'intent.json').stat().st_mode & 0o777 == 0o600
            if self.error:
                raise self.error
            return {'id': JID, 'request': dict(m.FIXTURE), 'state': 'QUEUED'}
        return {'id': JID, 'request': dict(m.FIXTURE), 'state': 'COMPLETED'}

    def close(self):
        self.cookie = None


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.area = Path(self.tmp.name) / 'smoke'
        patch = mock.patch.object(m, 'AREA', self.area); patch.start(); self.addCleanup(patch.stop)
        self.directory = m.prepare_directory(REF)

    def test_one_post_binds_fsynced_intent_and_exact_readable_submission(self):
        client = Client(self.directory); activity = {'generation_post_attempts': 0}
        submitted, sealed = m.submit_once(client, self.directory, REF, '5678', 'c' * 40, BEFORE, activity)
        self.assertEqual(activity['generation_post_attempts'], 1)
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(client.calls[0][0], '/api/ui/media/jobs')
        self.assertEqual(m.read_submission(REF, sealed), submitted)
        self.assertEqual((self.directory / 'submission.json').stat().st_mode & 0o777, 0o600)

    def test_timeout_preserves_intent_and_forbids_retry_or_guessing(self):
        client = Client(self.directory, TimeoutError('private transport text'))
        activity = {'generation_post_attempts': 0}
        with self.assertRaises(TimeoutError):
            m.submit_once(client, self.directory, REF, '5678', 'c' * 40, BEFORE, activity)
        self.assertTrue((self.directory / 'intent.json').exists())
        self.assertFalse((self.directory / 'submission.json').exists())
        with self.assertRaises(FileExistsError):
            m.submit_once(client, self.directory, REF, '5679', 'c' * 40, BEFORE, {})
        self.assertEqual(len(client.calls), 1)
        with self.assertRaisesRegex(m.SmokeHold, 'PRIOR_INTENT'):
            m.prepare_directory(REF)
        with self.assertRaises(FileNotFoundError):
            m.read_submission(REF, SEALED)

    def test_failed_submission_persistence_is_not_a_retry_permission(self):
        client = Client(self.directory); real = m.private_create
        def fail_second(path, row):
            if path.name == 'submission.json':
                raise OSError('private filesystem error')
            return real(path, row)
        with mock.patch.object(m, 'private_create', side_effect=fail_second):
            with self.assertRaises(OSError):
                m.submit_once(client, self.directory, REF, '5678', 'c' * 40, BEFORE, {})
        with self.assertRaises(FileExistsError):
            m.submit_once(client, self.directory, REF, '5678', 'c' * 40, BEFORE, {})
        self.assertEqual(len(client.calls), 1)

    def test_intent_readback_failure_prevents_post(self):
        client = Client(self.directory); activity = {'generation_post_attempts': 0}
        with mock.patch.object(m, 'read', return_value=b'corrupted'):
            with self.assertRaisesRegex(m.SmokeHold, 'RECEIPT_READBACK'):
                m.submit_once(client, self.directory, REF, '5678', 'c' * 40, BEFORE, activity)
        self.assertEqual(client.calls, [])
        self.assertEqual(activity['generation_post_attempts'], 0)

    def test_foreign_reference_or_unpinned_intent_cannot_adopt_job(self):
        submitted, sealed = m.submit_once(Client(self.directory), self.directory, REF, '5678', 'c' * 40, BEFORE, {})
        with self.assertRaisesRegex(m.SmokeHold, 'SEALED_SUBMISSION'):
            m.read_submission(dict(REF, source_sha='f' * 40), sealed)
        submitted['intent_sha256'] = None
        raw = m.encode(submitted); path = self.directory / 'submission.json'; path.write_bytes(raw)
        with self.assertRaisesRegex(m.SmokeHold, 'SEALED_SUBMISSION'):
            m.read_submission(REF, dict(sealed, receipt_sha256=m.digest(raw)))


def rollback_fixture():
    return {'schema': m.ROLLBACK_SCHEMA, 'state': 'ORIGINAL_CHECKPOINT25_HELD_STATE_RESTORED',
        'request': REF['request'], 'source_sha': REF['source_sha'], 'failed_execution_revision': m.FAILED_REF,
        'failed_attempt_preserved': True, 'training_flags_present': True, 'learning_rearm_performed': False,
        'initial_installer_reentry_not_executed': True, 'trainer_start_calls': 0, 'optimizer_permission_issued': False,
        'checkpoints_modified': False, 'main_chat_model_restarted': False, 'active_chat': m.MODEL,
        'chat_health': {'8080': 200, '8081': 200, '8082': 200},
        'checkpoint': {**core.ANCHOR, 'full_files_sha256_verified': True},
        'checkpoint_inventory': {'no_new_revision_checkpoint_metadata_observed': True},
        'ordinary_guard': {'state': 'INHIBITED', 'reason': 'EVALUATION_STALE',
                           'successful_updates': 25, 'evaluated_at_update': 10}}


class GateTests(unittest.TestCase):
    def test_real_sealed_success_is_required_not_http_or_rc_alone(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(m, 'ROLLBACK_AREA', Path(temp)):
            area = Path(temp) / REF['request']; area.mkdir(mode=0o700)
            row = rollback_fixture(); pin = m.private_create(area / 'result.json', row)
            ref = dict(REF, receipt_sha256=pin)
            self.assertTrue(m.rollback_receipt(core, ref)['historical_full_checkpoint_sha256_verified'])
            for key, bad in (('optimizer_permission_issued', True), ('learning_rearm_performed', True),
                             ('state', 'HOLD_QWEN_REVISION_ROLLBACK')):
                changed = copy.deepcopy(row); changed[key] = bad
                raw = m.encode(changed); (area / 'result.json').write_bytes(raw)
                with self.assertRaisesRegex(m.SmokeHold, 'ROLLBACK_ACCEPTANCE'):
                    m.rollback_receipt(core, dict(ref, receipt_sha256=m.digest(raw)))

    def test_new_execution_or_activation_prevents_held_smoke(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); scripts = root / 'scripts'; scripts.mkdir()
            failed = root / 'attempt'; failed.mkdir()
            fake = SimpleNamespace(protected=lambda: None, OLD_SOURCES={}, CONFIG_PINS={},
                OLD_ADMISSION='a' * 64, OLD_WRAPPER='b' * 64, SHARED='shared.py', STUDENT='student.py', SELF='issuer.py')
            with mock.patch.multiple(m, ROOT=root, SCRIPTS=scripts, STATE=root / 'state', FAILED_AREA=failed), \
                    mock.patch.object(m, 'read', return_value=b''):
                m.held_sources(fake)
                for path in (failed / 'activation.json', scripts / 'student.py'):
                    path.write_bytes(b'{}')
                    with self.assertRaisesRegex(m.SmokeHold, 'REVISION_OR_ACTIVATION_PRESENT'):
                        m.held_sources(fake)
                    path.unlink()

    def test_missing_active_or_nonbool_yield_is_not_idle(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(m, 'STATE', Path(temp)):
            folder = Path(temp) / 'media'; folder.mkdir(); path = folder / 'training_yield.json'
            m.inactive_yield()
            for value in ({}, {'active': True}, {'active': 1}, {'active': 'false'}):
                path.write_text(json.dumps(value))
                with self.assertRaisesRegex(m.SmokeHold, 'ACTIVE_OR_UNKNOWN_YIELD'):
                    m.inactive_yield()
            path.write_text('{"active":false}'); m.inactive_yield()

    def test_real_shared_lease_refuses_exclusive_but_permits_guard_shared(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'maintenance.lock'; path.write_bytes(b''); path.chmod(0o600)
            other = os.open(path, os.O_RDONLY)
            try:
                with mock.patch.object(m, 'MAINTENANCE', path):
                    fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    with self.assertRaisesRegex(m.SmokeHold, 'MAINTENANCE_EXCLUSIVE'):
                        m.maintenance_shared()
                    fcntl.flock(other, fcntl.LOCK_UN)
                    owned = m.maintenance_shared()
                    try:
                        fcntl.flock(other, fcntl.LOCK_SH | fcntl.LOCK_NB)
                        with self.assertRaises(BlockingIOError):
                            fcntl.flock(other, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    finally:
                        os.close(owned)
            finally:
                os.close(other)

    def test_unknown_job_prevents_submission_readiness(self):
        with tempfile.TemporaryDirectory() as temp, mock.patch.object(m, 'STATE', Path(temp)):
            folder = Path(temp) / 'media/jobs'; folder.mkdir(parents=True)
            path = folder / (JID + '.json')
            path.write_text(json.dumps({'schema': 'NOX_OWNER_MEDIA_JOB_V1', 'id': JID, 'state': 'UNKNOWN'}))
            runtime = SimpleNamespace(ACTIVE={'QUEUED'}, TERMINAL={'COMPLETED'})
            with self.assertRaisesRegex(m.SmokeHold, 'JOB_INVENTORY_STATE'):
                m.no_other_jobs(runtime)


class ObservationTests(unittest.TestCase):
    def fixture(self):
        job = {'schema': 'NOX_OWNER_MEDIA_JOB_V1', 'id': JID, 'request': dict(m.FIXTURE),
               'state': 'COMPLETED', 'generation_verified': True, 'gpu1_released': True,
               'training_resume': 'TRAINING_PREVIOUSLY_HELD'}
        proof = {'kind': 'image', 'job_id': JID, 'path': '/private/output.png', 'url': '/private',
                 'bytes': 1234, 'sha256': 'f' * 64, 'media_type': 'image/png', 'decode': {'width': 256, 'height': 256},
                 'decode_verified': True, 'authenticated_http_verified': True, 'pixels_exported': False, 'scope': 'GENERATED'}
        helper = SimpleNamespace(claim_projection=mock.Mock(return_value={'pid': 100, 'task_id': 'owner.media.' + JID}),
                                 verify_artifact=mock.Mock(return_value=proof))
        runtime = SimpleNamespace(ACTIVE={'RUNNING'}, TERMINAL={'COMPLETED'}, job_path=lambda _: Path('/unused'),
                                  configuration=lambda: {})
        return job, {'helper': helper, 'runtime': runtime}

    def test_claim_decode_delivery_and_held_postcondition_all_required(self):
        job, d = self.fixture(); client = Client(); result = {}
        with mock.patch.object(m, 'held_snapshot', return_value={'held': True}) as held, \
                mock.patch.object(m, 'no_other_jobs'), mock.patch.object(m, 'document', return_value=(job, 'a' * 64)), \
                mock.patch.object(m, 'queue_task', return_value={'status': 'done'}):
            m.observe(d, {}, {}, '', {'job_id': JID, 'before': BEFORE}, client, time.monotonic() + 100, result)
        self.assertEqual(result['state'], m.ACCEPTED)
        self.assertTrue(result['acceptance_verified'])
        self.assertEqual(held.call_count, 2)
        self.assertNotIn('path', result['artifact']); self.assertNotIn('url', result['artifact'])
        self.assertTrue(all(call[1].get('method', 'GET') == 'GET' for call in client.calls))

    def test_artifact_cannot_hide_changed_training_flag_after_decode(self):
        job, d = self.fixture(); result = {}
        with mock.patch.object(m, 'held_snapshot', side_effect=[{}, m.SmokeHold('HOLD_OLD_FLAGS_CHANGED')]), \
                mock.patch.object(m, 'no_other_jobs'), mock.patch.object(m, 'document', return_value=(job, 'a' * 64)), \
                mock.patch.object(m, 'queue_task', return_value={'status': 'done'}):
            with self.assertRaisesRegex(m.SmokeHold, 'OLD_FLAGS_CHANGED'):
                m.observe(d, {}, {}, '', {'job_id': JID, 'before': BEFORE}, Client(), time.monotonic() + 100, result)
        self.assertFalse(result.get('acceptance_verified', False))

    def test_completed_image_with_resume_request_is_rejected_before_decode(self):
        job, d = self.fixture(); job['training_resume'] = 'TRAINING_RESUME_QUEUED'
        with mock.patch.object(m, 'held_snapshot', return_value={}), mock.patch.object(m, 'no_other_jobs'), \
                mock.patch.object(m, 'document', return_value=(job, 'a' * 64)), \
                mock.patch.object(m, 'queue_task', return_value={'status': 'done'}):
            with self.assertRaisesRegex(m.SmokeHold, 'TRAINER_RESUME_NOT_HELD'):
                m.observe(d, {}, {}, '', {'job_id': JID, 'before': BEFORE}, Client(), time.monotonic() + 100, {})
        d['helper'].verify_artifact.assert_not_called()

    def test_expired_poll_budget_keeps_pending_without_more_requests(self):
        _, d = self.fixture(); client = Client(); result = {}
        m.observe(d, {}, {}, '', {'job_id': JID, 'before': BEFORE}, client, time.monotonic() + 1, result)
        self.assertEqual(result['state'], 'MEDIA_GENERATION_PENDING'); self.assertEqual(client.calls, [])


class EntryTests(unittest.TestCase):
    def test_ambiguous_main_is_pending_and_second_main_cannot_post(self):
        with tempfile.TemporaryDirectory() as temp:
            area = Path(temp) / 'smoke'; directory = area / REF['request']
            client = Client(directory, TimeoutError('private transport body'))
            d = {'helper': SimpleNamespace(OwnerClient=SimpleNamespace(authenticate=lambda: client)), 'core': object()}
            lease = Path(temp) / 'lock'; lease.write_bytes(b'')
            with mock.patch.object(m, 'AREA', area), mock.patch.object(m, 'dependencies', return_value=d), \
                    mock.patch.object(m, 'maintenance_shared', side_effect=lambda: os.open(lease, os.O_RDONLY)), \
                    mock.patch.object(m, 'rollback_receipt', return_value={}), \
                    mock.patch.object(m, 'held_context', return_value=({}, {}, '')), \
                    mock.patch.object(m, 'held_snapshot', return_value=BEFORE), \
                    mock.patch.object(m, 'ready_to_submit', return_value={}), \
                    mock.patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '5678', 'NOX_OWNER_SOURCE_SHA': 'c' * 40}):
                result = m.execute(REF)
                self.assertEqual(result['state'], 'MEDIA_SUBMISSION_UNRESOLVED')
                self.assertEqual(result['generation_post_attempts'], 1)
                self.assertEqual(result['reason'], 'HOLD_QWEN_HELD_MEDIA_TIMEOUTERROR')
                second = m.execute(REF)
            self.assertEqual(second['generation_post_attempts'], 0)
            self.assertEqual(len(client.calls), 1)
            self.assertNotIn('private transport body', json.dumps(result))

    def test_observe_existing_uses_sealed_job_and_never_calls_submit(self):
        with mock.patch.object(m, 'execute', return_value={'state': 'MEDIA_GENERATION_PENDING'}) as execute:
            result = m.observe_existing(REF, SEALED)
            self.assertEqual(result['state'], 'MEDIA_GENERATION_PENDING')
            execute.assert_called_once_with(REF, SEALED, timeout=180)
        with mock.patch.object(m, 'execute') as execute:
            with self.assertRaisesRegex(m.SmokeHold, 'REFERENCE'):
                m.observe_existing(REF, None)
            execute.assert_not_called()

    def test_missing_sealed_rollback_fails_before_dependencies(self):
        with mock.patch.object(m, 'dependencies') as deps:
            result = m.execute(None)
        deps.assert_not_called(); self.assertFalse(result['acceptance_verified'])
        self.assertEqual(result['generation_post_attempts'], 0)

    def test_180_second_cap_and_exact_definition_only_bundle(self):
        with self.assertRaisesRegex(m.SmokeHold, 'TIMEOUT_SCOPE'):
            m.execute(REF, timeout=181)
        for name, pin in m.PINS.items():
            raw = Path(__file__).with_name(name).read_bytes()
            self.assertEqual(m.digest(raw), pin)
            loaded = m.module(raw, name, pin)
            self.assertEqual(Path(loaded.__file__).name, name)


if __name__ == '__main__':
    unittest.main()
