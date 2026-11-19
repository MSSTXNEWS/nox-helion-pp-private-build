"""Small actual crypto/archive tests; never native files, private owner key or network."""
import base64
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

import owner_qwen6_backup_stream as core
import owner_qwen6_backup_local as local
import owner_qwen6_backup_runner as runner


class CryptoArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=4096)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.output = self.root / 'lora/qwen35_9b/6907283384'
        self.cp = self.output / core.CHECKPOINT
        self.cp.mkdir(parents=True); (self.root / 'state').mkdir()
        lineage = {'schema': 'TEST_LOCAL_SYNTHETIC_ONLY', 'runtime_versions': {'python': '3.12'}}
        self.data = {name: (b'opaque bytes, never unpickle: ' + name.encode()) for name in core.CHECKPOINT_NAMES}
        updates = [{'fixture': i} for i in range(6)]
        state = {'successful_total': 6, 'attempted_total': 6, 'skipped_total': 0,
                 'holdout_evaluated_successful_total': 6, 'update_evidence': updates}
        for name, value in [('lineage.json', lineage), ('student_state.json', state),
                            ('adapter_config.json', {'rank': 8}), ('python_rng.json', {'state': [1, 2, 3]})]:
            self.data[name] = core.canonical(value) + b'\n'
        total = sum(map(len, self.data.values()))
        line_sha = core.digest(core.canonical(lineage))
        line_file_sha = core.digest(self.data['lineage.json'])
        manifest = {'schema': 'NOX_QWEN35_9B_CHECKPOINT_V1', 'directory': core.CHECKPOINT,
                    'successful_total': 6, 'attempted_total': 6, 'lineage_sha256': line_sha,
                    'adapter_tensor_sha256': 'a' * 64,
                    'files_sha256': {name: core.digest(raw) for name, raw in self.data.items()}}
        self.data['checkpoint_manifest.json'] = core.canonical(manifest) + b'\n'
        man_sha = core.digest(self.data['checkpoint_manifest.json'])
        cert = {'schema': 'NOX_QWEN35_9B_UPDATE_PROOF_V1', 'state': 'STUDENT_RESTART_AND_UPDATES_VERIFIED',
                'successful_optimizer_steps': 6, 'new_successful_optimizer_steps': 1,
                'attempted_steps': 6, 'skipped_steps': 0, 'reload_verified': True,
                'independent_holdout_accepted': True, 'holdout_finite': True,
                'holdout_evaluated_successful_total': 6, 'base_manifest_sha256': core.BASE_MANIFEST_SHA,
                'lineage_sha256': line_sha, 'checkpoint_manifest_sha256': man_sha,
                'checkpoint': str(self.cp), 'update_evidence': updates, 'final_adapter_tensor_sha256': 'a' * 64}
        self.data['owner_acceptance.json'] = core.canonical(cert) + b'\n'
        window = {'schema': 'NOX_QWEN_WINDOW_ADVANCE_V1', 'request': core.WINDOW_REQUEST,
                  'source_sha': core.WINDOW_SOURCE, 'initial_request': '6907283384',
                  'target_goal': 6, 'state': 'WINDOW_STARTED_ACCEPTANCE_PENDING'}
        self.data['window6_receipt.json'] = core.canonical(window) + b'\n'
        self.pins = patch.multiple(core, ROOT=self.root, OUTPUT=self.output, CHECKPOINT_BYTES=total,
                                   MANIFEST_SHA=man_sha, ACCEPTANCE_SHA=core.digest(self.data['owner_acceptance.json']),
                                   LINEAGE_SHA=line_sha, LINEAGE_FILE_SHA=line_file_sha,
                                   WINDOW_SHA=core.digest(self.data['window6_receipt.json']))
        self.pins.start()
        for name in core.CHECKPOINT_NAMES + ('checkpoint_manifest.json',):
            (self.cp / name).write_bytes(self.data[name])
        (self.output / 'owner_acceptance.json').write_bytes(self.data['owner_acceptance.json'])
        (self.output / 'owner_lineage.json').write_bytes(self.data['lineage.json'])
        (self.root / 'state' / ('owner_qwen_window_' + core.WINDOW_REQUEST + '.json')).write_bytes(self.data['window6_receipt.json'])
        public = self.key.public_key()
        now = int(time.time())
        self.public = {'schema': core.KEY_SCHEMA, 'scope_sha256': core.scope_sha(), 'transfer_id': 'f' * 32,
                       'created_at': now - 1, 'expires_at': now + 600,
                       'public_key_pem': public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode(),
                       'key_id': core.digest(public.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo))}

    def tearDown(self):
        self.pins.stop(); self.tmp.cleanup()

    def export(self):
        buffer = io.BytesIO()
        native = core.export(self.public, 'b' * 40, '123', buffer, core.Budget())
        return buffer.getvalue(), native

    def parts(self, wire, native, sub='parts'):
        sink = runner.CipherParts(self.root / sub)
        for offset in range(0, len(wire), 619):
            sink.write(wire[offset:offset + 619])
        sink.close(); sink.readback()
        receipt = {'schema': local.RECEIPT_SCHEMA, 'state': 'CIPHERTEXT_READY_LOCAL_VERIFICATION_REQUIRED',
                   'scope_sha256': core.scope_sha(), 'ciphertext_bytes': len(wire),
                   'ciphertext_sha256': core.digest(wire), 'parts': sink.rows, 'native': native}
        return sink.directory, local.receipt_document(core.canonical(receipt))

    def test_actual_crypto_full_file_restore_and_private_parts(self):
        wire, native = self.export()
        self.assertNotIn(b'opaque bytes', wire)
        directory, receipt = self.parts(wire, native)
        destination = self.root / 'restore'
        result = local.verify(directory, receipt, self.public, self.key, 'b' * 40, '123', destination)
        self.assertTrue(result['all_file_sha256_verified'])
        self.assertEqual(set(result['files']), set(core.NAMES))
        self.assertEqual({n: r['sha256'] for n, r in result['files'].items()}, {n: core.digest(self.data[n]) for n in core.NAMES})
        self.assertFalse(result['drive_copy_verified'])
        self.assertFalse(result['gpu_restart_performed'])
        for row in result['plaintext_archive_parts']:
            p = destination / row['name']
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertEqual(core.digest(p.read_bytes()), row['sha256'])
        self.assertTrue((destination / 'QWEN6_RESTORE_MANIFEST.json').is_file())
        readback = local.verify_restore(destination, result, 'b' * 40, '123')
        self.assertTrue(readback['all_file_sha256_verified'])
        self.assertFalse(readback['private_key_required'])
        self.assertEqual(readback['verified_files'], 13)

    def test_plaintext_restore_parts_are_independently_verified_without_key(self):
        wire, native = self.export(); directory, receipt = self.parts(wire, native)
        destination = self.root / 'restore'
        result = local.verify(directory, receipt, self.public, self.key, 'b' * 40, '123', destination)
        p = destination / result['plaintext_archive_parts'][0]['name']
        original = p.read_bytes(); p.write_bytes(original[:-1] + b'x')
        with self.assertRaises(core.Hold):
            local.verify_restore(destination, result, 'b' * 40, '123')

    def test_modified_gcm_tag_fails_before_plaintext_publication(self):
        wire, native = self.export()
        damaged = wire[:-1] + bytes([wire[-1] ^ 1])
        native = {**native, 'ciphertext_sha256': core.digest(damaged)}
        directory, receipt = self.parts(damaged, native)
        destination = self.root / 'never_created'
        with self.assertRaises(Exception):
            local.verify(directory, receipt, self.public, self.key, 'b' * 40, '123', destination)
        self.assertFalse(destination.exists())

    def test_metadata_mutation_fails_before_ciphertext(self):
        (self.cp / 'student_state.json').write_bytes(b'{"successful_total":7}')
        buffer = io.BytesIO()
        with self.assertRaises(core.Hold):
            core.export(self.public, 'b' * 40, '123', buffer, core.Budget())
        self.assertEqual(buffer.getvalue(), b'')

    def test_post_stream_source_mutation_never_releases_tag(self):
        output = io.BytesIO()
        original = core.Snapshot.reverify
        def change(snapshot):
            path = self.cp / 'optimizer.pt'; path.write_bytes(b'changed')
            return original(snapshot)
        with patch.object(core.Snapshot, 'reverify', change), self.assertRaises(core.Hold):
            core.export(self.public, 'b' * 40, '123', output, core.Budget())
        wire = output.getvalue()
        size = struct.unpack('>I', wire[8:12])[0]
        header = core.document(wire[12:12 + size])
        self.assertEqual(len(wire), 12 + size + header['archive_bytes'])

    def test_symlink_member_rejected_before_any_export(self):
        p = self.cp / 'optimizer.pt'; p.unlink(); p.symlink_to(self.cp / 'scaler.pt')
        buffer = io.BytesIO()
        with self.assertRaises(OSError):
            core.export(self.public, 'b' * 40, '123', buffer, core.Budget())
        self.assertEqual(buffer.getvalue(), b'')

    def test_expired_public_key_and_wrong_run_rejected(self):
        with self.assertRaises(core.Hold):
            core.public_key(self.public, now=self.public['expires_at'] + 1)
        wire, native = self.export(); directory, receipt = self.parts(wire, native)
        with self.assertRaises(core.Hold):
            local.verify(directory, receipt, self.public, self.key, 'c' * 40, '123')

    def test_missing_reordered_or_changed_part_rejected(self):
        wire, native = self.export()
        with patch.object(core, 'PART_BYTES', 4096):
            directory, receipt = self.parts(wire, native)
            self.assertGreater(len(receipt['parts']), 1)
            bad = json.loads(core.canonical(receipt)); bad['parts'].reverse()
            with self.assertRaises(core.Hold):
                local.receipt_document(core.canonical(bad))
            p = directory / receipt['parts'][0]['name']
            p.write_bytes(b'x' * p.stat().st_size)
            with self.assertRaises(core.Hold):
                local.verify(directory, receipt, self.public, self.key, 'b' * 40, '123')

    def test_private_key_permissions_checked_without_log_contents(self):
        p = self.root / 'synthetic_private.pem'
        p.write_bytes(self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        p.chmod(0o644)
        with self.assertRaisesRegex(core.Hold, 'PRIVATE_KEY_PERMISSIONS'):
            local.private_key(p, self.public)
        p.chmod(0o600)
        self.assertEqual(local.private_key(p, self.public).private_numbers(), self.key.private_numbers())

    def test_binary_runner_stream_receives_no_plaintext_or_huge_log(self):
        wire, native = self.export()
        code = ('import sys,base64;sys.stdin.buffer.read();'
                'sys.stdout.buffer.write(base64.b64decode(' + repr(base64.b64encode(wire).decode()) + '));'
                'sys.stderr.write(' + repr('NOX_QWEN6_EXPORT=' + core.canonical(native).decode() + '\n') + ')')
        original = subprocess.Popen
        def local_child(*_args, **kwargs):
            return original([sys.executable, '-c', code], **kwargs)
        parts = runner.CipherParts(self.root / 'pipe-parts')
        with patch.object(runner.subprocess, 'Popen', local_child):
            header, observed = runner.receive([], 'ignored', b'pass\n', self.public, parts)
        self.assertEqual(observed, native)
        self.assertEqual(parts.hash.hexdigest(), core.digest(wire))
        self.assertEqual(header['archive_format'], 'USTAR_UNCOMPRESSED')

    def test_native_failure_surfaces_only_safe_reason_and_no_receipt(self):
        code = "import sys;sys.stdin.buffer.read();sys.stderr.write('private arbitrary text\\nNOX_QWEN6_EXPORT_HOLD=HOLD_QWEN6_BACKUP_POST_EXPORT_SHA\\n');sys.exit(2)"
        original = subprocess.Popen
        def local_child(*_args, **kwargs):
            return original([sys.executable, '-c', code], **kwargs)
        parts = runner.CipherParts(self.root / 'failed-pipe')
        with patch.object(runner.subprocess, 'Popen', local_child), self.assertRaisesRegex(core.Hold, '^HOLD_QWEN6_BACKUP_POST_EXPORT_SHA$'):
            runner.receive([], 'ignored', b'pass\n', self.public, parts)
        self.assertFalse((parts.directory / 'QWEN6_CIPHER_RECEIPT.json').exists())

    def test_archive_and_metadata_limits_are_real(self):
        with patch.object(core, 'MAX_TOTAL', 1):
            with self.assertRaises(core.Hold):
                self.export()
        with self.assertRaises(core.Hold):
            core.document(b'{"a":NaN}')
        with self.assertRaises(core.Hold):
            core.document(b'{"a":1,"a":2}')


class TransportScopeTests(unittest.TestCase):
    def test_current_auth_prefix_is_exact_and_stops_before_payload(self):
        ns = runner.authentication_namespace()
        self.assertEqual(ns['INSTANCE'], 60509551)
        self.assertEqual(ns['PIN'], runner.HOST_PIN)
        self.assertIsNone(ns['MASTER'])
        self.assertNotIn('payload', ns['run_native'].__code__.co_names)
        self.assertIs(ns['run_native'].__globals__.get('re'), runner.re)

    def test_push_never_authorizes_export_even_as_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'event.json'
            path.write_text(json.dumps({'inputs': {'allow_native': 'YES', 'checkpoint_scope': 'QWEN6'},
                                        'sender': {'id': runner.OWNER_ID}, 'repository': {'owner': {'id': runner.OWNER_ID}}}))
            env = {'GITHUB_EVENT_PATH': str(path), 'GITHUB_EVENT_NAME': 'push', 'GITHUB_REPOSITORY': runner.REPO,
                   'GITHUB_ACTOR': 'MSSTXNEWS', 'GITHUB_ACTOR_ID': str(runner.OWNER_ID), 'GITHUB_RUN_ATTEMPT': '1'}
            with patch.dict(os.environ, env, clear=True), self.assertRaises(core.Hold):
                runner.authorize_event()

    def test_manual_source_mismatch_never_authenticates(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'event.json'
            path.write_text(json.dumps({'inputs': {'allow_native': 'YES', 'checkpoint_scope': 'QWEN6', 'source_sha': 'a' * 40},
                                        'sender': {'id': runner.OWNER_ID}, 'repository': {'owner': {'id': runner.OWNER_ID}}}))
            env = {'GITHUB_EVENT_PATH': str(path), 'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REPOSITORY': runner.REPO,
                   'GITHUB_ACTOR': 'MSSTXNEWS', 'GITHUB_ACTOR_ID': str(runner.OWNER_ID), 'GITHUB_RUN_ATTEMPT': '1',
                   'NOX_PINNED_SOURCE_SHA': 'b' * 40, 'GITHUB_SHA': 'b' * 40,
                   'GITHUB_WORKFLOW_REF': runner.REPO + '/' + runner.WORKFLOW + '@refs/heads/test'}
            with patch.dict(os.environ, env, clear=True), self.assertRaises(core.Hold):
                runner.authorize_event()

    def test_workflow_retains_manual_only_native_and_legacy_default(self):
        source = (runner.REPOSITORY / runner.WORKFLOW).read_text()
        self.assertIn("default: 'LEGACY'", source)
        self.assertIn("inputs.checkpoint_scope == 'QWEN6'", source)
        self.assertIn("!inputs.checkpoint_scope || inputs.checkpoint_scope == 'LEGACY'", source)
        self.assertEqual(source.count('name: NOX_QWEN6_CIPHER_${{ github.run_id }}_PART_'), 7)
        qwen = source.split('  qwen6-export:', 1)[1]
        self.assertIn("github.event_name == 'workflow_dispatch'", qwen)
        self.assertNotIn('if: always()\n        uses: actions/upload-artifact', qwen)

    def test_exact_public_key_and_native_source_package_pins(self):
        data = core.document((runner.REPOSITORY / 'nox-control/owner_qwen6_backup_public.json').read_bytes())
        with patch.object(runner.time, 'time', return_value=data['created_at']):
            raw, public = runner.package()
        self.assertEqual(core.digest(raw), runner.CORE_SHA)
        self.assertEqual(core.digest(public['public_key_pem'].encode()), runner.PUBLIC_PEM_SHA)


if __name__ == '__main__':
    unittest.main()
