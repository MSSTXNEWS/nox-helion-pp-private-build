import importlib.util
import os
from pathlib import Path
import tempfile
import unittest


SOURCE = Path(__file__).with_name('owner_systemic_relay_observe.py')
SPEC = importlib.util.spec_from_file_location('owner_systemic_relay_observe_test', SOURCE)
observe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observe)


class ProjectLedgerHashSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ledger_dir = self.root / 'state/dispatcher'
        self.ledger_dir.mkdir(parents=True)
        for name in observe.PROJECT_LEDGER_NAMES:
            (self.ledger_dir / name).write_bytes((name + '\n').encode())

    def tearDown(self):
        self.temp.cleanup()

    def test_stable_snapshot_is_hash_and_metadata_only(self):
        result = observe.project_ledger_hash_snapshot(root=self.root)
        self.assertEqual(tuple(result), observe.PROJECT_LEDGER_NAMES)
        for name, row in result.items():
            self.assertEqual(set(row), {'sha256', 'size_bytes', 'mtime_ns', 'device', 'inode'})
            self.assertEqual(row['size_bytes'], len((self.ledger_dir / name).read_bytes()))
            self.assertEqual(len(row['sha256']), 64)
            self.assertNotIn('content', row)

    def test_concurrent_mutation_mid_read_holds_snapshot(self):
        target = self.ledger_dir / observe.PROJECT_LEDGER_NAMES[0]
        target.write_bytes(b'a' * 131072)
        original_read = observe.os.read
        changed = False

        def read_then_mutate(fd, count):
            nonlocal changed
            data = original_read(fd, count)
            if data and not changed:
                changed = True
                with target.open('ab') as writer:
                    writer.write(b'changed')
                    writer.flush()
                    os.fsync(writer.fileno())
            return data

        observe.os.read = read_then_mutate
        try:
            with self.assertRaisesRegex(ValueError, 'HOLD_LEDGER_CHANGED'):
                observe.project_ledger_hash_snapshot(root=self.root)
        finally:
            observe.os.read = original_read
        self.assertTrue(changed)

    def test_symlink_ledger_holds_snapshot(self):
        target = self.ledger_dir / observe.PROJECT_LEDGER_NAMES[0]
        replacement = self.ledger_dir / 'outside.json'
        target.rename(replacement)
        target.symlink_to(replacement.name)
        with self.assertRaises(OSError):
            observe.project_ledger_hash_snapshot(root=self.root)

    def test_size_bound_holds_snapshot(self):
        (self.ledger_dir / observe.PROJECT_LEDGER_NAMES[0]).write_bytes(b'x' * 1025)
        with self.assertRaisesRegex(ValueError, 'HOLD_LEDGER_TYPE_OR_SIZE'):
            observe.project_ledger_hash_snapshot(root=self.root, limit=1024)

    def test_time_bound_holds_snapshot(self):
        original_monotonic = observe.time.monotonic
        ticks = iter((0.0, 2.0))
        observe.time.monotonic = lambda: next(ticks)
        try:
            with self.assertRaisesRegex(ValueError, 'HOLD_LEDGER_TIME_BOUND'):
                observe.project_ledger_hash_snapshot(root=self.root, max_seconds=1.0)
        finally:
            observe.time.monotonic = original_monotonic


if __name__ == '__main__':
    unittest.main()
