import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import owner_browser_runtime_inspect as inspect


class RuntimeInspectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.area = Path(self.temp.name) / 'browser_qa'; self.area.mkdir(mode=0o700)
        (self.area / 'venv/bin').mkdir(parents=True)
        self.marker = self.area / 'owner-environment.json'
        self.marker.write_text(json.dumps(inspect.SPEC)); self.marker.chmod(0o600)
        self.target = self.area / 'known-python'; self.target.write_bytes(b'\x7fELFsynthetic'); self.target.chmod(0o700)
        (self.area / 'venv/bin/python').symlink_to(self.target)
        patched = patch.object(inspect, 'AREA', self.area); patched.start(); self.addCleanup(patched.stop)

    def test_unsafe_exact_directory_is_reported_and_no_interpreter_or_mutation(self):
        folder = self.area / 'venv'; folder.chmod(0o775)
        before = {p: (p.lstat().st_mode, p.lstat().st_ino, p.lstat().st_size) for p in (folder, self.marker, self.target)}
        with patch.object(inspect.subprocess, 'run') as run:
            result = inspect.snapshot()
        self.assertEqual(result['failing_original_directory_labels'], ['VENV'])
        self.assertEqual(result['directories']['VENV']['mode_octal'], '0775')
        self.assertFalse(result['original_runtime_gate_passes'])
        self.assertFalse(result['interpreter_version_probe']['executed']); run.assert_not_called()
        self.assertEqual(before, {p: (p.lstat().st_mode, p.lstat().st_ino, p.lstat().st_size) for p in before})
        self.assertEqual(result['native_chat_posts'], 0)

    def test_marker_unexpected_fields_are_hashed_but_never_exported(self):
        self.marker.write_text(json.dumps({**inspect.SPEC, 'PRIVATE_TOKEN': 'SECRET', 'playwright': 'PRIVATE_VERSION'}))
        result = inspect.marker_record(); text = json.dumps(result)
        self.assertFalse(result['exact_expected_marker']); self.assertFalse(result['original_marker_gate_passes'])
        self.assertEqual(result['declared_playwright_version'], 'UNEXPECTED')
        for value in ('SECRET', 'PRIVATE_TOKEN', 'PRIVATE_VERSION', str(self.area)):
            self.assertNotIn(value, text)

    def test_symlink_target_path_not_exported_and_parent_symlink_not_followed(self):
        result = inspect.python_record()
        self.assertTrue(result['target_regular']); self.assertTrue(result['target_elf_header'])
        self.assertEqual(len(result['resolved_target_path_sha256']), 64)
        self.assertNotIn(str(self.area), json.dumps(result))
        old = self.area / 'venv/bin'; renamed = self.area / 'venv/bin-old'; old.rename(renamed); old.symlink_to(renamed)
        blocked = inspect.directory_record(old, False)
        self.assertFalse(blocked['original_directory_gate_passes'])

    def test_missing_marker_is_metadata_hold_without_runtime_creation(self):
        self.marker.unlink()
        with patch.object(inspect.subprocess, 'run') as run:
            result = inspect.snapshot()
        self.assertFalse(result['original_runtime_gate_passes']); run.assert_not_called()
        self.assertFalse(self.marker.exists())

    def test_python_nonregular_target_is_not_opened(self):
        python = self.area / 'venv/bin/python'; python.unlink()
        fifo = self.area / 'not-python'; os.mkfifo(fifo); python.symlink_to(fifo)
        original = inspect.os.open
        def no_fifo_open(path, *args, **kwargs):
            self.assertNotEqual(path, fifo)
            return original(path, *args, **kwargs)
        with patch.object(inspect.os, 'open', side_effect=no_fifo_open):
            result = inspect.python_record()
        self.assertEqual(result['read_state'], 'TARGET_NOT_REGULAR')
        self.assertFalse(result['original_python_gate_passes'])


if __name__ == '__main__':
    unittest.main()
