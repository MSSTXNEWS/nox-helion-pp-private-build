import base64
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).parent


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


m = module('drive_bridge', 'owner_drive_ram_bridge.py')
p = module('drive_prepare', 'owner_drive_ram_prepare.py')
HOST = 'sdmntpritalynorth.oaiusercontent.com'


def url(index=0):
    return 'https://' + HOST + '/files/12345678-1234-1234-1234-%012d/raw?private_signature=secret' % index


def fixture():
    assets, links, bodies = [], [], {}
    for asset_index in range(3):
        data = b'abcdefgh'
        parts = []
        for ordinal in range(2):
            drive_id = 'private_drive_fixture_%d_%d' % (asset_index, ordinal)
            digest = hashlib.sha256(drive_id.encode()).hexdigest()
            address = url(asset_index * 2 + ordinal)
            links.append({'drive_id': drive_id, 'url': address})
            bodies[address] = data[ordinal * 4:ordinal * 4 + 4]
            parts.append({'ordinal': ordinal, 'bytes': 4, 'drive_id_sha256': digest})
        assets.append({'role': 'role%d' % asset_index, 'filename': 'adapter%d.safetensors' % asset_index,
                       'bytes': 8, 'sha256': hashlib.sha256(data).hexdigest(), 'parts': parts})
    return {'schema': 'NOX_DRIVE_RAM_APPROVED_ASSETS_V1', 'instance_id': m.INSTANCE_ID,
            'collection': '3t724u', 'assets': assets}, links, bodies


class Response:
    def __init__(self, body, status=200, headers=None):
        self.body = io.BytesIO(body)
        self.status = status
        self.headers = headers or {}

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read(self, size):
        return self.body.read(size)

    def close(self):
        self.body.close()


