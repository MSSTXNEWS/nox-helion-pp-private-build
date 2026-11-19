import importlib.util
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('retry_checked', Path(__file__).with_name('owner_qwen_media_retry_entry.py'))
M = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(M)


class SubmissionTests(unittest.TestCase):
    def fixture(self, crash=False, unexpected=False):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        root = Path(folder.name); state = root / 'state'
        new = 'a' * 32
        request = {'kind': 'image', 'prompt': 'private fixture', 'negative_prompt': '',
                   'width': 512, 'height': 512, 'frames': 1, 'fps': 8, 'seed': 123}
        previous = {'id': 'b' * 32, 'owner': 'private-owner', 'request': request}
        writes, saves = [], []
        link = {'replacements': []}
        rt = types.SimpleNamespace(validate_request=lambda data: dict(data),
                                   job_path=lambda jid: state / 'media/jobs' / (jid + '.json'))
        def atomic(path, value):
            # Every normal job publication must already have a durable ID.
            if Path(path).parent == state / 'media/jobs':
                self.assertTrue(saves)
                self.assertEqual(saves[-1]['replacements'][0]['state'], 'PREPARED_BEFORE_JOB_PUBLICATION')
                self.assertEqual(saves[-1]['replacements'][0]['new_job_id'], new)
            writes.append((path, value))
        rt.atomic = atomic
        def create(data, owner):
            self.assertEqual(data, request); self.assertEqual(owner, previous['owner'])
            job = {'id': new, 'request': data, 'owner': owner, 'state': 'QUEUED'}
            rt.atomic(state / 'unexpected' if unexpected else rt.job_path(new), job)
            if crash:
                raise OSError('simulated process loss after first publication')
            rt.atomic(state / 'media/inbox' / (new + '.json'), {'job_id': new})
            return {'id': new}
        rt.create_job = create
        def save():
            import copy
            saves.append(copy.deepcopy(link))
        return state, rt, previous, link, save, writes, saves, atomic

    def test_normal_request_seed_and_owner_preserved(self):
        state, rt, old, link, save, writes, saves, atomic = self.fixture()
        with patch.object(M, 'STATE', state):
            row = M.submit_linked(rt, old, link, save)
        self.assertEqual(row['state'], 'SUBMITTED_GENERATION_PENDING')
        self.assertEqual(len(writes), 2)
        self.assertIs(rt.atomic, atomic)
        self.assertNotIn('private fixture', str(link))
        self.assertNotIn('private-owner', str(link))

    def test_crash_retains_known_new_id_and_restores_runtime(self):
        state, rt, old, link, save, writes, saves, atomic = self.fixture(crash=True)
        with patch.object(M, 'STATE', state), self.assertRaises(OSError):
            M.submit_linked(rt, old, link, save)
        self.assertEqual(len(writes), 1)
        self.assertEqual(saves[-1]['replacements'][0]['new_job_id'], 'a' * 32)
        self.assertEqual(saves[-1]['replacements'][0]['state'], 'PREPARED_BEFORE_JOB_PUBLICATION')
        self.assertIs(rt.atomic, atomic)

    def test_unexpected_create_write_is_blocked(self):
        state, rt, old, link, save, writes, saves, atomic = self.fixture(unexpected=True)
        with patch.object(M, 'STATE', state), self.assertRaisesRegex(RuntimeError, 'UNEXPECTED_CREATE_WRITE'):
            M.submit_linked(rt, old, link, save)
        self.assertEqual(writes, [])
        self.assertIs(rt.atomic, atomic)

    def test_normalization_change_prevents_submission(self):
        state, rt, old, link, save, writes, saves, atomic = self.fixture()
        rt.validate_request = lambda data: {**data, 'seed': 456}
        with patch.object(M, 'STATE', state), self.assertRaisesRegex(RuntimeError, 'NORMALIZED_REQUEST'):
            M.submit_linked(rt, old, link, save)
        self.assertEqual(writes, []); self.assertEqual(saves, [])


if __name__ == '__main__':
    unittest.main()
