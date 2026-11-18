"""Focused source-only integration gate for the existing authenticated NOX media create."""
import fcntl
import json
import threading
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import owner_media_runtime as media


class MediaCreateDedupIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.patchers = [
            patch.object(media, 'ROOT', self.root),
            patch.object(media, 'capabilities', return_value={'image': True, 'video': True}),
        ]
        for p in self.patchers:
            p.start()
            self.addCleanup(p.stop)
        (self.root / 'state/media/jobs').mkdir(parents=True)
        (self.root / 'state/media/inbox').mkdir(parents=True)

    @staticmethod
    def body(key='a' * 32, prompt='test image'):
        return {'client_request_id': key, 'kind': 'image', 'prompt': prompt}

    def test_replay_returns_one_stored_job_even_without_engine(self):
        first = media.create_job(self.body(), 'alice')
        with patch.object(media, 'capabilities', side_effect=AssertionError('must not probe on replay')):
            replay = media.create_job(self.body(), 'alice')
        self.assertEqual(first['id'], replay['id'])
        self.assertEqual(len(list((self.root/'state/media/jobs').glob('*.json'))), 1)

    def test_mismatch_fails_without_second_job(self):
        media.create_job(self.body(), 'alice')
        with self.assertRaisesRegex(media.MediaHold, 'IDEMPOTENCY_CONFLICT'):
            media.create_job(self.body(prompt='different'), 'alice')
        self.assertEqual(len(list((self.root/'state/media/jobs').glob('*.json'))), 1)

    def test_owner_scoped_lookup(self):
        one = media.create_job(self.body(), 'alice')
        two = media.create_job(self.body(), 'bob')
        self.assertNotEqual(one['id'], two['id'])
        self.assertEqual(media.lookup_media_request('alice', 'a'*32)['id'], one['id'])
        with self.assertRaisesRegex(media.MediaHold, 'MEDIA_JOB_NOT_FOUND'):
            media.lookup_media_request('charlie', 'a'*32)

    def test_repair_unknown_post_inbox_without_duplicate(self):
        first = media.create_job(self.body(), 'alice')
        inbox = self.root/'state/media/inbox'/(first['id']+'.json')
        inbox.unlink()
        replay = media.create_job(self.body(), 'alice')
        self.assertEqual(replay['id'], first['id'])
        self.assertEqual(json.loads(inbox.read_text()), {'job_id': first['id']})

    def test_legacy_unkeyed_supported(self):
        self.assertNotEqual(media.create_job({'kind':'image','prompt':'same'},'alice')['id'],
                            media.create_job({'kind':'image','prompt':'same'},'alice')['id'])

    def test_old_inbox_records_do_not_starve_a_new_job(self):
        # Real inbox files are durable even after the task is integrated;
        # three lexically earlier stale entries must not hide the next job.
        inbox = self.root / 'state/media/inbox'
        for char in ('0', '1', '2'):
            job_id = char * 32
            media.atomic(media.job_path(job_id), {
                'id': job_id, 'state': 'COMPLETED', 'request': {'kind': 'image'}})
            media.atomic(inbox / (job_id + '.json'), {'job_id': job_id})
        fresh = 'f' * 32
        media.atomic(media.job_path(fresh), {
            'id': fresh, 'state': 'QUEUED', 'request': {'kind': 'image'}})
        media.atomic(inbox / (fresh + '.json'), {'job_id': fresh})
        state = {'tasks': {}}
        self.assertEqual(media.ingest_media_tasks(state), 1)
        self.assertIn('owner.media.' + fresh, state['tasks'])
        self.assertEqual(len(list(inbox.glob('*.json'))), 4)

    def test_orphan_inbox_cannot_starve_valid_job(self):
        # The orphan receipt remains untouched for manual reconciliation.
        inbox = self.root / 'state/media/inbox'
        missing_id, valid_id = '0' * 32, 'f' * 32
        media.atomic(inbox / (missing_id + '.json'), {'job_id': missing_id})
        media.atomic(media.job_path(valid_id), {
            'id': valid_id, 'state': 'QUEUED', 'request': {'kind': 'image'}})
        media.atomic(inbox / (valid_id + '.json'), {'job_id': valid_id})
        state = {'tasks': {}}
        self.assertEqual(media.ingest_media_tasks(state), 1)
        self.assertIn('owner.media.' + valid_id, state['tasks'])
        self.assertEqual(len(list(inbox.glob('*.json'))), 2)
        self.assertFalse(media.job_path(missing_id).exists())

    def test_existing_corrupt_job_does_not_bypass_hold(self):
        # Missing and unreadable are different. Do not mask damaged S03.
        bad_id, valid_id = '0' * 32, 'f' * 32
        inbox = self.root / 'state/media/inbox'
        (media.job_path(bad_id)).write_text('{not-json')
        media.atomic(inbox / (bad_id + '.json'), {'job_id': bad_id})
        media.atomic(media.job_path(valid_id), {
            'id': valid_id, 'state': 'QUEUED', 'request': {'kind': 'image'}})
        media.atomic(inbox / (valid_id + '.json'), {'job_id': valid_id})
        with self.assertRaisesRegex(media.MediaHold, 'MEDIA_JOB_NOT_FOUND'):
            media.ingest_media_tasks({'tasks': {}})
        self.assertEqual(len(list(inbox.glob('*.json'))), 2)

    def test_invalid_id_fails_closed(self):
        with self.assertRaisesRegex(media.MediaHold, 'INVALID_MEDIA_CLIENT_REQUEST_ID'):
            media.create_job(self.body(key='../'), 'alice')

    def test_actual_runtime_lock_waits_for_short_competing_commit(self):
        # Exercise the production lock path, not the blocking helper test lease.
        lock_path = self.root / 'state/media/jobs.lock'
        with lock_path.open('a+b') as guard:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            released = threading.Event()
            def release():
                fcntl.flock(guard, fcntl.LOCK_UN)
                released.set()
            timer = threading.Timer(0.06, release)
            timer.start()
            try:
                job = media.create_job(self.body(), 'alice')
            finally:
                timer.join(timeout=1)
                fcntl.flock(guard, fcntl.LOCK_UN)
        self.assertTrue(released.is_set())
        self.assertEqual(media.lookup_media_request('alice', 'a' * 32)['id'], job['id'])
        self.assertEqual(len(list((self.root / 'state/media/jobs').glob('*.json'))), 1)

    def test_actual_runtime_lock_timeout_does_not_commit_partial_job(self):
        lock_path = self.root / 'state/media/jobs.lock'
        with lock_path.open('a+b') as guard:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(media.MediaHold, 'WAIT_RESOURCE_LEASE'):
                media.create_job(self.body(), 'alice')
            self.assertEqual(list((self.root / 'state/media/jobs').glob('*.json')), [])
            fcntl.flock(guard, fcntl.LOCK_UN)
        # A subsequent deliberate owner operation with the SAME pinned key
        # can reconcile safely: no second job can be created for that key.
        first = media.create_job(self.body(), 'alice')
        self.assertEqual(media.create_job(self.body(), 'alice')['id'], first['id'])
        self.assertEqual(len(list((self.root / 'state/media/jobs').glob('*.json'))), 1)

    def test_durable_job_missing_or_corrupt_never_recreated_from_worker_cache(self):
        # The old "read_json(path) or job" fallback rewrote missing/corrupt
        # durable records from an obsolete in-memory copy. That loses evidence.
        for mode, key in (('missing', 'b' * 32), ('corrupt', 'c' * 32)):
            with self.subTest(mode=mode):
                cached = media.create_job(self.body(key=key), 'alice')
                record = media.job_path(cached['id'])
                if mode == 'missing':
                    record.unlink()
                else:
                    record.write_text('{invalid-json')
                before = record.read_bytes() if record.exists() else None
                with self.assertRaisesRegex(media.MediaHold, 'HOLD_MEDIA_JOB_STATE_UNREADABLE'):
                    media.update_job(cached, state='COMPLETED')
                after = record.read_bytes() if record.exists() else None
                self.assertEqual(after, before)
                self.assertEqual(cached['state'], 'QUEUED')


if __name__ == '__main__':
    unittest.main()