class Connection:
    def close(self):
        pass


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.state = Path(cls.folder.name) / 'state'
        cls.manifest, cls.links, cls.bodies = fixture()
        cls.manifest_sha = hashlib.sha256(m.canonical(cls.manifest)).hexdigest()
        with patch.object(p, 'STATE', cls.state), patch.object(p, 'MANIFEST_SHA256', cls.manifest_sha), \
                patch.dict(os.environ, {'NOX_OWNER_REQUEST_ID': '54321', 'NOX_OWNER_SOURCE_SHA': 'b' * 40}), \
                patch.object(p, 'candidate_pythons', return_value=[sys.executable]):
            cls.metadata = p.prepare()

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def crypto_context(self):
        return patch.multiple(m, STATE=self.state, MANIFEST_SHA256=self.manifest_sha)

    def test_real_seal_decrypt_never_publishes_urls_or_ids(self):
        with self.crypto_context():
            envelope = m.seal(self.metadata, self.links, self.manifest)
            text = json.dumps(envelope)
            self.assertNotIn('private_signature', text)
            self.assertNotIn('private_drive_fixture', text)
            self.assertNotIn(HOST, text)
            m.validate_envelope(envelope, self.metadata)
            self.assertEqual(m.decrypt(envelope, self.metadata, p), self.links)

    def test_ciphertext_and_aad_tampering_fail_closed(self):
        with self.crypto_context():
            envelope = m.seal(self.metadata, self.links, self.manifest)
            changed = copy.deepcopy(envelope)
            data = bytearray(base64.b64decode(changed['ciphertext']))
            data[-1] ^= 1
            changed['ciphertext'] = base64.b64encode(data).decode()
            with self.assertRaisesRegex(RuntimeError, 'AUTHENTICATION_FAILED'):
                m.decrypt(changed, self.metadata, p)
            changed = copy.deepcopy(envelope)
            changed['aad']['instance_id'] = 1
            with self.assertRaisesRegex(RuntimeError, 'AAD_BINDING'):
                m.validate_envelope(changed, self.metadata)
            with self.assertRaisesRegex(RuntimeError, 'EXPIRED'):
                m.validate_envelope(envelope, self.metadata, envelope['aad']['expires_at'])

    def test_exact_id_list_rejects_substitution_or_duplicate(self):
        changed = copy.deepcopy(self.links)
        changed[0]['drive_id'] = 'unapproved_private_id'
        with self.assertRaisesRegex(RuntimeError, 'ID_NOT_APPROVED'):
            m.validate_links(changed, self.manifest)
        changed = copy.deepcopy(self.links)
        changed[0] = changed[1]
        with self.assertRaisesRegex(RuntimeError, 'ID_NOT_APPROVED'):
            m.validate_links(changed, self.manifest)

    def test_url_scope_rejects_ssrf_and_nonraw_paths(self):
        self.assertEqual(m.validate_url(url()).hostname, HOST)
        bad = [url().replace('https:', 'http:'), url().replace(HOST, '127.0.0.1'),
               url().replace(HOST, HOST + '.evil.example'), url().replace(HOST, 'owner@' + HOST),
               url().replace(HOST, HOST + ':444'), url() + '#fragment',
               url().replace('/raw?', '/download?'), url() + '\n', url().replace(HOST, 'google.com')]
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    m.validate_url(value)

    def test_dns_rebinding_target_and_cross_host_redirect_rejected(self):
        result = types.SimpleNamespace(returncode=0, stdout=b'["127.0.0.1"]')
        with patch.object(m.subprocess, 'run', return_value=result):
            with self.assertRaisesRegex(RuntimeError, 'NONPUBLIC_ADDRESS'):
                m.resolve_public(HOST)
        response = Response(b'', 302, {'Location': url().replace(HOST, 'sdmntprdenmarkeast.oaiusercontent.com')})
        conn = types.SimpleNamespace(request=lambda *a, **k: None, getresponse=lambda: response, close=lambda: None)
        with patch.object(m, 'resolve_public', return_value=['8.8.8.8']) as resolve, \
                patch.object(m, 'PinnedHTTPS', return_value=conn):
            with self.assertRaisesRegex(RuntimeError, 'CROSS_HOST_REDIRECT'):
                m.open_response(url(), 0, time.monotonic() + 10)
            self.assertEqual(resolve.call_count, 1)

    def test_source_pinned_before_execution(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'prepare.py'
            source.write_text('raise AssertionError("must not execute")')
            with patch.object(m, 'PREPARE_PATH', source):
                with self.assertRaisesRegex(RuntimeError, 'SOURCE_PIN'):
                    m.load_prepare()

    def transfer_context(self, destination):
        return patch.multiple(m, DESTINATION=destination, MANIFEST_SHA256=self.manifest_sha)

    def response_factory(self, seen):
        def open_response(address, offset, deadline, attempt=0):
            body = self.bodies[address]
            headers = {'Content-Length': str(len(body) - offset)}
            if offset:
                headers['Content-Range'] = 'bytes %d-%d/%d' % (offset, len(body) - 1, len(body))
            seen.append(offset)
            return Connection(), Response(body[offset:], 206 if offset else 200, headers)
        return open_response

    def test_manifest_bound_range_resume_and_full_joined_sha(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder)
            asset = self.manifest['assets'][0]
            path = destination / asset['filename']
            partial = path.with_name(path.name + '.partial')
            partial.write_bytes(b'ab')
            partial.chmod(0o600)
            ledger = {'schema': 'NOX_DRIVE_RAM_PARTIAL_V1', 'manifest_sha256': self.manifest_sha,
                      'filename': asset['filename'], 'bytes': asset['bytes'], 'sha256': asset['sha256']}
            p.atomic_private(path.with_name(path.name + '.partial.json'), m.canonical(ledger))
            seen = []
            with self.transfer_context(destination), patch.object(m, 'admit', return_value={}), \
                    patch.object(m, 'open_response', side_effect=self.response_factory(seen)), \
                    patch.object(m, 'emit') as emitted:
                result = m.transfer_asset(asset, m.validate_links(self.links, self.manifest), self.manifest, p, time.monotonic() + 10)
            self.assertTrue(result['verified'])
            self.assertEqual(path.read_bytes(), b'abcdefgh')
            self.assertEqual(seen, [2, 0])
            self.assertFalse(partial.exists())
            self.assertEqual(path.stat().st_nlink, 1)
            self.assertNotIn('private_signature', str(emitted.call_args_list))

    def test_failed_joined_sha_preserves_partial_never_publishes(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder)
            asset = copy.deepcopy(self.manifest['assets'][0])
            asset['sha256'] = '0' * 64
            with self.transfer_context(destination), patch.object(m, 'admit', return_value={}), \
                    patch.object(m, 'open_response', side_effect=self.response_factory([])), patch.object(m, 'emit'):
                with self.assertRaisesRegex(RuntimeError, 'JOINED_SHA'):
                    m.transfer_asset(asset, m.validate_links(self.links, self.manifest), self.manifest, p, time.monotonic() + 10)
            self.assertFalse((destination / asset['filename']).exists())
            self.assertEqual((destination / (asset['filename'] + '.partial')).read_bytes(), b'abcdefgh')

    def test_wrong_range_and_oversized_response_never_write(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'partial'
            path.write_bytes(b'ab')
            path.chmod(0o600)
            fd = m.open_owned(path, create=True)
            try:
                with patch.object(m, 'open_response', return_value=(Connection(), Response(b'cd', 200))), \
                        patch.object(m, 'admit', return_value={}):
                    with self.assertRaisesRegex(RuntimeError, 'CONTENT_RANGE'):
                        m.receive_part(fd, {'bytes': 4}, 0, url(), time.monotonic() + 10, self.manifest)
                self.assertEqual(path.read_bytes(), b'ab')
                os.ftruncate(fd, 0)
                with patch.object(m, 'open_response', return_value=(Connection(), Response(b'abcde'))), \
                        patch.object(m, 'admit', return_value={}):
                    with self.assertRaisesRegex(RuntimeError, 'BYTE_QUOTA'):
                        m.receive_part(fd, {'bytes': 4}, 0, url(), time.monotonic() + 10, self.manifest)
                self.assertEqual(path.read_bytes(), b'')
            finally:
                os.close(fd)

    def test_admission_reserves_other_selected_media_downloads(self):
        resources = {'shm_free': m.SHM_RESERVE + m.IO_MARGIN + 1000,
                     'memory_free': m.CGROUP_RESERVE + m.IO_MARGIN + 1000}
        with patch.object(m, 'remaining_bytes', return_value=500), \
                patch.object(m, 'media_pending', return_value=(600, 600)), \
                patch.object(m, 'resource_snapshot', return_value=resources):
            with self.assertRaisesRegex(RuntimeError, 'SHM_RESERVE'):
                m.admit(self.manifest)

    def test_owner_stop_blocks_before_request_or_write(self):
        with patch.object(m, 'global_stop', return_value=True), patch.object(m, 'resource_snapshot') as snapshot:
            with self.assertRaisesRegex(RuntimeError, 'OWNER_STOP'):
                m.admit(self.manifest)
            snapshot.assert_not_called()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'partial'
            path.write_bytes(b'ab')
            path.chmod(0o600)
            fd = m.open_owned(path, create=True)
            try:
                with patch.object(m, 'global_stop', return_value=True), patch.object(m, 'open_response') as remote:
                    with self.assertRaisesRegex(RuntimeError, 'OWNER_STOP'):
                        m.receive_part(fd, {'bytes': 4}, 0, url(), time.monotonic() + 10, self.manifest)
                    remote.assert_not_called()
                self.assertEqual(path.read_bytes(), b'ab')
            finally:
                os.close(fd)

    def test_complete_consume_receipt_and_single_use_envelope(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / 'ram/3t724u'
            with self.crypto_context(), patch.object(m, 'DESTINATION', destination), \
                    patch.object(p, 'STATE', self.state), patch.object(m, 'load_prepare', return_value=p), \
                    patch.object(m, 'load_manifest', return_value=self.manifest), \
                    patch.object(m, 'require_tmpfs_destination'), patch.object(m, 'admit', return_value={}), \
                    patch.object(m, 'open_response', side_effect=self.response_factory([])), \
                    patch.object(m, 'emit') as emitted, patch.dict(os.environ, {
                        'NOX_OWNER_REQUEST_ID': '98765', 'NOX_OWNER_SOURCE_SHA': 'c' * 40}):
                envelope = m.seal(self.metadata, self.links, self.manifest)
                receipt = m.consume(envelope)
                self.assertEqual(receipt['state'], 'RAM_FILES_SHA_VERIFIED_NOT_MERGED')
                self.assertEqual(len(receipt['assets']), 3)
                self.assertFalse(receipt['weights_merged'])
                self.assertNotIn('private_signature', json.dumps(receipt))
                self.assertNotIn('private_drive_fixture', str(emitted.call_args_list))
                with self.assertRaisesRegex(RuntimeError, 'ALREADY_CONSUMED'):
                    m.consume(envelope)
            self.assertEqual(len(list(destination.glob('*.safetensors'))), 3)

    def test_existing_wrong_final_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder)
            asset = self.manifest['assets'][0]
            path = destination / asset['filename']
            path.write_bytes(b'XXXXXXXX')
            path.chmod(0o600)
            with self.transfer_context(destination):
                with self.assertRaisesRegex(RuntimeError, 'EXISTING_FINAL_SHA'):
                    m.transfer_asset(asset, {}, self.manifest, p, time.monotonic() + 10)
            self.assertEqual(path.read_bytes(), b'XXXXXXXX')

    def test_interrupted_atomic_publication_keeps_verified_inode(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder)
            asset = self.manifest['assets'][0]
            path = destination / asset['filename']
            partial = path.with_name(path.name + '.partial')
            partial.write_bytes(b'abcdefgh')
            partial.chmod(0o600)
            os.link(partial, path)
            inode = path.stat().st_ino
            ledger = {'schema': 'NOX_DRIVE_RAM_PARTIAL_V1', 'manifest_sha256': self.manifest_sha,
                      'filename': asset['filename'], 'bytes': asset['bytes'], 'sha256': asset['sha256']}
            p.atomic_private(path.with_name(path.name + '.partial.json'), m.canonical(ledger))
            with self.transfer_context(destination):
                self.assertEqual(m.remaining_bytes(self.manifest), 16)
                result = m.transfer_asset(asset, {}, self.manifest, p, time.monotonic() + 10)
            self.assertTrue(result['verified'])
            self.assertEqual(path.stat().st_ino, inode)
            self.assertEqual(path.stat().st_nlink, 1)
            self.assertFalse(partial.exists())

    def test_public_manifest_and_prepare_actual_pins(self):
        with patch.object(m, 'MANIFEST_PATH', HERE / 'owner_drive_ram_assets.json'), \
                patch.object(m, 'PREPARE_PATH', HERE / 'owner_drive_ram_prepare.py'):
            manifest = m.load_manifest()
            helper = m.load_prepare()
        self.assertEqual(helper.MANIFEST_SHA256, m.MANIFEST_SHA256)
        self.assertEqual(sum(asset['bytes'] for asset in manifest['assets']), 920362008)


if __name__ == '__main__':
    unittest.main()
