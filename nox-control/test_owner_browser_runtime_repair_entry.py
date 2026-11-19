import base64
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

import owner_browser_runtime_inspect as diag
import owner_browser_runtime_repair_entry as entry


class ModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.area = self.root / 'browser_qa'; self.area.mkdir(mode=0o700)
        (self.area / 'venv/bin').mkdir(parents=True)
        for path in (self.area / 'venv', self.area / 'venv/bin'):
            path.chmod(0o775)
        marker = self.area / 'owner-environment.json'; marker.write_text(json.dumps(diag.SPEC)); marker.chmod(0o600)
        self.target = self.root / 'python-target'; self.target.write_bytes(b'\x7fELFfixture'); self.target.chmod(0o755)
        link = self.area / 'venv/bin/python'; link.symlink_to(self.target)
        self.paths = {'AREA': self.area, 'VENV': self.area / 'venv', 'BIN': self.area / 'venv/bin',
                      'MARKER': marker, 'PYTHON_LINK': link, 'PYTHON_TARGET': self.target}
        expected = {label: (str(p.lstat().st_dev), str(p.lstat().st_ino), p.lstat().st_size,
                            str(p.lstat().st_mtime_ns)) for label, p in self.paths.items()}
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        for name, value in {'AREA': self.area, 'EXPECTED': expected,
                'OWNER_UID': os.geteuid(), 'OWNER_GID': os.getegid(),
                'MARKER_SHA': hashlib.sha256(marker.read_bytes()).hexdigest(),
                'TARGET_PATH_SHA': hashlib.sha256(os.fsencode(str(self.target))).hexdigest()}.items():
            self.stack.enter_context(patch.object(entry, name, value))
        self.objects, self.handles = entry.open_objects(diag)
        self.addCleanup(lambda: [os.close(fd) for fd in reversed(self.handles)])

    def test_exact_two_modes_only_preserve_marker_target_inode_mtime(self):
        before = {label: entry.metadata(path.lstat()) for label, path in self.paths.items()}
        changed = []; entry.repair_modes(self.objects, changed)
        self.assertEqual(changed, ['VENV', 'BIN'])
        for label, path in self.paths.items():
            after = entry.metadata(path.lstat())
            if label in changed:
                self.assertEqual(after['mode_octal'], '0755')
                self.assertEqual({k: v for k, v in after.items() if k not in ('mode_octal', 'ctime_ns')},
                    {k: v for k, v in before[label].items() if k not in ('mode_octal', 'ctime_ns')})
            else:
                self.assertEqual(after, before[label])

    def test_live_mutation_is_not_hidden_by_historical_ctime_tolerance(self):
        # Fresh same-mode chmod changes ctime, which is accepted by historical
        # known() but rejected against this action's already-open live snapshot.
        path = self.paths['VENV']; path.chmod(0o775)
        entry.known('VENV', path.stat())
        with self.assertRaisesRegex(RuntimeError, 'VENV_BEFORE_CHANGED'):
            entry.repair_modes(self.objects, [])

    def test_second_chmod_failure_can_restore_only_our_first_change(self):
        original = entry.os.fchmod; changed = []
        def fail_second(fd, mode):
            if fd == self.objects['BIN']['fd'] and mode == 0o755:
                raise OSError('synthetic setup failure')
            original(fd, mode)
        with patch.object(entry.os, 'fchmod', side_effect=fail_second):
            with self.assertRaises(OSError):
                entry.repair_modes(self.objects, changed)
        self.assertEqual(changed, ['VENV'])
        self.assertEqual(entry.rollback_modes(self.objects, changed), ['VENV'])
        self.assertEqual(self.paths['VENV'].stat().st_mode & 0o777, 0o775)
        self.assertEqual(self.paths['BIN'].stat().st_mode & 0o777, 0o775)

    def test_foreign_directory_change_is_never_rolled_back(self):
        changed = []; entry.repair_modes(self.objects, changed)
        self.paths['BIN'].chmod(0o750)
        with self.assertRaisesRegex(RuntimeError, 'BIN_OWNER_TYPE_MODE'):
            entry.rollback_modes(self.objects, changed)
        self.assertEqual(self.paths['BIN'].stat().st_mode & 0o777, 0o750)

    def test_same_size_marker_change_blocks_before_any_chmod(self):
        marker = self.paths['MARKER']; raw = marker.read_bytes(); marker.write_bytes(b'X' + raw[1:])
        with patch.object(entry.os, 'fchmod') as chmod, self.assertRaises(RuntimeError):
            entry.repair_modes(self.objects, [])
        chmod.assert_not_called()

    def test_prepared_record_is_private_durable_and_no_replace(self):
        state = self.root / 'state'; state.mkdir(); fd = os.open(state, os.O_RDONLY | os.O_DIRECTORY)
        try:
            value = {'state': 'PREPARED_BEFORE_ANY_PERMISSION_MUTATION'}
            receipt = entry.private_record(fd, 'prepared.json', value)
            self.assertEqual((state / 'prepared.json').stat().st_mode & 0o777, 0o600)
            self.assertEqual(hashlib.sha256((state / 'prepared.json').read_bytes()).hexdigest(), receipt['sha256'])
            self.assertTrue(receipt['readback_verified'])
            with self.assertRaises(FileExistsError):
                entry.private_record(fd, 'prepared.json', {'changed': True})
        finally:
            os.close(fd)

    def run_main(self, setup_failure=False):
        state = self.root / 'state'; state.mkdir(); qa_state = state / 'owner_browser_qa'; qa_state.mkdir(mode=0o700)
        for path in (state / 'owner_maintenance.lock', qa_state / 'qa.lock'):
            path.touch(mode=0o600)
        def check_runtime():
            self.assertEqual((self.area / 'venv').stat().st_mode & 0o777, 0o755)
            if setup_failure:
                raise RuntimeError('HOLD_SYNTHETIC_SETUP_FAILURE')
        qa = types.SimpleNamespace(owner_context=lambda: ('123', 'a' * 40), stop_present=lambda: False,
            resource_budget=lambda: {'synthetic': True}, existing_runtime=check_runtime,
            run_child=lambda *args: 2, emit=lambda *args: None)
        def qa_main():
            result = qa.run_child()
            qa.emit('browser_stream_only_receipt', {'state': 'HOLD', 'reason': 'HOLD_PROGRESSIVE_STREAM_NOT_OBSERVED',
                'native_posts_admitted': 1, 'two_parts_observed': True, 'stream_only_acceptance_verified': False})
            return result
        qa.main = qa_main
        with patch.object(entry, 'ROOT', self.root), patch.object(entry, 'STATE', state), \
             patch.object(entry, 'prepared', return_value=({}, diag, qa, 'b' * 64)), patch.object(entry, 'emit'):
            self.assertEqual(entry.main(), 2)
        return json.loads((state / 'owner_browser_runtime_repair_123.json').read_bytes())

    def test_actual_qa_hold_retains_verified_modes_and_separate_result(self):
        result = self.run_main()
        self.assertEqual(result['state'], 'RUNTIME_PERMISSIONS_VERIFIED_STREAM_ONLY_HOLD')
        self.assertTrue(result['permissions_verified']); self.assertTrue(result['qa_execution_delegated'])
        self.assertFalse(result['qa_acceptance_verified']); self.assertFalse(result['rollback_performed'])
        self.assertTrue(result['prepared_receipt']['readback_verified'])
        self.assertEqual(self.paths['BIN'].stat().st_mode & 0o777, 0o755)
        self.assertEqual(result['qa_observation']['native_posts_admitted'], 1)

    def test_setup_failure_restores_exact_modes_before_qa_delegation(self):
        result = self.run_main(setup_failure=True)
        self.assertEqual(result['state'], 'HOLD'); self.assertTrue(result['rollback_performed'])
        self.assertFalse(result['qa_execution_delegated']); self.assertFalse(result['permissions_verified'])
        self.assertEqual(self.paths['VENV'].stat().st_mode & 0o777, 0o775)
        self.assertEqual(self.paths['BIN'].stat().st_mode & 0o777, 0o775)


class EntryTests(unittest.TestCase):
    def test_exact_six_module_closure_compiles_without_old_installers(self):
        here = Path(__file__).parent
        names = list(entry.PINS) + ['owner_chat_browser_qa.py', 'owner_chat_browser_transport_qa.py',
            'owner_chat_browser_release_qa.py', 'owner_chat_stream_only_qa.py']
        bundle = {name: base64.b64encode((here / name).read_bytes()).decode() for name in names}
        with patch.object(entry, 'BUNDLE', bundle):
            assets, diagnostic, qa, program_sha = entry.prepared()
        self.assertEqual(set(assets), set(names)); self.assertEqual(len(program_sha), 64)
        self.assertEqual(qa.PINS['owner_chat_stream_only_qa.py'], 'd2a426c113f09fb033105d4949ef4e40892a89fbbde43b12f1f804152158779a')
        self.assertNotIn('owner_browser_qa_entry.py', assets)
        bundle[entry.ENTRY] = base64.b64encode(b'changed').decode()
        with patch.object(entry, 'BUNDLE', bundle), self.assertRaisesRegex(RuntimeError, 'BUNDLE_PIN'):
            entry.prepared()


if __name__ == '__main__':
    unittest.main()
