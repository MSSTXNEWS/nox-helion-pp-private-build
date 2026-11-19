import ast
import base64
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

sys.path.insert(0, str(Path(__file__).parent))
import owner_media_fixture_transport as transport
import owner_media_fixture_local as local
import owner_media_fixture_export as exporter


class Transport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
        cls.pem = cls.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                        serialization.NoEncryption())
        public = cls.key.public_key()
        cls.public_pem = public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        cls.key_id = transport.digest(public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.payloads = []; rows = []
        for original in transport.FILES:
            marker = b'PRIVATE_SYNTHETIC_PIXEL_CONTENT_'+original['kind'].encode()
            raw = (marker*((original['bytes']//len(marker))+1))[:original['bytes']]
            path = self.root/original['filename']; path.write_bytes(raw); path.chmod(0o600)
            rows.append(dict(original, sha256=transport.digest(raw), native_path=str(path))); self.payloads.append(raw)
        context = patch.object(transport, 'FILES', tuple(rows)); context.start(); self.addCleanup(context.stop)
        self.files = tuple(rows)
        self.public = {'schema': 'NOX_MEDIA_REVIEW_PUBLIC_KEY_V1', 'key_id': self.key_id, 'public_key_pem': self.public_pem,
                       'transfer_id': 'd'*32, 'created_at': int(time.time())-1, 'expires_at': int(time.time())+600,
                       'manifest_sha256': transport.manifest_sha()}
        self.request = '1234567890'; self.source = 'a'*40

    def seal(self): return transport.seal(self.public, self.request, self.source)

    def decrypt(self, rows, **kwargs):
        return transport.decrypt(rows, self.pem, kwargs.get('public', self.public),
                                 kwargs.get('request', self.request), kwargs.get('source', self.source))

    def changed_envelope(self, rows, mutate):
        value = copy.deepcopy(rows)
        envelope, _ = transport.assemble(value); mutate(envelope)
        sha = transport.digest(transport.canonical(envelope))
        value[0]['data']['metadata'] = {k: v for k, v in envelope.items() if k != 'ciphertext'}
        value[0]['data']['envelope_sha256'] = sha
        chunks = [envelope['ciphertext'][i:i+transport.CHUNK_CHARS] for i in range(0, len(envelope['ciphertext']), transport.CHUNK_CHARS)]
        for index, item in enumerate(value[1:]):
            item['data']['envelope_sha256'] = sha; item['data']['ciphertext'] = chunks[index]
        return value

    def test_actual_crypto_roundtrip_exact_sizes_bounded_chunks_no_native_write_or_plaintext_log(self):
        opened = []; actual_open = os.open
        def audited(path, flags, *args, **kwargs):
            self.assertFalse(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
            opened.append(str(path)); return actual_open(path, flags, *args, **kwargs)
        with patch.object(transport.os, 'open', side_effect=audited):
            rows = self.seal()
        self.assertEqual(opened, [row['native_path'] for row in self.files])
        self.assertTrue(all(len(transport.canonical(row)) < 80000 for row in rows))
        encoded = transport.canonical(rows)
        self.assertNotIn(b'PRIVATE_SYNTHETIC_PIXEL', encoded)
        self.assertNotIn(b'PRIVATE KEY', encoded)
        self.assertNotIn(str(self.root).encode(), encoded)
        files, proof = self.decrypt([rows[0], *reversed(rows[1:])])
        self.assertEqual([transport.digest(raw) for _, raw in files], [row['sha256'] for row in self.files])
        self.assertEqual(sum(len(raw) for _, raw in files), 321278)
        self.assertFalse(proof['visual_review_completed'])

    def test_ciphertext_corruption_even_with_rewritten_outer_hash_cannot_pass_aead(self):
        def corrupt(envelope):
            cipher = bytearray(base64.b64decode(envelope['ciphertext'])); cipher[7] ^= 1
            envelope['ciphertext'] = transport.b64(cipher)
            envelope['ciphertext_sha256'] = transport.digest(cipher)
        rows = self.changed_envelope(self.seal(), corrupt)
        with self.assertRaises(InvalidTag): self.decrypt(rows)

    def test_request_source_and_manifest_aad_are_bound(self):
        rows = self.seal()
        with self.assertRaisesRegex(transport.TransportHold, 'AAD'): self.decrypt(rows, request='9')
        with self.assertRaisesRegex(transport.TransportHold, 'AAD'): self.decrypt(rows, source='b'*40)
        changed = self.changed_envelope(rows, lambda e: e['aad']['context'].update(source_sha='b'*40))
        with self.assertRaises(InvalidTag): self.decrypt(changed, source='b'*40)
        changed = self.changed_envelope(rows, lambda e: e['aad']['manifest']['files'][0].update(filename='../escape'))
        with self.assertRaisesRegex(transport.TransportHold, 'AAD'): self.decrypt(changed)

    def test_missing_duplicate_or_cross_transfer_chunk_is_rejected(self):
        rows = self.seal()
        for changed in (rows[:-1], [*rows, rows[-1]], [rows[0], rows[1], rows[1], *rows[3:]]):
            with self.assertRaises(transport.TransportHold): self.decrypt(changed)
        changed = copy.deepcopy(rows); changed[-1]['data']['envelope_sha256'] = 'f'*64
        with self.assertRaisesRegex(transport.TransportHold, 'CHUNK'): self.decrypt(changed)

    def test_expired_wrong_manifest_private_pem_and_wrong_key_are_rejected(self):
        expired = dict(self.public, expires_at=int(time.time())-1, created_at=int(time.time())-100)
        with self.assertRaises(transport.TransportHold): transport.seal(expired, self.request, self.source)
        bad = dict(self.public, manifest_sha256='b'*64)
        with self.assertRaises(transport.TransportHold): transport.seal(bad, self.request, self.source)
        bad = dict(self.public, public_key_pem=self.pem.decode())
        with self.assertRaises(transport.TransportHold): transport.seal(bad, self.request, self.source)
        bad = dict(self.public, key_id='0'*64)
        with self.assertRaises(transport.TransportHold): transport.seal(bad, self.request, self.source)

    def test_native_sha_mismatch_fifo_symlink_and_private_permissions_fail_closed(self):
        path = Path(self.files[0]['native_path']); path.write_bytes(b'x'*self.files[0]['bytes'])
        with self.assertRaisesRegex(transport.TransportHold, 'NATIVE_SHA'): self.seal()
        path.unlink(); os.mkfifo(path); started = time.monotonic()
        with self.assertRaises(transport.TransportHold): self.seal()
        self.assertLess(time.monotonic()-started, .5)
        path.unlink(); path.symlink_to(self.files[1]['native_path'])
        with self.assertRaises(transport.TransportHold): self.seal()
        private = self.root/'private.pem'; private.write_bytes(self.pem); private.chmod(0o644)
        with self.assertRaises(transport.TransportHold): transport.read_regular(private, 8192, private=True)

    def private_state(self):
        state = self.root/'local-state'; state.mkdir(mode=0o700)
        local.write_new(state/'private.pem', self.pem)
        local.write_new(state/'public_metadata.json', transport.canonical(self.public))
        return state

    def test_local_publication_only_after_both_hashes_and_never_overwrites(self):
        rows = self.seal(); state = self.private_state(); output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = local.recover(state, transport.canonical(rows), self.request, self.source)
        self.assertEqual(output.getvalue(), '')
        self.assertEqual(result['state'], 'FULL_SHA_VERIFIED_LOCAL_FILES')
        for item in result['files']:
            path = Path(item['path'])
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(transport.digest(path.read_bytes()), item['sha256'])
        self.assertEqual((state/'recovered').stat().st_mode & 0o777, 0o700)
        with self.assertRaises(FileExistsError): local.recover(state, transport.canonical(rows), self.request, self.source)

    def test_bad_transport_creates_no_plaintext_directory(self):
        state = self.private_state(); rows = self.seal(); rows[-1]['data']['ciphertext'] = 'A'*len(rows[-1]['data']['ciphertext'])
        with self.assertRaises(transport.TransportHold): local.recover(state, transport.canonical(rows), self.request, self.source)
        self.assertFalse((state/'recovered').exists())

    def test_prepare_creates_private_key_and_only_public_return_metadata(self):
        directory = self.root/'fresh-state'
        result = local.prepare(directory)
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        self.assertEqual((directory/'private.pem').stat().st_mode & 0o777, 0o600)
        self.assertEqual((directory/'public_metadata.json').stat().st_mode & 0o777, 0o600)
        self.assertNotIn('PRIVATE KEY', json.dumps(result))
        value = transport.decode_json(transport.read_regular(directory/'public_metadata.json', 8192, private=True))
        self.assertEqual(transport.public_key_metadata(value).key_size, 4096)
        self.assertEqual(result['public_metadata_sha256'], transport.digest((directory/'public_metadata.json').read_bytes()))
        with self.assertRaises(FileExistsError): local.prepare(directory)

    def test_duplicate_json_and_oversized_stdin_document_are_rejected(self):
        with self.assertRaises(transport.TransportHold): transport.decode_json(b'{"key":1,"key":2}')
        with self.assertRaises(transport.TransportHold): transport.decode_json(b' '*700001)

    def test_real_child_protocol_uses_only_ciphertext_and_completion_marker(self):
        tree = ast.parse(Path(transport.__file__).read_text())
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'FILES' for target in node.targets):
                node.value = ast.parse(repr(self.files), mode='eval').body
        raw = ast.unparse(ast.fix_missing_locations(tree)).encode()
        meta = transport.canonical(self.public)
        value = {'transport': transport.b64(raw), 'transport_sha256': transport.digest(raw),
                 'metadata': transport.b64(meta), 'metadata_sha256': transport.digest(meta),
                 'request': self.request, 'source_sha': self.source}
        result = subprocess.run([sys.executable, '-I', '-B', '-c', exporter.CHILD], input=json.dumps(value).encode(),
                                capture_output=True, timeout=25)
        self.assertEqual(result.returncode, 0, 'fixed crypto child failed')
        self.assertNotIn(b'PRIVATE_SYNTHETIC_PIXEL', result.stdout)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[-1], b'NOX_MAINT_REPAIR_COMPLETE=true')
        self.assertTrue(all(len(line) < 80000 for line in lines))
        rows = [json.loads(line.split(b'=', 1)[1]) for line in lines[:-1]]
        files, _ = self.decrypt(rows)
        self.assertEqual(sum(len(raw) for _, raw in files), 321278)

    def test_exporter_rejects_bad_pins_before_spawning_and_never_prints_child_stderr(self):
        with patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': self.request, 'NOX_OWNER_SOURCE_SHA': self.source}), \
             patch.object(exporter, 'TRANSPORT_SHA', 'a'*64), patch.object(exporter, 'BUNDLE', {}), \
             patch.object(exporter.subprocess, 'run') as spawned:
            with self.assertRaisesRegex(RuntimeError, 'BUNDLE_PIN'): exporter.main()
            spawned.assert_not_called()
        source = b'# fixed transport'; meta = transport.canonical(self.public)
        bundle = {'owner_media_fixture_transport.py': transport.b64(source),
                  'owner_media_fixture_public_key.json': transport.b64(meta)}
        failure = subprocess.CompletedProcess([], 2, b'', b'PRIVATE_SERVER_EXCEPTION_AND_PATH')
        captured = io.StringIO()
        with patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': self.request, 'NOX_OWNER_SOURCE_SHA': self.source}), \
             patch.object(exporter, 'TRANSPORT_SHA', transport.digest(source)), \
             patch.object(exporter, 'PUBLIC_METADATA_SHA', transport.digest(meta)), patch.object(exporter, 'BUNDLE', bundle), \
             patch.object(exporter.subprocess, 'run', return_value=failure) as spawned, contextlib.redirect_stdout(captured):
            with self.assertRaisesRegex(RuntimeError, '^HOLD_MEDIA_FIXTURE_NATIVE_EXPORT_FAILED$'): exporter.main()
        self.assertNotIn('PRIVATE_SERVER', captured.getvalue())
        self.assertEqual(spawned.call_args.args[0][:4], ['/usr/bin/python3', '-I', '-B', '-c'])
        self.assertEqual(set(spawned.call_args.kwargs['env']),
                         {'PATH', 'LANG', 'PYTHONNOUSERSITE', 'PYTHONDONTWRITEBYTECODE', 'CUDA_VISIBLE_DEVICES', 'OMP_NUM_THREADS'})


if __name__ == '__main__':
    unittest.main()
