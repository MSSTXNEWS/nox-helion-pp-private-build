"""Offline regression: create only isolated browser QA runtime, never NOX serving."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import owner_browser_stream_only_entry as entry


class BrowserRuntimeBootstrapTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name) / 'nox'
        self.root.mkdir(mode=0o700)
        self.area = self.root / 'browser_qa'
        self.env_spec = dict(entry.ENV_SPEC, base_python=sys.executable)
        self.patches = [
            patch.object(entry, 'ROOT', self.root),
            patch.object(entry, 'AREA', self.area),
            patch.object(entry, 'ENV_SPEC', self.env_spec),
            patch.object(entry, 'resource_budget', return_value={'bounded': True}),
            patch.object(entry, 'stop_present', return_value=False),
            patch.object(entry.shutil, 'disk_usage', return_value=SimpleNamespace(free=20*1024**3)),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.calls = []

    def install_stub(self, args, env, hold_code, timeout_sec=180):
        self.calls.append((list(args), dict(env), hold_code))
        # No external processes, network access or browser downloads in tests.
        if hold_code == 'VENV':
            target = Path(args[-1])
            (target / 'bin').mkdir(parents=True)
            python = target / 'bin/python'
            python.write_text('# mock executable\n')
            python.chmod(0o700)

    def test_missing_environment_restores_private_qa_runtime(self):
        with patch.object(entry, '_checked_install', side_effect=self.install_stub):
            python, newly_created = entry.ensure_runtime('7014919240')
        self.assertTrue(newly_created)
        self.assertEqual(python, self.area / 'venv/bin/python')
        self.assertEqual(json.loads((self.area/'owner-environment.json').read_text()), self.env_spec)
        self.assertEqual((self.area/'owner-environment.json').stat().st_mode & 0o777, 0o600)
        self.assertEqual([c[2] for c in self.calls], ['VENV','PIP','CHROMIUM','VERSION'])
        pip = self.calls[1][0]
        self.assertIn('playwright==1.65.2', pip)
        self.assertIn('--only-binary=:all:', pip)
        self.assertEqual(self.calls[2][0][-2:], ['install', 'chromium'])
        self.assertEqual(self.calls[2][1]['PLAYWRIGHT_BROWSERS_PATH'],
                         self.calls[1][1]['PLAYWRIGHT_BROWSERS_PATH'])
        self.assertEqual(list(self.root.glob('.nox-browserqa-*')), [])

    def test_incomplete_old_qa_is_preserved_without_overwrite(self):
        self.area.mkdir(mode=0o700)
        previous = self.area / 'original-user-file'
        previous.write_text('do not delete')
        with patch.object(entry, '_checked_install', side_effect=self.install_stub):
            _, repaired = entry.ensure_runtime('7014919250')
        self.assertTrue(repaired)
        self.assertEqual((self.root/'browser_qa.previous.7014919250'/'original-user-file').read_text(),
                         'do not delete')
        self.assertFalse((self.area/'original-user-file').exists())

    def test_existing_valid_qa_does_not_download_again(self):
        self.area.mkdir(mode=0o700)
        (self.area/'venv/bin').mkdir(parents=True)
        exe = self.area/'venv/bin/python'
        exe.write_text('mock executable')
        exe.chmod(0o700)
        marker=self.area/'owner-environment.json'
        marker.write_text(json.dumps(self.env_spec))
        marker.chmod(0o600)
        with patch.object(entry, '_checked_install', side_effect=AssertionError('unexpected download')):
            resolved, repaired = entry.ensure_runtime('7014919260')
        self.assertEqual(resolved, exe)
        self.assertFalse(repaired)

    def test_install_failure_does_not_destroy_old_area(self):
        self.area.mkdir(mode=0o700)
        previous=self.area/'important_file'
        previous.write_text('preserved')
        def fail(*args,**kwargs):
            raise RuntimeError('HOLD_BROWSER_BOOTSTRAP_PIP')
        with patch.object(entry, '_checked_install', side_effect=fail):
            with self.assertRaisesRegex(RuntimeError, 'HOLD_BROWSER_BOOTSTRAP_PIP'):
                entry.ensure_runtime('7014919270')
        self.assertEqual(previous.read_text(), 'preserved')
        self.assertEqual(list(self.root.glob('.nox-browserqa-*')), [])


if __name__ == '__main__':
    unittest.main()
