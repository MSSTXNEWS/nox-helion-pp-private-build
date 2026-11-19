import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import owner_browser_qa_entry as entry


class BrowserEntryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.area = self.root / 'browser_qa'
        self.area.mkdir()
        for name, value in (('ROOT', self.root), ('AREA', self.area)):
            current = patch.object(entry, name, value)
            current.start(); self.addCleanup(current.stop)

    def test_exact_observed_shared_libraries_map_to_reviewed_packages(self):
        self.assertEqual(set(entry.LIBRARY_PACKAGES), {'libXcomposite.so.1', 'libXdamage.so.1',
                         'libatk-1.0.so.0', 'libatk-bridge-2.0.so.0', 'libatspi.so.0'})
        self.assertIn('libatk1.0-data', entry.RUNTIME_PACKAGES)
        self.assertNotIn('libc6', entry.RUNTIME_PACKAGES)
        self.assertFalse(any('torch' in name or 'cuda' in name or 'nvidia' in name for name in entry.RUNTIME_PACKAGES))

    def test_apt_plan_pins_new_runtime_packages_only(self):
        raw = (b'Inst libatk1.0-data (2.36.0-3build1 Ubuntu:22.04/jammy [all])\n'
               b'Inst libatk1.0-0:amd64 (2.36.0-3build1 Ubuntu:22.04/jammy [amd64])\n'
               b'Conf libatk1.0-data (2.36.0-3build1 Ubuntu:22.04/jammy [all])\n')
        self.assertEqual(entry.apt_plan(raw, ['libatk1.0-0']), [('libatk1.0-data', '2.36.0-3build1'), ('libatk1.0-0', '2.36.0-3build1')])
        for unsafe in (b'Remv libc6 [2.35]\n',
                       b'Inst libatk1.0-0 [2.35] (2.36 Ubuntu:22.04 [amd64])\n',
                       b'Inst cuda-toolkit-12-4 (12.4 CUDA:local [amd64])\n',
                       b'Inst dbus (1.2 Ubuntu:22.04 [amd64])\n'):
            with self.assertRaises(RuntimeError):
                entry.apt_plan(unsafe, ['libatk1.0-0'])

    def test_no_package_mutation_when_linker_already_passes(self):
        calls = []
        with patch.object(entry, 'browser_binary', return_value=Path('/safe/chrome')), patch.object(entry, 'missing_libraries', return_value=[]), patch.object(entry, 'run', side_effect=lambda *args: calls.append(args)), patch.object(entry, 'emit'):
            entry.install_runtime_libraries({})
        self.assertEqual(calls, [])

    def test_unreviewed_library_does_not_trigger_broad_install(self):
        with patch.object(entry, 'browser_binary', return_value=Path('/safe/chrome')), patch.object(entry, 'missing_libraries', return_value=['libunknown.so']), patch.object(entry, 'apt_context') as context:
            with self.assertRaisesRegex(RuntimeError, 'UNREVIEWED_SHARED_LIBRARY'):
                entry.install_runtime_libraries({})
            context.assert_not_called()

    def test_install_then_linker_and_exact_version_readback_before_acceptance(self):
        calls = []
        plan = b'Inst libxcomposite1 (1:0.4.5-1build2 Ubuntu:22.04/jammy [amd64])\n'
        def fake_run(argv, env, timeout, tag):
            calls.append((argv, env, timeout, tag))
            if tag == 'ARCH':
                return b'amd64\n'
            if tag == 'APT_PLAN':
                return plan
            if tag == 'APT_VERIFY':
                return b'libxcomposite1:amd64\t1:0.4.5-1build2\tinstalled\n'
            return b''
        with patch.object(entry, 'browser_binary', return_value=Path('/safe/chrome')), patch.object(entry, 'missing_libraries', side_effect=[['libXcomposite.so.1'], []]), patch.object(entry, 'apt_context', return_value=['-o', 'Dir::Etc::sourceparts=-']), patch.object(entry, 'run', fake_run), patch.object(entry.shutil, 'disk_usage', return_value=type('Budget', (), {'free': 20 * 1024**3})()), patch.object(entry, 'emit'):
            entry.install_runtime_libraries({})
        install = next(row for row in calls if row[3] == 'APT_RUNTIME')
        self.assertIn('libxcomposite1=1:0.4.5-1build2', install[0])
        self.assertIn('--no-remove', install[0])
        self.assertIn('--no-upgrade', install[0])
        self.assertIn('--no-install-recommends', install[0])
        self.assertEqual(install[1]['NEEDRESTART_MODE'], 'l')
        marker = self.area / 'owner-system-libraries.json'
        self.assertEqual(marker.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(marker.read_text())['missing_libraries'], [])

    def test_ubuntu_sources_are_isolated_signed_and_no_recommended_daemon(self):
        self.assertEqual(entry.UBUNTU_SOURCES.count('signed-by=/usr/share/keyrings/ubuntu-archive-keyring.gpg'), 3)
        self.assertNotIn('trusted=yes', entry.UBUNTU_SOURCES)
        self.assertNotIn('ppa.launchpad', entry.UBUNTU_SOURCES)
        source = Path(entry.__file__).read_text()
        self.assertNotIn('install-deps', source)
        self.assertNotIn('--with-deps', source)
        self.assertNotIn('--allow-unauthenticated', source)
        self.assertEqual(entry.PIN, hashlib.sha256(Path(entry.__file__).with_name('owner_chat_browser_qa.py').read_bytes()).hexdigest())

    def test_linker_parser_exports_missing_names_only(self):
        raw = b'\tlibXdamage.so.1 => not found\n\tlibc.so.6 => /private/runtime/path/libc.so.6 (0x123)\n'
        with patch.object(entry, 'run', return_value=raw):
            self.assertEqual(entry.missing_libraries(Path('/safe/chrome'), {}), ['libXdamage.so.1'])


if __name__ == '__main__':
    unittest.main()
