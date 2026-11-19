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
from unittest.mock import patch

SOURCE = Path(__file__).with_name('owner_qwen_public_memfd_access_probe.py')
spec = importlib.util.spec_from_file_location('public_memfd_probe_test_module', SOURCE)
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)


class ProbeTests(unittest.TestCase):
    def setUp(self):
        self.fds = []

    def tearDown(self):
        for fd in self.fds:
            os.close(fd)

    def memfd(self, name, payload, sealed=True):
        fd = os.memfd_create(name, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        self.fds.append(fd); os.write(fd, payload)
        if sealed:
            fcntl.fcntl(fd, getattr(fcntl, 'F_ADD_SEALS', 1033), m.FULL_SEALS)
        return fd

    def row(self, name, payload):
        return {'path': name, 'bytes': len(payload), 'sha256': hashlib.sha256(payload).hexdigest()}

    def scan(self, files):
        out = {}; m.memfd_access(os.getpid(), files, out); return out

    def test_only_sealed_public_config_payload_and_no_retained_fds(self):
        cfg = b'{"public":true}'
        cfd = self.memfd('nox-qwen-config.json', cfg)
        shard = self.memfd('nox-qwen-model.safetensors', b'weight bytes')
        self.memfd('secret-token-DO-NOT-EXPORT', b'PRIVATE CONTENT')
        before = set(os.listdir('/proc/self/fd')); reads = []
        original = os.pread
        def tracked(fd, count, offset):
            reads.append((os.fstat(fd).st_ino, count, offset)); return original(fd, count, offset)
        with patch.object(m.os, 'pread', side_effect=tracked):
            out = self.scan([self.row('config.json', cfg), self.row('model.safetensors', b'weight bytes')])
        self.assertEqual(before, set(os.listdir('/proc/self/fd')))
        self.assertEqual([r[0] for r in reads], [os.fstat(cfd).st_ino])
        self.assertNotIn(os.fstat(shard).st_ino, [r[0] for r in reads])
        self.assertEqual(out['config_payload_bytes_read'], len(cfg))
        self.assertTrue(out['config_sha_verified'])
        self.assertEqual(out['fully_sealed_members'], 2)
        self.assertNotIn('PRIVATE', json.dumps(out)); self.assertNotIn('secret-token', json.dumps(out))
        self.assertEqual(os.lseek(cfd, 0, os.SEEK_CUR), len(cfg))
        self.assertFalse(out['full_public_base_payload_sha_verified'])

    def test_unsealed_and_absent_are_not_access_failure_or_payload_read(self):
        self.memfd('nox-qwen-config.json', b'abc', sealed=False)
        with patch.object(m.os, 'pread', side_effect=AssertionError('must not read')):
            out = self.scan([self.row('config.json', b'abcdef'), self.row('other.json', b'xyz')])
        self.assertEqual([r['state'] for r in out['members']], ['PENDING_UNSEALED', 'PENDING_NOT_OBSERVED'])
        self.assertEqual(out['config_payload_bytes_read'], 0)

    def test_access_denied_preserves_other_evidence(self):
        cfg = b'{}'; fd = self.memfd('nox-qwen-config.json', cfg)
        self.memfd('nox-qwen-other.json', b'abc')
        original = os.open
        def denied(path, flags, *args, **kwargs):
            if str(path) == '/proc/%s/fd/%s' % (os.getpid(), fd):
                raise PermissionError(errno.EACCES, 'DO NOT EXPORT PRIVATE ERROR')
            return original(path, flags, *args, **kwargs)
        with patch.object(m.os, 'open', side_effect=denied):
            out = self.scan([self.row('config.json', cfg), self.row('other.json', b'abc')])
        self.assertEqual(out['members'][0]['state'], 'ACCESS_DENIED')
        self.assertEqual(out['members'][1]['state'], 'SEALED_METADATA_ONLY')
        self.assertNotIn('PRIVATE ERROR', json.dumps(out))

    def test_deadline_during_metadata_closes_owned_fd_and_retains_partial(self):
        self.memfd('nox-qwen-config.json', b'{}'); before = set(os.listdir('/proc/self/fd'))
        original = fcntl.fcntl; out = {}
        def deadline(fd, command, *args):
            if command == m.GET_SEALS:
                raise m.ProbeDeadline('HOLD_PUBLIC_MEMFD_PROBE_DEADLINE')
            return original(fd, command, *args)
        with patch.object(m.fcntl, 'fcntl', side_effect=deadline), self.assertRaises(m.ProbeDeadline):
            m.memfd_access(os.getpid(), [self.row('config.json', b'{}')], out)
        self.assertEqual(before, set(os.listdir('/proc/self/fd')))
        self.assertEqual(out['public_readonly_open_count'], 1)
        self.assertEqual(out['config_payload_bytes_read'], 0)

    def test_same_inode_duplicate_does_not_repeat_config_payload(self):
        fd = self.memfd('nox-qwen-config.json', b'{}')
        self.fds.append(os.dup(fd))
        out = self.scan([self.row('config.json', b'{}')])
        self.assertGreaterEqual(out['matched_descriptors'], 2)
        self.assertEqual(out['config_payload_bytes_read'], 2)
        self.assertTrue(out['config_sha_verified'])

    def test_distinct_inode_duplicate_is_ambiguous(self):
        self.memfd('nox-qwen-config.json', b'{}'); self.memfd('nox-qwen-config.json', b'{}')
        out = self.scan([self.row('config.json', b'{}')])
        self.assertEqual(out['members'][0]['state'], 'AMBIGUOUS_PUBLIC_INODE')
        self.assertFalse(out['config_sha_verified'])
        self.assertEqual(out['config_payload_bytes_read'], 2)

    def test_wrong_config_sha_is_observed_failure(self):
        self.memfd('nox-qwen-config.json', b'{1}')
        out = self.scan([self.row('config.json', b'{2}')])
        self.assertEqual(out['members'][0]['state'], 'CONFIG_SHA_MISMATCH')
        self.assertFalse(out['config_sha_verified'])

    def test_pid_boot_recheck_invalidates_binding_preserving_scan(self):
        ctx = {'raw': b'admission', 'context': dict(m.REFERENCE),
               'execution': {'runtime_entry_sha256': m.STUDENT_SHA, 'descriptor': {'activation_issuer_sha256': m.INSTALLER_SHA}},
               'contract': types.SimpleNamespace(validate_manifest=lambda _: [self.row('config.json', b'{}')])}
        shared = types.SimpleNamespace(current_context=lambda _: ctx)
        before = {'service': {'state': 'RUNNING', 'pid': 10}, 'process_identity': {'pid': 11, 'start_ticks': 12, 'boot_id': 'a'}}
        after = {'service': {'state': 'RUNNING', 'pid': 10}, 'process_identity': {'pid': 11, 'start_ticks': 12, 'boot_id': 'b'}}
        core = types.SimpleNamespace(SCRIPTS=Path('/not/native'), SHARED='shared.py',
            PINS={'shared.py': m.SHARED_SHA}, PROTECTED={'qwen35_9b_manifest.json': m.MANIFEST_SHA},
            read=lambda _: b'shared', digest=lambda b: m.SHARED_SHA if b == b'shared' else m.MANIFEST_SHA,
            module=lambda *_: shared, protected=lambda: None, document=lambda _: ({}, b'manifest'))
        from unittest.mock import Mock
        core.trainer = Mock(side_effect=[before, after]); out = {}
        with patch.object(m, 'core_module', return_value=core), patch.object(m, 'cgroup_snapshot', return_value={}), \
             patch.object(m, 'memfd_access', side_effect=lambda p, f, r: r.update(config_sha_verified=True)):
            with self.assertRaisesRegex(RuntimeError, 'TRAINER_CHANGED'):
                m.snapshot(out)
        self.assertFalse(out['current_binding_verified']); self.assertTrue(out['memfd']['config_sha_verified'])

    def test_main_deadline_retains_metadata_without_raw_exception(self):
        def bounded(out):
            out['memfd'] = {'matched_descriptors': 4}; raise m.ProbeDeadline('HOLD_PUBLIC_MEMFD_PROBE_DEADLINE')
        with patch.object(m, 'snapshot', side_effect=bounded), patch('builtins.print') as output:
            self.assertEqual(m.main(), 2)
        row = json.loads(output.call_args_list[0].args[0].split('=', 1)[1])['data']
        self.assertEqual(row['memfd']['matched_descriptors'], 4)
        self.assertFalse(row['current_binding_verified'])

    def test_readonly_source_scope_and_pins(self):
        tree = ast.parse(SOURCE.read_text())
        calls = {ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
        self.assertFalse(calls & {'os.write', 'os.pwrite', 'os.unlink', 'os.rename', 'os.chmod', 'os.kill',
            'os.memfd_create', 'subprocess.run', 'subprocess.Popen', 'socket.socket', 'core.main', 'core.finalize_current'})
        self.assertNotIn('F_ADD_SEALS', SOURCE.read_text())
        self.assertEqual(hashlib.sha256(SOURCE.with_name('owner_qwen_transport_budget_install.py').read_bytes()).hexdigest(), m.INSTALLER_SHA)
        self.assertEqual(hashlib.sha256(SOURCE.with_name('qwen_student_training_entry_transport_budget.py').read_bytes()).hexdigest(), m.STUDENT_SHA)


if __name__ == '__main__':
    unittest.main()
