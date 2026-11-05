import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from nox_selfbuilder.firstboot_coordinator import FirstBootHold
from nox_selfbuilder.local_library_intake import scan_approved_local_library

NOW = datetime(2026, 11, 1, 18, 42, tzinfo=timezone.utc)


class LocalIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'approved'
        self.root.mkdir()
        self.proof_log = []
        self.stop_calls = 0
        self.epoch = 7
        self.policy = {'schema': 'NOX-ONEHOST-FIRSTBOOT-POLICY-v1',
                       'windows_sid_attested': True, 'source_lock_verified': True,
                       'signed_by_native_owner': True,
                       'allow_firstboot_downloads': True,
                       'installer_consent_recorded': True,
                       'expiry_utc': (NOW + timedelta(minutes=5)).isoformat(),
                       'approved_scan_roots': [str(self.root)]}

    def scan(self, **kw):
        def path_proof(session, path, stage):
            self.proof_log.append((path, stage))
            return kw.get('allow_path', True) and stage != kw.get('deny_stage')
        def stop():
            self.stop_calls += 1
            return kw.get('stop', False)
        def epoch():
            return kw.get('epoch', self.epoch)
        return scan_approved_local_library('NATIVE_SESSION', now=NOW,
                   native_policy=lambda _: self.policy,
                   native_path_proof=path_proof,
                   stop_requested=stop, stop_epoch=epoch)

    def test_real_file_sha_dedup_and_not_admitted(self):
        data = b'NOX source candidate\n'
        (self.root / 'a.py').write_bytes(data)
        (self.root / 'b.py').write_bytes(data)
        result = self.scan()
        self.assertEqual(result['files_examined'], 2)
        self.assertEqual(len(result['candidates']), 1)
        entry = result['candidates'][0]
        self.assertEqual(entry['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(entry['duplicate_paths'], 1)
        self.assertEqual(entry['status'], 'DISCOVERED_UNTRUSTED_NOT_IMPORTED')
        self.assertEqual(entry['license'], 'REVIEW_REQUIRED')
        self.assertFalse(result['source_executed'])
        self.assertFalse(result['imported_into_s03'])
        self.assertIn('POST_HASH', [x[1] for x in self.proof_log])

    def test_nested_only_within_root_and_no_exec(self):
        nested = self.root / 'models'
        nested.mkdir()
        (nested / 'tiny.gguf').write_bytes(b'model bytes')
        result = self.scan()
        self.assertEqual(result['candidates'][0]['kind'], 'MODEL_WEIGHTS')
        self.assertFalse(result['models_installed'])
        self.assertFalse(result['download_performed'])

    def test_reparse_link_denied(self):
        outside = Path(self.temp.name) / 'outside'
        outside.mkdir()
        (outside / 'hidden.py').write_text('private')
        try:
            (self.root / 'escape').symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('symlink requires privilege')
        with self.assertRaisesRegex(FirstBootHold, 'SYMLINK_REPARSE_DENIED'):
            self.scan()

    def test_unapproved_native_path_denied(self):
        (self.root / 'a.py').write_text('code')
        with self.assertRaisesRegex(FirstBootHold, 'NATIVE_PERMISSION_REQUIRED'):
            self.scan(allow_path=False)

    def test_consent_missing_denied_before_disk(self):
        self.policy['installer_consent_recorded'] = False
        (self.root / 'a.py').write_text('code')
        with self.assertRaisesRegex(FirstBootHold, 'OWNER_DOWNLOAD_CONSENT_REQUIRED'):
            self.scan()
        self.assertEqual(self.proof_log, [])

    def test_stop_denies_before_read(self):
        (self.root / 'a.py').write_text('code')
        with self.assertRaisesRegex(FirstBootHold, 'LOCAL_SCAN_STOP_OR_REVOKE'):
            self.scan(stop=True)

    def test_no_root_is_full_disk_scan(self):
        self.policy['approved_scan_roots'] = []
        with self.assertRaisesRegex(FirstBootHold, 'LOCAL_SCAN_EXPLICIT_ROOTS_REQUIRED'):
            self.scan()

    def test_nonapproved_extensions_skipped(self):
        (self.root / 'secrets.txt').write_text('unlisted data')
        self.assertEqual(self.scan()['files_examined'], 0)

    def test_file_budget_blocks_without_partial_success(self):
        from nox_selfbuilder import local_library_intake as module
        old = module.MAX_SCAN_BYTES
        try:
            module.MAX_SCAN_BYTES = 2
            (self.root / 'heavy.gguf').write_bytes(b'model')
            with self.assertRaisesRegex(FirstBootHold, 'BYTE_BUDGET_EXHAUSTED'):
                self.scan()
        finally:
            module.MAX_SCAN_BYTES = old

    def test_cross_category_equal_hash_is_not_silently_reclassified(self):
        (self.root / 'model.gguf').write_bytes(b'same bytes')
        (self.root / 'code.py').write_bytes(b'same bytes')
        with self.assertRaisesRegex(FirstBootHold, 'CONFLICTING_DIGEST_METADATA'):
            self.scan()

    def test_after_hash_native_grant_revoked(self):
        (self.root / 'model.gguf').write_bytes(b'model bytes')
        with self.assertRaisesRegex(FirstBootHold, 'REVOKED_AFTER_HASH'):
            self.scan(deny_stage='POST_HASH')

    def test_unbounded_ignored_directory_listing_denied(self):
        from nox_selfbuilder import local_library_intake as module
        old = module.MAX_SCAN_ENTRIES
        try:
            module.MAX_SCAN_ENTRIES = 3
            for index in range(4):
                (self.root / f'ignored{index}.txt').write_bytes(b'no scan')
            with self.assertRaisesRegex(FirstBootHold, 'DIRECTORY_ENTRY_LIMIT'):
                self.scan()
        finally:
            module.MAX_SCAN_ENTRIES = old

    def test_missing_callback_denied(self):
        with self.assertRaisesRegex(FirstBootHold, 'NATIVE_OWNER_PORTS_REQUIRED'):
            scan_approved_local_library('session', now=NOW,
              native_policy=lambda _: self.policy, native_path_proof=None,
              stop_requested=lambda: False, stop_epoch=lambda: 7)


if __name__ == '__main__':
    unittest.main()
