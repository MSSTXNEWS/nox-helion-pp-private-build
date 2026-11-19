import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch


def load(name):
    path = Path(__file__).with_name(name + '.py')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


h = load('owner_hermes_hydrate')
m = load('owner_hermes_warm_move')
p = load('owner_hermes_ram_preflight')


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / 'nox'; self.shm = base / 'shm'
        self.ssd = self.root / 'offload/teachers' / h.NAME
        self.warm = self.shm / 'legacy/teachers' / h.NAME
        self.teacher = self.root / 'models/teachers' / h.NAME
        self.backup = self.root / 'state/move'; self.payload = self.warm.parent / '.owned-copy'
        for path in (self.ssd.parent, self.warm.parent, self.teacher.parent.parent, self.backup, self.payload, self.root / 'scripts'):
            path.mkdir(parents=True, exist_ok=True)
        self.teacher.parent.symlink_to(self.warm.parent, target_is_directory=True)
        self.raw = b'public synthetic weights\x00' * 200
        self.ssd.write_bytes(self.raw); self.warm.symlink_to(self.ssd)
        self.patches = [patch.object(h, name, value) for name, value in {
            'ROOT': self.root, 'SHM': self.shm, 'SSD': self.ssd, 'WARM': self.warm,
            'SIZE': len(self.raw), 'SHA': hashlib.sha256(self.raw).hexdigest(), 'CHUNK': 1024}.items()]
        self.patches += [patch.object(p, name, value) for name, value in {
            'SSD': self.ssd, 'WARM': self.warm, 'TEACHER': self.teacher}.items()]
        self.patches += [patch.object(m, 'RATE', 10**9), patch.object(h, 'allocation_gate', return_value={}),
                         patch.object(h, 'owner_stop', return_value=False)]
        for item in self.patches: item.start(); self.addCleanup(item.stop)
        self.handles = []
        self.addCleanup(lambda: [os.close(fd) for fd in self.handles])

    def directory(self, path):
        fd = h.directory(path); self.handles.append(fd); return fd

    def opened(self, path, flags=os.O_RDONLY):
        fd = os.open(path, flags | os.O_NOFOLLOW); self.handles.append(fd); return fd

    def aliases_setup(self):
        payload = self.payload / 'payload.gguf'; payload.write_bytes(self.raw); payload.chmod(0o600)
        before = h.identity(self.ssd.stat()); warm_before = h.identity(self.warm.lstat())
        rows = p.aliases(before)
        keep = {row['source_path_sha256']: row for item in rows.values() for row in item['link_metadata']
                if row['source_path_sha256'] != m.digest(str(self.warm).encode())}
        parents = tuple(self.directory(path) for path in (self.backup, self.warm.parent, self.ssd.parent, self.root / 'scripts'))
        td = self.directory(self.payload)
        state = {'phase': {}, 'ssd_original': before, 'warm_original': warm_before,
                 'ram_verified': h.identity(payload.stat())}
        return parents, td, state, keep

    def test_copy_and_full_sha_preserve_original_and_call_live_gates(self):
        source = self.opened(self.ssd); out = self.payload / 'payload.gguf'
        target = self.opened(out, os.O_RDWR | os.O_CREAT | os.O_EXCL)
        before = h.identity(os.fstat(source)); checks = []
        m.copy_verified(h, source, target, before, time.monotonic() + 5, lambda: checks.append(True))
        verified = m.full_hash(h, target, time.monotonic() + 5, out, lambda: checks.append(True))
        self.assertEqual(out.read_bytes(), self.raw); self.assertEqual(self.ssd.read_bytes(), self.raw)
        self.assertEqual(before, h.identity(self.ssd.stat())); self.assertTrue(checks)
        self.assertEqual(verified, h.identity(out.stat()))

    def test_source_corruption_never_reaches_verified_copy(self):
        self.ssd.write_bytes(b'X' * len(self.raw))
        source = self.opened(self.ssd); target = self.opened(self.payload / 'payload.gguf', os.O_RDWR | os.O_CREAT)
        with self.assertRaisesRegex(m.Hold, 'COPY_SHA'):
            m.copy_verified(h, source, target, h.identity(os.fstat(source)), time.monotonic() + 5, lambda: None)
        self.assertTrue(self.warm.is_symlink()); self.assertFalse(self.ssd.is_symlink())

    def test_atomic_alias_switch_and_rollback_preserve_both_payloads(self):
        parents, td, state, keep = self.aliases_setup()
        proof = m.switch_aliases(h, p, parents, td, self.payload, self.backup, state, keep)
        self.assertTrue(proof['warm_and_teacher_resolve_to_verified_ram'])
        self.assertFalse(self.warm.is_symlink()); self.assertTrue(self.ssd.is_symlink())
        self.assertEqual(self.teacher.read_bytes(), self.raw)
        self.assertEqual((self.backup / 'ssd.exchange').read_bytes(), self.raw)
        done = m.rollback(h, self.backup, self.payload, parents, state)
        self.assertTrue(done['ssd_original_restored']); self.assertTrue(self.warm.is_symlink())
        self.assertEqual(self.ssd.read_bytes(), self.raw)
        self.assertEqual((self.payload / 'payload.gguf').read_bytes(), self.raw)

    def test_successful_rename_is_latched_before_fsync_failure(self):
        parents, td, state, keep = self.aliases_setup()
        with patch.object(m.os, 'fsync', side_effect=OSError('synthetic fsync')):
            with self.assertRaises(OSError): m.switch_aliases(h, p, parents, td, self.payload, self.backup, state, keep)
        self.assertTrue(state['phase']['warm_exchanged']); self.assertFalse(self.warm.is_symlink())
        m.rollback(h, self.backup, self.payload, parents, state)
        self.assertTrue(self.warm.is_symlink()); self.assertEqual(self.ssd.read_bytes(), self.raw)

    def test_foreign_ssd_replacement_is_never_overwritten_by_rollback(self):
        parents, td, state, keep = self.aliases_setup()
        m.switch_aliases(h, p, parents, td, self.payload, self.backup, state, keep)
        self.ssd.unlink(); self.ssd.write_bytes(b'foreign')
        with self.assertRaisesRegex(m.Hold, 'ROLLBACK_SSD_FOREIGN'):
            m.rollback(h, self.backup, self.payload, parents, state)
        self.assertEqual(self.ssd.read_bytes(), b'foreign')
        self.assertEqual((self.backup / 'ssd.exchange').read_bytes(), self.raw)
        self.assertEqual(self.warm.read_bytes(), self.raw)

    def test_ram_named_replacement_fails_hash_even_when_original_fd_valid(self):
        target = self.payload / 'payload.gguf'; target.write_bytes(self.raw)
        fd = self.opened(target); target.rename(self.payload / 'old')
        target.write_bytes(self.raw)
        with self.assertRaisesRegex(m.Hold, 'HASH_OR_NAME_CHANGED'):
            m.full_hash(h, fd, time.monotonic() + 5, target, lambda: None)

    def test_restore_map_readback_corruption_blocks_success(self):
        with patch.object(h, 'read', return_value=b'foreign'):
            with self.assertRaisesRegex(h.Hold, 'RECORD_READBACK'):
                h.private_record(self.backup / 'map.json', {'public_sha': h.SHA})
        self.assertTrue(self.warm.is_symlink()); self.assertFalse(self.ssd.is_symlink())

    def test_created_helper_is_latched_before_fsync_and_only_own_inode_removed(self):
        path = self.root / 'scripts/helper.py'; captured = []
        with patch.object(m.os, 'fsync', side_effect=OSError('synthetic fsync')):
            with self.assertRaises(OSError): m.create_bytes(h, path, b'pass\n', on_created=captured.append)
        self.assertGreaterEqual(len(captured), 1)
        q = self.directory(self.backup)
        m.remove_created(h, path, captured[-1], q, 'helper')
        self.assertFalse(path.exists())
        path.write_bytes(b'foreign')
        with self.assertRaisesRegex(m.Hold, 'ROLLBACK_CREATED_FOREIGN'):
            m.remove_created(h, path, captured[-1], q, 'helper')
        self.assertEqual(path.read_bytes(), b'foreign')

    def test_ssd_exchange_rollback_works_when_first_reverse_readback_fails(self):
        parents, td, state, keep = self.aliases_setup()
        with patch.object(h, 'reversed_alias', side_effect=h.Hold('HOLD_TEST_READBACK')):
            with self.assertRaises(h.Hold): m.switch_aliases(h, p, parents, td, self.payload, self.backup, state, keep)
        self.assertTrue(state['phase']['ssd_exchanged']); self.assertNotIn('ssd_alias_after', state)
        m.rollback(h, self.backup, self.payload, parents, state)
        self.assertFalse(self.ssd.is_symlink()); self.assertTrue(self.warm.is_symlink())
        self.assertEqual(self.ssd.read_bytes(), self.raw)


