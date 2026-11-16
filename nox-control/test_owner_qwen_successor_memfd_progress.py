"""Synthetic public memfd fixtures only; no native process or payload operations."""
import ast
import errno
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import types
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).with_name('owner_qwen_successor_memfd_progress.py')
spec = importlib.util.spec_from_file_location('successor_public_memfd_test', SOURCE)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class MemfdProgressTests(unittest.TestCase):
    def setUp(self):
        self.fds = []
        self.fixture = patch.multiple(m, OWNER_UID=os.geteuid(), STOPS=())
        self.fixture.start()

    def tearDown(self):
        self.fixture.stop()
        for fd in self.fds:
            os.close(fd)

    def memfd(self, name, data, *, sealed=False):
        fd = os.memfd_create(name, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        self.fds.append(fd); os.write(fd, data)
        if sealed:
            fcntl.fcntl(fd, getattr(fcntl, 'F_ADD_SEALS', 1033), m.FULL_SEALS)
        return fd

    def row(self, name, size):
        return {'path': name, 'bytes': size, 'sha256': 'a' * 64}

    def scan(self, files):
        value = {}; m.sample(os.getpid(), files, value); return value

    def test_real_growth_then_seal_is_metadata_only_and_original_offset_unchanged(self):
        fd = self.memfd('nox-qwen-config.json', b'abc')
        first = self.scan([self.row('config.json', 6)])
        self.assertEqual(first['observed_unique_written_bytes'], 3)
        self.assertEqual(first['members'][0]['fdinfo_pos_min'], 3)
        self.assertEqual(os.lseek(fd, 0, os.SEEK_CUR), 3)
        os.write(fd, b'def'); fcntl.fcntl(fd, getattr(fcntl, 'F_ADD_SEALS', 1033), m.FULL_SEALS)
        second = self.scan([self.row('config.json', 6)])
        self.assertEqual(second['fully_sealed_members'], 1)
        self.assertEqual(second['observed_unique_written_bytes'], 6)
        self.assertEqual(second['members'][0]['state'], 'SEALED_PUBLIC_METADATA_ONLY')
        self.assertEqual(m.growth(first, second)['same_inode_written_bytes_delta'], 3)
        self.assertEqual(os.lseek(fd, 0, os.SEEK_CUR), 6)

    def test_zero_payload_no_unknown_open_or_export_and_no_retained_fds(self):
        public = self.memfd('nox-qwen-config.json', b'public', sealed=True)
        private = self.memfd('private-secret-DO-NOT-EXPORT', b'PRIVATE')
        before = set(os.listdir('/proc/self/fd'))
        original_open, original_fdopen = os.open, os.fdopen
        private_path = f'/proc/{os.getpid()}/fd/{private}'
        def checked_open(path, flags, *a, **kw):
            self.assertNotEqual(str(path), private_path)
            return original_open(path, flags, *a, **kw)
        def checked_fdopen(fd, *a, **kw):
            self.assertNotIn('memfd:', os.readlink(f'/proc/self/fd/{fd}'))
            return original_fdopen(fd, *a, **kw)
        with patch.object(m.os, 'open', side_effect=checked_open), patch.object(m.os, 'fdopen', side_effect=checked_fdopen), \
                patch.object(m.os, 'pread', side_effect=AssertionError('payload forbidden')), \
                patch.object(m.os, 'read', side_effect=AssertionError('payload forbidden')):
            value = self.scan([self.row('config.json', 6)])
        self.assertEqual(before, set(os.listdir('/proc/self/fd')))
        self.assertEqual(value['readonly_open_count'], value['readonly_closed_count'])
        self.assertTrue(value['owned_fd_cleanup_complete'])
        self.assertEqual(value['public_payload_bytes_read'], 0)
        self.assertEqual(value['unknown_fd_payload_bytes_read'], 0)
        self.assertNotIn('PRIVATE', json.dumps(value)); self.assertNotIn('private-secret', json.dumps(value))
        self.assertEqual(os.lseek(public, 0, os.SEEK_CUR), 6)

    def test_same_inode_aliases_count_once(self):
        fd = self.memfd('nox-qwen-config.json', b'abc', sealed=True)
        self.fds.append(os.dup(fd))
        value = self.scan([self.row('config.json', 3)])
        self.assertGreaterEqual(value['members'][0]['descriptor_count'], 2)
        self.assertEqual(value['observed_unique_public_members'], 1)
        self.assertEqual(value['observed_unique_written_bytes'], 3)

    def test_different_inode_same_public_name_excluded_from_total(self):
        self.memfd('nox-qwen-config.json', b'abc')
        self.memfd('nox-qwen-config.json', b'def')
        value = self.scan([self.row('config.json', 3)])
        self.assertEqual(value['members'][0]['state'], 'AMBIGUOUS_PUBLIC_INODE')
        self.assertFalse(value['members'][0]['readonly_access_verified'])
        self.assertEqual(value['observed_unique_written_bytes'], 0)

    def test_access_denied_safe_partial_without_raw_error(self):
        fd = self.memfd('nox-qwen-config.json', b'abc')
        original = os.open
        def denied(path, flags, *a, **kw):
            if str(path) == f'/proc/{os.getpid()}/fd/{fd}':
                raise PermissionError(errno.EACCES, 'PRIVATE_ERROR_TEXT')
            return original(path, flags, *a, **kw)
        with patch.object(m.os, 'open', side_effect=denied):
            value = self.scan([self.row('config.json', 3), self.row('pending.json', 2)])
        self.assertEqual([row['state'] for row in value['members']], ['ACCESS_DENIED', 'NOT_OBSERVED'])
        self.assertNotIn('PRIVATE_ERROR_TEXT', json.dumps(value))
        self.assertEqual(value['observed_unique_written_bytes'], 0)

    def test_fdinfo_inode_race_rejected_and_descriptor_closed(self):
        self.memfd('nox-qwen-config.json', b'abc')
        before = set(os.listdir('/proc/self/fd')); original = m.fdinfo
        def changed(pid, number):
            value = original(pid, number); value['ino'] += 1; return value
        with patch.object(m, 'fdinfo', side_effect=changed):
            value = self.scan([self.row('config.json', 3)])
        self.assertEqual(value['members'][0]['state'], 'PUBLIC_METADATA_REJECTED')
        self.assertEqual(value['observed_unique_written_bytes'], 0)
        self.assertEqual(before, set(os.listdir('/proc/self/fd')))

    def test_named_proc_target_race_is_not_admitted(self):
        fd = self.memfd('nox-qwen-config.json', b'abc')
        original = os.readlink; count = [0]
        def changed(path, *a, **kw):
            if str(path) == f'/proc/{os.getpid()}/fd/{fd}':
                count[0] += 1
                if count[0] > 1:
                    return '/memfd:PRIVATE_REPLACEMENT (deleted)'
            return original(path, *a, **kw)
        with patch.object(m.os, 'readlink', side_effect=changed):
            value = self.scan([self.row('config.json', 3)])
        self.assertEqual(value['members'][0]['state'], 'PUBLIC_METADATA_REJECTED')
        self.assertNotIn('PRIVATE_REPLACEMENT', json.dumps(value))

    def test_deadline_escapes_member_catch_and_closes_owned_fd(self):
        self.memfd('nox-qwen-config.json', b'abc')
        before = set(os.listdir('/proc/self/fd')); value = {}; original = fcntl.fcntl
        def expired(fd, operation, *a):
            if operation == m.GET_SEALS:
                raise m.Deadline()
            return original(fd, operation, *a)
        with patch.object(m.fcntl, 'fcntl', side_effect=expired), self.assertRaises(m.Deadline):
            m.sample(os.getpid(), [self.row('config.json', 3)], value)
        self.assertEqual(value['readonly_open_count'], 1)
        self.assertEqual(value['readonly_closed_count'], 1)
        self.assertEqual(before, set(os.listdir('/proc/self/fd')))

    def test_fd_scan_bound_is_not_silently_complete(self):
        with patch.object(m, 'MAX_FDS', 1), self.assertRaisesRegex(m.Hold, 'FD_SCAN_BOUND'):
            self.scan([self.row('config.json', 3)])

    def test_start_receipt_exact_hash_and_current_pid_required(self):
        row = {'schema': 'NOX_QWEN_SUCCESSOR_START_RECEIPT_V1', 'execution_revision': m.REFERENCE,
               'watcher_ready_sha256': m.READY_SHA, 'start_command_issued': True,
               'start_command_returncode': 0, 'trainer': {'process_identity': dict(m.PROCESS), 'service': {'state': 'RUNNING'}}}
        shared = types.SimpleNamespace(document=Mock(return_value=(row, b'start')), read=Mock(return_value=b'ready'))
        ctx = {'execution': {'directory': Path('/synthetic-immutable-attempt')}}
        m.start_binding(shared, ctx)
        self.assertEqual(shared.document.call_args.kwargs, {'expected': m.START_SHA, 'private': True})
        self.assertEqual(shared.read.call_args.kwargs, {'expected': m.READY_SHA, 'private': True})
        row['trainer']['process_identity']['start_ticks'] += 1
        with self.assertRaisesRegex(m.Hold, 'START_BINDING'):
            m.start_binding(shared, ctx)

    def fake_context(self):
        raw, manifest_raw = b'fixture-shared-definitions', b'fixture-manifest'
        ctx = {'context': dict(m.REFERENCE), 'raw': b'admission', 'wrapper': b'wrapper', 'config_sha256': 'a' * 64,
               'execution': {'descriptor': {'activation_issuer_sha256': m.INSTALLER_SHA}, 'runtime_entry_sha256': m.STUDENT_SHA},
               'contract': types.SimpleNamespace(validate_manifest=lambda _: [self.row(f'public{i}.json', 1) for i in range(16)])}
        shared = types.SimpleNamespace(current_context=Mock(return_value=ctx))
        trainer = {'process_identity': dict(m.PROCESS), 'service': {'state': 'RUNNING', 'pid': 1091068}}
        core = types.SimpleNamespace(SCRIPTS=Path('/synthetic'), SHARED='canonical.py', SHARED_ASSET='successor.py',
            PINS={'successor.py': m.digest(raw)}, PROTECTED={'qwen35_9b_manifest.json': m.digest(manifest_raw)},
            read=lambda _: raw, module=lambda *_: shared, protected=Mock(), trainer=Mock(return_value=trainer),
            document=lambda *_: ({}, manifest_raw))
        return core, shared, ctx, trainer, raw, manifest_raw

    def test_changed_pid_discards_current_progress_binding(self):
        core, shared, ctx, trainer, raw, manifest = self.fake_context()
        core.trainer.side_effect = [trainer, {**trainer, 'process_identity': {**m.PROCESS, 'start_ticks': 123}}]
        result = {'current_binding_verified': False}
        with patch.object(m, 'core_module', return_value=core), patch.object(m, 'start_binding'), \
                patch.multiple(m, SHARED_SHA=m.digest(raw), MANIFEST_SHA=m.digest(manifest), TOTAL_PUBLIC_BYTES=16), \
                patch.object(m, 'sample'), patch.object(m.time, 'sleep') as wait:
            with self.assertRaisesRegex(m.Hold, 'TRAINER_CHANGED'):
                m.snapshot(result)
        wait.assert_called_once_with(1.0)
        self.assertFalse(result['current_binding_verified']); self.assertEqual(len(result['samples']), 2)

    def test_shared_source_drift_holds_before_fd_scan(self):
        core, _, _, _, _, _ = self.fake_context()
        with patch.object(m, 'core_module', return_value=core), patch.object(m, 'sample') as scan:
            with self.assertRaisesRegex(m.Hold, 'SHARED_PIN'):
                m.snapshot({})
        scan.assert_not_called()

    def test_deadline_reporting_does_not_promote_partial_sample(self):
        def expired(out):
            out['samples'] = [{'readonly_open_count': 1, 'readonly_closed_count': 1}]
            raise m.Deadline()
        with patch.object(m, 'snapshot', side_effect=expired), patch('builtins.print') as output:
            self.assertEqual(m.main(), 2)
        result = json.loads(output.call_args_list[0].args[0].split('=', 1)[1])['data']
        self.assertFalse(result['current_binding_verified'])
        self.assertTrue(result['owned_fd_cleanup_verified'])
        self.assertEqual(result['persistent_fds_retained'], 0)
        self.assertEqual(result['reason'], 'HOLD_SUCCESSOR_MEMFD_DEADLINE')

    def test_readonly_scope_and_exact_current_source_pins(self):
        tree = ast.parse(SOURCE.read_text())
        calls = {ast.unparse(node.func) for node in ast.walk(tree) if isinstance(node, ast.Call)}
        self.assertFalse(calls & {'os.read', 'os.pread', 'os.readv', 'os.write', 'os.pwrite', 'os.unlink', 'os.rename',
                                 'os.chmod', 'os.kill', 'os.memfd_create', 'subprocess.run', 'subprocess.Popen',
                                 'socket.socket', 'core.main', 'core.finalize_same_process', 'core.owned_pause'})
        self.assertNotIn('F_ADD_SEALS', SOURCE.read_text())
        for name, pin in [('owner_qwen_successor_install_v2.py', m.INSTALLER_SHA),
                          ('owner_qwen_execution_successor.py', m.SHARED_SHA),
                          ('qwen_student_training_entry_successor.py', m.STUDENT_SHA)]:
            self.assertEqual(hashlib.sha256(SOURCE.with_name(name).read_bytes()).hexdigest(), pin)
        self.assertEqual(m.MAX_SECONDS, 20); self.assertEqual(m.MAX_FDS, 512)


if __name__ == '__main__':
    unittest.main()
