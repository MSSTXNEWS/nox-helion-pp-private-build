import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent))
import owner_chat_ui as ui
import owner_download_status as status


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = value if isinstance(value, bytes) else json.dumps(value, sort_keys=True).encode()
    path.write_bytes(raw); path.chmod(0o600)
    return hashlib.sha256(raw).hexdigest()


class Inventory(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.root = self.base/'nox'
        self.ram = self.base/'media'; self.drive = self.base/'drive'
        self.media = tuple((a, b, c, d, 32, hashlib.sha256(d.encode()).hexdigest())
                           for a, b, c, d, _, _ in status.MEDIA)
        self.adapters = tuple((a, b, 16, hashlib.sha256(b.encode()).hexdigest()) for a, b, _, _ in status.DRIVE)
        for name, value in {'ROOT': self.root, 'MEDIA_RAM': self.ram, 'DRIVE_RAM': self.drive,
                            'MEDIA': self.media, 'DRIVE': self.adapters}.items():
            context = patch.object(status, name, value); context.start(); self.addCleanup(context.stop)
        source = b'# approved fixed bridge\n'; self.bridge_sha = write(self.root/'scripts/owner_drive_ram_bridge.py', source)
        context = patch.object(status, 'DRIVE_BRIDGE_SHA', self.bridge_sha); context.start(); self.addCleanup(context.stop)
        self.selection = self.root/'config/owner_download_manifest.json'
        self.manifest_sha = write(self.selection, {'selection': 'unchanged', 'downloaded_bytes': 0})
        self.prepare = {'schema': 'NOX_MEDIA_PREPARE_JOB_V1', 'request': '1234567', 'source_sha': 'a'*40,
                        'installer_sha256': status.INSTALLER_SHA, 'runtime_sha256': status.RUNTIME_SHA}
        write(self.root/'state/owner_media/prepare_job.json', self.prepare)
        assets = []
        for kind, role, subdir, filename, size, sha in self.media:
            path = self.ram/'models'/subdir/filename; write(path, b'x'*size); info = path.stat()
            assets.append({'kind': kind, 'role': role, 'filename': filename, 'path': str(path), 'bytes': size,
                           'sha256': sha, 'verified': True, 'stat_device': info.st_dev,
                           'stat_inode': info.st_ino, 'stat_mtime_ns': info.st_mtime_ns})
        self.config = {'schema_version': 1, 'enabled': True, 'engine_service': 'nox-media-comfyui', 'assets': assets}
        self.save_media()
        drive_rows = []
        for role, filename, size, sha in self.adapters:
            path = self.drive/filename; write(path, b'y'*size); info = path.stat()
            drive_rows.append({'role': role, 'filename': filename, 'bytes': size, 'sha256': sha, 'verified': True,
                               'stat_inode': info.st_ino, 'stat_mtime_ns': info.st_mtime_ns})
        self.drive_receipt = {'schema': 'NOX_DRIVE_RAM_RECEIPT_V1', 'state': 'RAM_FILES_SHA_VERIFIED_NOT_MERGED',
                              'manifest_sha256': status.DRIVE_MANIFEST_SHA, 'weights_merged': False,
                              'active_model_changed': False, 'private_urls_exported': False, 'ram_is_durable_backup': False,
                              'finished_at': time.time()-10, 'assets': drive_rows, 'envelope_sha256': 'e'*64,
                              'request': '7654321', 'source_sha': 'b'*40}
        self.save_drive()

    def save_media(self):
        sha = write(self.root/'config/owner_media_runtime.json', self.config)
        self.media_receipt = {'schema': 'NOX_MEDIA_PREPARE_WORKER_V1', 'request': self.prepare['request'],
                              'source_sha': self.prepare['source_sha'], 'config_sha256': sha,
                              'state': 'ENGINE_AND_FILES_READY_GENERATION_ACCEPTANCE_PENDING', 'finished': time.time()-20}
        write(self.root/'state/owner_media/prepare_result_1234567.json', self.media_receipt)

    def save_drive(self):
        write(self.root/'state/owner_drive_ram/latest_receipt.json', self.drive_receipt)
        write(self.root/('state/owner_drive_ram/consumed/'+'e'*64+'.json'), self.drive_receipt)

    def test_full_receipts_and_current_files_show_seven_without_hashing_payloads_or_mutating_manifest(self):
        before = self.selection.stat(); original_read = os.read
        def guarded(fd, length):
            target = os.readlink('/proc/self/fd/'+str(fd))
            self.assertFalse(target.endswith('.safetensors'), 'UI must not read multi-GB payloads')
            return original_read(fd, length)
        with patch.object(status.os, 'read', side_effect=guarded):
            value = status.snapshot()
        self.assertEqual(value['media']['verified_files'], 4)
        self.assertEqual(value['drive_adapters']['verified_files'], 3)
        self.assertEqual(value['selection_manifest'], {'sha256': self.manifest_sha, 'is_transfer_status': False})
        self.assertEqual(self.selection.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertFalse(value['media']['generation_acceptance']['image']['verified'])
        self.assertEqual(value['drive_adapters']['current_model_merge_inclusion'], 'NOT_VERIFIED')
        self.assertFalse(value['large_file_hashes_recomputed'])

    def test_changed_or_missing_current_file_revokes_only_that_file(self):
        path = Path(self.config['assets'][0]['path']); path.unlink()
        adapter = self.drive/self.adapters[0][1]
        previous = adapter.stat(); os.utime(adapter, ns=(previous.st_atime_ns, previous.st_mtime_ns+1))
        value = status.snapshot()
        self.assertEqual(value['media']['verified_files'], 3)
        self.assertEqual(value['drive_adapters']['verified_files'], 2)
        self.assertNotEqual(value['drive_adapters']['assets'][0]['state'], 'SHA_VERIFIED_CURRENT_FILE')

    def test_same_size_replacement_inode_is_not_a_verified_download(self):
        path = Path(self.config['assets'][0]['path']); info = path.stat()
        replace = path.with_suffix('.replacement'); write(replace, b'z'*info.st_size)
        os.utime(replace, ns=(info.st_atime_ns, info.st_mtime_ns)); os.replace(replace, path)
        value = status.snapshot()
        self.assertEqual(value['media']['verified_files'], 3)
        self.assertEqual(value['media']['assets'][0]['state'], 'PRESENT_UNVERIFIED')

    def test_old_receipt_is_currently_usable_only_while_file_identity_still_matches(self):
        self.drive_receipt['finished_at'] = time.time()-86400; self.save_drive()
        self.assertEqual(status.snapshot()['drive_adapters']['verified_files'], 3)
        (self.drive/self.adapters[0][1]).unlink()
        self.assertEqual(status.snapshot()['drive_adapters']['verified_files'], 2)

    def test_changed_config_or_failed_worker_never_upgrades_file_presence_to_verification(self):
        self.config['enabled'] = False
        write(self.root/'config/owner_media_runtime.json', self.config)
        self.assertEqual(status.snapshot()['media']['verified_files'], 0)
        self.config['enabled'] = True; self.save_media()
        self.media_receipt['state'] = 'HOLD_MEDIA_PREPARE'
        write(self.root/'state/owner_media/prepare_result_1234567.json', self.media_receipt)
        self.assertEqual(status.snapshot()['media']['verified_files'], 0)

    def test_partial_bytes_never_count_as_verified_or_complete(self):
        path = Path(self.config['assets'][0]['path']); path.unlink()
        write(path.with_name(path.name+'.partial'), b'q'*11)
        value = status.snapshot()['media']
        self.assertEqual(value['verified_files'], 3)
        self.assertEqual(value['partial_bytes_unverified'], 11)
        self.assertEqual(value['assets'][0]['state'], 'PARTIAL_UNVERIFIED')

    def test_duplicate_rows_out_of_scope_paths_and_future_receipts_fail_closed(self):
        original = json.loads(json.dumps(self.config))
        self.config['assets'][1] = self.config['assets'][0]; self.save_media()
        self.assertEqual(status.snapshot()['media']['verified_files'], 0)
        self.config = original; self.config['assets'][0]['path'] = '/etc/passwd'; self.save_media()
        self.assertEqual(status.snapshot()['media']['verified_files'], 0)
        self.drive_receipt['finished_at'] = time.time()+3600; self.save_drive()
        self.assertEqual(status.snapshot()['drive_adapters']['verified_files'], 0)

    def test_no_private_prompt_path_url_or_unvalidated_source_text_is_exported(self):
        secret = 'https://private.example/?secret=PRIVATE_SENTINEL'
        self.config['private'] = secret; self.save_media()
        self.drive_receipt['private'] = secret; self.save_drive()
        raw = json.dumps(status.snapshot())
        for forbidden in (secret, str(self.root), str(self.ram), str(self.drive), 'private.example'):
            self.assertNotIn(forbidden, raw)

    def test_generation_requires_actual_decode_delivery_receipt_not_enabled_engine(self):
        path = self.root/'state/owner_media_acceptance/accepted_3456789.json'
        proof = {'schema': 'NOX_OWNER_MEDIA_ACCEPTANCE_V1', 'state': 'GENERATED_DECODED_AND_GPU_RELEASED',
                 'generation_verified': True, 'finished_at': time.time()-1, 'private_text_exported': False,
                 'pixels_exported': False, 'source_pins': {'runtime_sha256': status.RUNTIME_SHA},
                 'artifacts': [{'kind': kind, 'decode_verified': True, 'authenticated_http_verified': True,
                               'sha256': 'd'*64, 'decode': {'frames': frames}}
                              for kind, frames in (('image', 1), ('video', 9))]}
        write(path, proof)
        self.assertTrue(status.snapshot()['media']['generation_acceptance']['video']['verified'])
        proof['artifacts'][1]['decode_verified'] = False; write(path, proof)
        self.assertFalse(status.snapshot()['media']['generation_acceptance']['video']['verified'])

    def test_fifo_symlink_duplicate_json_and_path_replacement_are_rejected(self):
        fifo = self.base/'blocked'; os.mkfifo(fifo)
        started = time.monotonic()
        with self.assertRaises(status.StatusUnknown): status.read(fifo)
        self.assertLess(time.monotonic()-started, 0.5)
        symlink = self.base/'alias'; symlink.symlink_to(self.selection)
        with self.assertRaises(status.StatusUnknown): status.read(symlink)
        bad = self.base/'duplicates.json'; write(bad, b'{"a":1,"a":2}')
        with self.assertRaises(status.StatusUnknown): status.document(bad)
        target = self.base/'target'; write(target, b'abc')
        with self.assertRaises(status.StatusUnknown):
            with status.opened(target, 10):
                replacement = self.base/'replacement'; write(replacement, b'abc'); os.replace(replacement, target)

    def test_current_inventory_route_keeps_existing_owner_auth_and_no_store(self):
        app = FastAPI()
        async def legacy(): return 'legacy'
        ui.register_owner_chat_ui(app, {'_session_ok': lambda request: request.headers.get('x-fixture-owner') == 'yes',
            '_unauthorized': lambda: JSONResponse({'error': 'unauthorized'}, status_code=401), 'chat_page': legacy})
        with TestClient(app) as client, patch.object(status, 'snapshot', wraps=status.snapshot) as observed:
            self.assertEqual(client.get('/api/ui/downloads').status_code, 401)
            observed.assert_not_called()
            response = client.get('/api/ui/downloads', headers={'x-fixture-owner': 'yes'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(response.json()['media']['verified_files'], 4)

    def test_ui_script_parses(self):
        result = subprocess.run(['node', '--check', str(Path(__file__).with_name('owner-chat-ui.js'))], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())


if __name__ == '__main__':
    unittest.main()