class BudgetAndHydrationTests(unittest.TestCase):
    def test_exact_72gib_and_3gib_floors_apply_before_next_allocation(self):
        fs = SimpleNamespace(f_bavail=h.TMPFS_RESERVE + 10, f_frsize=1)
        with patch.object(h, 'headroom', return_value=h.MIN_HEADROOM + 10), patch.object(h.os, 'statvfs', return_value=fs):
            h.allocation_gate(10, 10)
            with self.assertRaisesRegex(h.Hold, 'RAM_72GIB'):
                h.allocation_gate(10, 11)
            with self.assertRaisesRegex(h.Hold, 'TMPFS_3GIB'):
                h.allocation_gate(11, 10)

    def test_public_only_url_scope_rejects_private_or_cross_service_redirects(self):
        for value in (h.URL, 'https://cas-bridge.xethub.hf.co/a?signature=synthetic'):
            self.assertEqual(h.allowed_url(value), value)
        for value in ('http://huggingface.co/x', 'https://127.0.0.1/x', 'https://huggingface.co.evil/x',
                      'https://user:password@huggingface.co/x', 'https://huggingface.co:444/x', 'file:///root/key'):
            with self.assertRaises(h.Hold): h.allowed_url(value)

    def test_pinned_download_has_no_proxy_and_never_publishes_wrong_sha(self):
        data = b'synthetic public file'
        class Response(io.BytesIO):
            status = 200
            headers = {'Content-Length': str(len(data))}
        opener = SimpleNamespace(open=lambda *args, **kwargs: Response(data))
        with tempfile.TemporaryFile() as target, patch.object(h, 'SIZE', len(data)), \
                patch.object(h, 'SHA', hashlib.sha256(data).hexdigest()), patch.object(h, 'CHUNK', 8), \
                patch.object(h, 'allocation_gate', return_value={}), patch.object(h, 'owner_stop', return_value=False), \
                patch.object(h.urllib.request, 'build_opener', return_value=opener) as build:
            self.assertEqual(h.download(target.fileno(), time.monotonic() + 5), len(data))
            self.assertEqual(build.call_args.args[0].proxies, {})
            target.seek(0); self.assertEqual(target.read(), data)
            with patch.object(h, 'SHA', '0' * 64):
                with self.assertRaisesRegex(h.Hold, 'DOWNLOAD_FULL_SHA'):
                    h.download(target.fileno(), time.monotonic() + 5)

    def test_downloader_patch_preserves_every_other_byte_and_does_not_use_main(self):
        source = (b'#!/bin/bash\nprevious() {\n  true\n}\n\ndownload_one() {\n'
                  b'  local name="$1" repo="$2" file="$3" dest="$4"\n'
                  b'  mkdir -p "$dest"\n' + m.ANCHOR + b'  echo original\n}\n')
        actual = m.patch_download(source, m.digest(source))
        self.assertEqual(actual.replace(m.BRANCH, b'', 1), source)
        self.assertIn(b'return $?', actual); self.assertNotIn(b'resolve/main', m.BRANCH)
        self.assertIn(h.REVISION, h.URL)
        with self.assertRaisesRegex(m.Hold, 'DOWNLOADER_PREIMAGE'): m.patch_download(source)
        with self.assertRaises(m.Hold): m.patch_download(source + m.ANCHOR, m.digest(source + m.ANCHOR))

    def test_wrong_source_pin_fails_before_any_definition_execution(self):
        raw = b'raise AssertionError("must not execute")\n'
        with patch.object(m, 'BUNDLE', {'bad.py': base64.b64encode(raw).decode()}):
            with self.assertRaisesRegex(m.Hold, 'BUNDLE_PIN'): m.module('bad.py', '0' * 64)

    def test_known_reference_blocks_even_when_visibility_partial(self):
        fake = SimpleNamespace(process_refs=lambda *a: {'known_reference_count': 1, 'complete': False})
        with self.assertRaisesRegex(m.Hold, 'KNOWN_HERMES_REFERENCE'):
            m.refs(fake, None, {}, 5, time.monotonic() + 5)

    def test_partial_visibility_is_retained_without_inactivity_claim(self):
        row = {'known_reference_count': 0, 'complete': False, 'partial_visibility_is_not_inactivity_proof': True}
        fake = SimpleNamespace(process_refs=lambda *a: row)
        self.assertEqual(m.refs(fake, None, {}, 5, time.monotonic() + 5), row)

    def test_failed_lease_conversion_does_not_claim_old_exclusive_lock(self):
        journal = {'lease_mode': 'EX'}
        with patch.object(m, 'convert_lease', side_effect=BlockingIOError()):
            with self.assertRaises(BlockingIOError): m.change_lease(4, False, journal)
        self.assertIsNone(journal['lease_mode'])


if __name__ == '__main__': unittest.main()
