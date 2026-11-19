import ast
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location('held_recover_tested', Path(__file__).with_name('owner_qwen_held_media_recover.py'))
m = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(m)
JOB = 'e' * 32


def raw(row):
    return (json.dumps(row, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def intent():
    return {'schema': m.SUBMISSION_SCHEMA, 'stage': 'PREPARED_SINGLE_POST', 'rollback_reference': dict(m.ROLLBACK),
            'request': m.REQUEST, 'source_sha': m.SOURCE, 'fixture_sha256': m.FIXTURE_SHA, 'created_at': 123.0,
            'before': {'private_fixture_data': 'never export this'}, 'generation_retry_authorized': False}


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.area = Path(self.tmp.name) / 'journal'
        patch = mock.patch.object(m, 'AREA', self.area); patch.start(); self.addCleanup(patch.stop)

    def write(self, name, value):
        self.area.mkdir(mode=0o700, exist_ok=True)
        path = self.area / name; path.write_bytes(raw(value)); path.chmod(0o600)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def submitted(self):
        old = intent(); pin = self.write('intent.json', old)
        row = {**old, 'stage': 'SINGLE_JOB_SUBMITTED', 'intent_sha256': pin, 'job_id': JOB, 'submitted_at': 124.0}
        sha = self.write('submission.json', row)
        return old, row, sha

    def test_absent_directory_is_observed_without_creation(self):
        result = m.inspect()
        self.assertEqual(result['state'], 'JOURNAL_DIRECTORY_CONFIRMED_ABSENT')
        self.assertTrue(result['journal_observation_complete'])
        self.assertFalse(self.area.exists())
        self.assertFalse(result['automatic_repost_authorized'])

    def test_intent_only_never_discovers_or_invents_a_job(self):
        self.write('intent.json', intent())
        before = (self.area / 'intent.json').read_bytes()
        result = m.inspect()
        self.assertEqual(result['state'], 'INTENT_PRESENT_SUBMISSION_UNRESOLVED')
        self.assertEqual(result['prior_generation_occurrence'], 'UNKNOWN')
        self.assertNotIn('job_id', result); self.assertNotIn('submission_context', result)
        self.assertEqual((self.area / 'intent.json').read_bytes(), before)
        self.assertEqual(set(p.name for p in self.area.iterdir()), {'intent.json'})

    def test_sealed_submission_returns_actual_sha_and_only_exact_job(self):
        _, _, sha = self.submitted(); result = m.inspect()
        self.assertEqual(result['state'], 'SEALED_SUBMISSION_RESULT_PENDING')
        self.assertEqual(result['job_id'], JOB)
        self.assertEqual(result['submission_context'], {'request': m.REQUEST, 'source_sha': m.SOURCE, 'receipt_sha256': sha})
        self.assertNotIn('private_fixture_data', json.dumps(result))
        self.assertNotIn('never export this', json.dumps(result))

    def test_partial_write_is_held_and_not_absent_or_repostable(self):
        self.write('intent.json', intent()); path = self.area / 'submission.json'
        path.write_bytes(b'{"schema":'); path.chmod(0o600)
        result = m.inspect()
        self.assertEqual(result['state'], 'JOURNAL_OBSERVATION_HELD')
        self.assertEqual(result['reason'], 'HOLD_HELD_MEDIA_RECOVERY_PARTIAL_OR_INVALID_JSON')
        self.assertTrue(result['files']['submission.json']['present'])
        self.assertNotIn('job_id', result)

    def test_foreign_context_or_unsealed_submission_is_rejected(self):
        old, submitted, _ = self.submitted()
        for change in ('source', 'intent'):
            row = copy.deepcopy(submitted)
            if change == 'source': row['source_sha'] = '0' * 40
            else: row['intent_sha256'] = '0' * 64
            self.write('submission.json', row); result = m.inspect()
            self.assertEqual(result['state'], 'JOURNAL_OBSERVATION_HELD')
            self.assertNotIn('submission_context', result)

    def test_result_records_prior_claim_but_not_fresh_generation_proof(self):
        before, submitted, sha = self.submitted()
        outcome = {'schema': m.SMOKE_SCHEMA, 'request': m.REQUEST, 'source_sha': m.SOURCE, 'rollback_reference': m.ROLLBACK,
                   'state': 'MEDIA_GENERATION_PENDING', 'generation_post_attempts': 1, 'acceptance_verified': False,
                   'artifact_verified': False, 'trainer_start_calls': 0, 'training_flags_written': False,
                   'sources_modified': False, 'direct_engine_control_calls': 0, 'private_content_exported': False,
                   'submission_context': {'request': m.REQUEST, 'source_sha': m.SOURCE, 'receipt_sha256': sha},
                   'before': before['before'], 'job_id': JOB, 'reason': 'private server contents'}
        pin = self.write('result.json', outcome); result = m.inspect()
        self.assertEqual(result['state'], 'RESULT_RECORDED')
        self.assertEqual(result['result_context']['receipt_sha256'], pin)
        self.assertIsNone(result['recorded_reason'])
        self.assertFalse(result['generation_independently_verified_by_reader'])
        self.assertNotIn('private server contents', json.dumps(result))

    def test_symlink_wrong_permissions_or_record_replacement_are_held(self):
        self.write('intent.json', intent()); path = self.area / 'intent.json'
        path.chmod(0o644); self.assertEqual(m.inspect()['state'], 'JOURNAL_OBSERVATION_HELD')
        path.chmod(0o600)
        real_read = m.read_record
        def replace_after_read(p):
            value = real_read(p)
            if p.name == 'intent.json':
                replacement = p.with_suffix('.tmp'); replacement.write_bytes(p.read_bytes()); replacement.chmod(0o600)
                os.replace(replacement, p)
            return value
        with mock.patch.object(m, 'read_record', side_effect=replace_after_read):
            self.assertEqual(m.inspect()['reason'], 'HOLD_HELD_MEDIA_RECOVERY_JOURNAL_CHANGED_DURING_READ')
        path.unlink(); path.symlink_to('/private/unknown')
        self.assertEqual(m.inspect()['reason'], 'HOLD_HELD_MEDIA_RECOVERY_SYMLINK')

    def test_source_is_standalone_and_fixture_digest_matches_frozen_smoke(self):
        source = Path(m.__file__).read_text()
        self.assertNotIn('__NOX_BUNDLE_JSON__', source)
        self.assertNotIn('import owner_', source)
        self.assertNotIn('urllib', source)
        self.assertNotIn('subprocess', source)
        tree = ast.parse(Path(__file__).with_name('owner_qwen_held_media_smoke.py').read_bytes())
        node = next(n for n in tree.body if isinstance(n, ast.Assign)
                    and any(isinstance(t, ast.Name) and t.id == 'FIXTURE' for t in n.targets))
        value = ast.literal_eval(node.value)
        encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), m.FIXTURE_SHA)


if __name__ == '__main__':
    unittest.main()
