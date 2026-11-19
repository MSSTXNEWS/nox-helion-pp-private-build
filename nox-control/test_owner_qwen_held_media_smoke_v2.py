import ast
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


HERE = Path(__file__).parent
def load(name):
    spec = importlib.util.spec_from_file_location('_test_' + name, HERE / (name + '.py'))
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value

old = load('owner_qwen_held_media_smoke')
m = load('owner_qwen_held_media_smoke_v2')
runtime = load('owner_media_runtime')
JOB = 'a' * 32


class InventoryDeltaTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for value, attr, path in ((runtime, 'ROOT', self.root), (m, 'STATE', self.root / 'state'),
                                  (old, 'STATE', self.root / 'state')):
            patch = mock.patch.object(value, attr, path); patch.start(); self.addCleanup(patch.stop)
        self.row = {'schema': 'NOX_OWNER_MEDIA_JOB_V1', 'id': JOB, 'state': 'RUNNING', 'request': {}}
        runtime.atomic(runtime.job_path(JOB), self.row)
        # Exercise the actual frozen ca8 writer, solely inside this temp tree.
        runtime.update_job(self.row, state='COMPLETED')
        self.job = runtime.job_path(JOB); self.lock = self.job.with_suffix('.lock')

    def test_actual_ca8_persistent_lock_reproduces_original_hold_and_v2_accepts_inventory(self):
        self.assertEqual(hashlib.sha256((HERE / 'owner_media_runtime.py').read_bytes()).hexdigest(),
                         'ca8ce2466d0ee4321e17bbf2dc26a6f6396bafb93f3df361a1b35a7e8e3347e5')
        self.assertTrue(self.lock.is_file()); self.assertEqual(self.lock.stat().st_size, 0)
        with self.assertRaisesRegex(old.SmokeHold, 'JOB_INVENTORY'):
            old.no_other_jobs(runtime)
        before = {p.name: p.read_bytes() for p in self.job.parent.iterdir()}
        m.no_other_jobs(runtime)
        self.assertEqual({p.name: p.read_bytes() for p in self.job.parent.iterdir()}, before)

    def test_active_job_is_still_blocked_despite_valid_lock(self):
        runtime.update_job(self.row, state='QUEUED')
        with self.assertRaisesRegex(m.SmokeHold, 'OTHER_OWNER_JOB'):
            m.no_other_jobs(runtime)
        m.no_other_jobs(runtime, JOB)

    def test_lock_requires_its_actual_valid_json_record(self):
        self.job.unlink()
        with self.assertRaisesRegex(m.SmokeHold, 'JOB_LOCK_WITHOUT_RECORD'):
            m.no_other_jobs(runtime)
        runtime.atomic(self.job, {'schema': 'OTHER', 'id': JOB, 'state': 'COMPLETED'})
        with self.assertRaisesRegex(m.SmokeHold, 'JOB_INVENTORY_STATE'):
            m.no_other_jobs(runtime)

    def test_nonempty_or_nonprivate_lock_is_never_skipped(self):
        self.lock.write_bytes(b'foreign')
        with self.assertRaises(m.SmokeHold):
            m.no_other_jobs(runtime)
        self.lock.write_bytes(b''); self.lock.chmod(0o644)
        with self.assertRaisesRegex(m.SmokeHold, 'PRIVATE_FILE'):
            m.no_other_jobs(runtime)

    def test_hardlinked_or_symlink_lock_is_never_skipped(self):
        external = self.root / 'retained-lock'; os.link(self.lock, external)
        with self.assertRaisesRegex(m.SmokeHold, 'PRIVATE_FILE'):
            m.no_other_jobs(runtime)
        external.unlink(); self.lock.unlink(); self.lock.symlink_to(external)
        with self.assertRaisesRegex(m.SmokeHold, 'PATH'):
            m.no_other_jobs(runtime)

    def test_atomic_write_waits_and_unknown_files_continue_to_hold(self):
        temp = self.job.parent / '.media-abcdefgh'; temp.write_bytes(b'')
        with self.assertRaisesRegex(m.SmokeHold, '^WAIT_QWEN_HELD_MEDIA_ATOMIC_JOB_WRITE$'):
            m.no_other_jobs(runtime)
        temp.unlink(); unknown = self.job.parent / 'unrelated.lock'; unknown.write_bytes(b'')
        with self.assertRaisesRegex(m.SmokeHold, 'JOB_INVENTORY'):
            m.no_other_jobs(runtime)

    def test_entry_count_includes_locks_and_temporary_metadata(self):
        with os.scandir(self.job.parent) as entries:
            entry = next(item for item in entries if item.name == self.lock.name)
        context = mock.MagicMock(); context.__enter__.return_value = iter([entry] * 451)
        with mock.patch.object(m.os, 'scandir', return_value=context):
            with self.assertRaisesRegex(m.SmokeHold, '^HOLD_QWEN_HELD_MEDIA_JOB_INVENTORY$'):
                m.no_other_jobs(runtime)


class InverseTests(unittest.TestCase):
    def test_only_inventory_function_changes_and_journal_identity_is_unchanged(self):
        original = (HERE / 'owner_qwen_held_media_smoke.py').read_bytes()
        revised = (HERE / 'owner_qwen_held_media_smoke_v2.py').read_bytes()
        self.assertEqual(hashlib.sha256(original).hexdigest(),
                         '51b42fef5455fd041a2cadb19c8ca86b3e35e7ad45b2315cdbe4ae5b82d24200')
        def section(value):
            start = value.index(b'def no_other_jobs(')
            end = value.index(b'\n\ndef ready_to_submit(', start)
            return start, end
        a,b = section(original); c,d = section(revised)
        self.assertEqual(revised[:c] + original[a:b] + revised[d:], original)
        def without_inventory(value):
            tree = ast.parse(value)
            tree.body = [n for n in tree.body if not isinstance(n,ast.FunctionDef) or n.name!='no_other_jobs']
            return ast.dump(tree, include_attributes=False)
        self.assertEqual(without_inventory(revised), without_inventory(original))
        self.assertEqual(m.AREA, old.AREA); self.assertEqual(m.FIXTURE, old.FIXTURE)
        self.assertEqual(m.SCHEMA, old.SCHEMA); self.assertEqual(m.PINS, old.PINS)
        self.assertEqual(m.ROLLBACK_AREA, old.ROLLBACK_AREA)


if __name__ == '__main__':
    unittest.main()
