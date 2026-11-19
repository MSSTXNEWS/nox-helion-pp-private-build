"""B0 6V14-04: durable receipt rename after metadata fsync; source-only."""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import work_progress as progress


class DurableReceiptPublishTests(unittest.TestCase):
    def test_file_then_directory_are_synced_before_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            target = directory / 'work_receipts.json'
            observed = []
            original_fsync = os.fsync

            def track(fd):
                observed.append('directory' if stat.S_ISDIR(os.fstat(fd).st_mode) else 'file')
                return original_fsync(fd)

            with patch.object(progress.os, 'fsync', side_effect=track):
                progress.save_receipt_payload(directory, target, {'tasks': {'0A04': {'state': 'verified'}}})
            self.assertEqual(observed, ['file', 'directory'])
            self.assertEqual(json.loads(target.read_text())['tasks']['0A04']['state'], 'verified')

    def test_directory_fsync_error_is_not_reported_as_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            target = directory / 'work_receipts.json'
            original_fsync = os.fsync

            def fail_directory(fd):
                if stat.S_ISDIR(os.fstat(fd).st_mode):
                    raise OSError(5, 'metadata sync failed')
                return original_fsync(fd)

            with patch.object(progress.os, 'fsync', side_effect=fail_directory):
                with self.assertRaises(OSError):
                    progress.save_receipt_payload(directory, target, {'tasks': {}})
            # Rename may already have succeeded; caller must treat this as unknown/HOLD.
            self.assertEqual(list(directory.glob('tmp*')), [])

    def test_json_error_keeps_old_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            target = directory / 'work_receipts.json'
            target.write_text('{"prior": true}', encoding='utf-8')
            with self.assertRaises(TypeError):
                progress.save_receipt_payload(directory, target, {'unsupported': {1, 2}})
            self.assertEqual(target.read_text(), '{"prior": true}')

    def test_symlinked_directory_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'real'
            directory.mkdir()
            alias = Path(tmp) / 'alias'
            alias.symlink_to(directory, target_is_directory=True)
            with self.assertRaises(OSError):
                progress.save_receipt_payload(alias, alias / 'work_receipts.json', {'tasks': {}})


    def test_replace_uses_same_pinned_directory_for_both_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            target = directory / 'work_receipts.json'
            actual_replace = os.replace
            observed = []

            def track(src, dst, **kwargs):
                observed.append((src, dst, kwargs.copy()))
                return actual_replace(src, dst, **kwargs)

            with patch.object(progress.os, 'replace', side_effect=track):
                progress.save_receipt_payload(directory, target, {'tasks': {}})
            self.assertEqual(len(observed), 1)
            src, dst, kw = observed[0]
            self.assertTrue(src.startswith('.work_receipts.'))
            self.assertEqual(dst, 'work_receipts.json')
            self.assertIsInstance(kw['src_dir_fd'], int)
            self.assertEqual(kw['src_dir_fd'], kw['dst_dir_fd'])

    def test_rebound_path_does_not_publish_into_other_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / 'original'
            moved = root / 'moved'
            decoy = root / 'decoy'
            original.mkdir()
            decoy.mkdir()
            actual_replace = os.replace
            did_rebind = []

            def rebind_then_replace(src, dst, **kwargs):
                if not did_rebind:
                    original.rename(moved)
                    original.symlink_to(decoy, target_is_directory=True)
                    did_rebind.append(True)
                return actual_replace(src, dst, **kwargs)

            with patch.object(progress.os, 'replace', side_effect=rebind_then_replace):
                progress.save_receipt_payload(original, original / 'work_receipts.json',
                                              {'schema': 'nox-work-receipts-v1', 'tasks': {}})
            self.assertEqual(len(did_rebind), 1)
            self.assertTrue((moved / 'work_receipts.json').is_file())
            self.assertFalse((decoy / 'work_receipts.json').exists())
            self.assertEqual(list(moved.glob('.work_receipts.*.tmp')), [])

    def test_rejects_target_outside_pinned_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            safe = root / 'safe'
            decoy = root / 'decoy'
            safe.mkdir()
            decoy.mkdir()
            with self.assertRaisesRegex(ValueError, 'TARGET_OUTSIDE_DIRECTORY'):
                progress.save_receipt_payload(safe, decoy / 'work_receipts.json',
                                              {'tasks': {}})
            self.assertEqual(list(safe.iterdir()), [])
            self.assertEqual(list(decoy.iterdir()), [])

    def test_nonfinite_json_cannot_poison_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            target = directory / 'work_receipts.json'
            target.write_text('{"prior": true}', encoding='utf-8')
            with self.assertRaises(ValueError):
                progress.save_receipt_payload(directory, target, {'unsafe': float('nan')})
            self.assertEqual(target.read_text(), '{"prior": true}')
            self.assertEqual(list(directory.glob('.work_receipts.*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
