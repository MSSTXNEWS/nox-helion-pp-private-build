"""B5/5B01: original helper with real POSIX cross-process flock and durable file I/O.

SOURCE ONLY, NO LIVE MEDIA/ONEHOST INVOCATION.
"""
import contextlib
import fcntl
import json
import multiprocessing as mp
import os
from pathlib import Path
import secrets
import tempfile
import time
import unittest

from owner_media_idempotency import create_or_resume, IdempotencyHold

KEY = 'a' * 32
REQUEST = {'client_request_id': KEY, 'kind': 'image', 'prompt': 'stable prompt', 'width': 1024, 'height': 1024}


def durable_atomic(target, obj):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.' + secrets.token_hex(8) + '.tmp')
    try:
        with open(temporary, 'x', encoding='utf-8') as f:
            json.dump(obj, f, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, target)
        fd = os.open(target.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try: os.fsync(fd)
        finally: os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


@contextlib.contextmanager
def file_lease(path):
    with open(path, 'a+b') as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(fh, fcntl.LOCK_UN)


def create(root, owner, body=REQUEST, crash_after_job=False):
    root = Path(root)
    jobs, inbox = root / 'jobs', root / 'inbox'
    jobs.mkdir(exist_ok=True)
    inbox.mkdir(exist_ok=True)

    def read(path):
        try:
            return json.loads(Path(path).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None

    def atomic(path, data):
        if crash_after_job and Path(path).parent == inbox:
            raise OSError('INJECTED_AFTER_DURABLE_JOB_BEFORE_INBOX')
        durable_atomic(path, data)

    def new_job(normalized):
        # Process-independent unique ID: two creations yield different IDs.
        return {'id': secrets.token_hex(16), 'owner': owner,
                'request': normalized, 'state': 'QUEUED'}

    job = create_or_resume(body, owner,
        lock=lambda: file_lease(root / 'jobs.lock'), jobs_dir=jobs,
        inbox_dir=inbox, read_json=read, atomic=atomic,
        preflight=lambda _: time.sleep(0.005), new_job=new_job)
    return job['id']


def worker(root, owner, barrier, queue, body=REQUEST):
    try:
        barrier.wait(timeout=15)
        queue.put(('ok', create(root, owner, body)))
    except Exception as exc:
        queue.put(('error', type(exc).__name__, str(exc)))


class TestMultiprocessDurability(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_six_competing_processes_one_durable_job(self):
        ctx = mp.get_context('spawn')
        queue = ctx.Queue()
        gate = ctx.Barrier(6)
        procs = [ctx.Process(target=worker, args=(str(self.root), 'owner-A', gate, queue)) for _ in range(6)]
        for process in procs: process.start()
        for process in procs:
            process.join(20)
            if process.is_alive():
                process.terminate(); process.join(2)
            self.assertEqual(process.exitcode, 0)
        rows = [queue.get(timeout=3) for _ in procs]
        self.assertTrue(all(row[0] == 'ok' for row in rows), rows)
        self.assertEqual(len({row[1] for row in rows}), 1)
        job_id = rows[0][1]
        self.assertEqual(len(list((self.root / 'jobs').glob('*.json'))), 1)
        self.assertEqual(json.loads((self.root / 'inbox' / (job_id + '.json')).read_text()), {'job_id': job_id})
        self.assertEqual(json.loads((self.root / 'jobs' / (job_id + '.json')).read_text())['owner'], 'owner-A')

    def test_new_process_recovers_after_durable_job_but_no_inbox(self):
        with self.assertRaisesRegex(OSError, 'INJECTED_AFTER_DURABLE_JOB_BEFORE_INBOX'):
            create(self.root, 'owner-A', crash_after_job=True)
        rows = list((self.root / 'jobs').glob('*.json'))
        self.assertEqual(len(rows), 1)
        first_id = rows[0].stem
        ctx = mp.get_context('spawn')
        queue = ctx.Queue(); gate = ctx.Barrier(1)
        process = ctx.Process(target=worker, args=(str(self.root), 'owner-A', gate, queue))
        process.start(); process.join(20)
        if process.is_alive(): process.terminate(); process.join(2)
        self.assertEqual(process.exitcode, 0)
        self.assertEqual(queue.get(timeout=3), ('ok', first_id))
        self.assertEqual(len(list((self.root / 'jobs').glob('*.json'))), 1)
        self.assertEqual(json.loads((self.root/'inbox'/(first_id+'.json')).read_text()), {'job_id':first_id})

    def test_owner_isolation_and_conflict_are_still_durable(self):
        first = create(self.root, 'owner-A')
        second = create(self.root, 'owner-B')
        self.assertNotEqual(first, second)
        self.assertEqual(create(self.root, 'owner-A'), first)
        with self.assertRaisesRegex(IdempotencyHold, 'CONFLICT'):
            create(self.root, 'owner-A', {**REQUEST, 'prompt': 'changed'})
        self.assertEqual(len(list((self.root / 'jobs').glob('*.json'))), 2)


if __name__ == '__main__': unittest.main()
