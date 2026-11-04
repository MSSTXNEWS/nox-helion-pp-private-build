"""Source-only negative admission tests; no Windows E07 PASS is asserted."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest

OWNER = Path(__file__).resolve().parents[2] / 'coordination/e06/e07_independent_sha_preflight.py'
spec = importlib.util.spec_from_file_location('e07_independent_sha_preflight', OWNER)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
COMMIT = 'b8ad64f1b2bd07ab268ef599e4d43994d294b0e3'


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def pe(marker: bytes) -> bytes:
    content = bytearray(b'\0' * 1024)
    content[:2] = b'MZ'
    content[0x3c:0x40] = struct.pack('<I', 0x80)
    content[0x80:0x84] = b'PE\0\0'
    content[0x90:0x90+len(marker)] = marker
    return bytes(content)


class FrozenIndependentShaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.setup = self.root / 'dist/setup.exe'
        self.published = self.root / 'dist/wpf.exe'
        self.installed_exe = self.root / 'installed/NOX.P01.Shell.exe'
        self.built = self.root / 'E07_BUILT_HANDOFF.json'
        self.installed = self.root / 'E07_INSTALLED_HANDOFF.json'
        self.setup.parent.mkdir()
        self.installed_exe.parent.mkdir()
        self.setup.write_bytes(pe(b'NSIS-original'))
        self.published.write_bytes(pe(b'WPF-original'))
        self.installed_exe.write_bytes(self.published.read_bytes())
        self.setup_sha = digest(self.setup.read_bytes())
        self.wpf_sha = digest(self.published.read_bytes())
        self.logs = {}
        hashes = {}
        for name in gate.LOG_NAMES:
            path = self.root / (name + '.log')
            path.write_bytes((name + ' actual independently supplied log\n').encode())
            self.logs[name] = path
            hashes[name] = digest(path.read_bytes())
        base = {'schema': 'NOX_V16_E07_IMMUTABLE_HANDOFF_V1',
                'build_id': 'NOX-V16-' + digest((gate.ORIGINAL_ZIP + '|' + COMMIT + '|' + self.setup_sha + '|' + self.wpf_sha).encode())[:24],
                'source_commit_sha1': COMMIT, 'original_zip_sha256': gate.ORIGINAL_ZIP,
                'original_manifest_sha256': 'a'*64,
                'owner_729_manifest_sha256': 'b'*64,
                'e06_onehost_receipt_sha256': 'c'*64,
                'setup_sha256': self.setup_sha, 'published_exe_sha256': self.wpf_sha,
                'source_receipts_729_parity_verified': True,
                'source_files': 729, 'independent_e07_cases_accepted': 0,
                'release_accepted': False}
        self.built_row = dict(base, phase='BUILT', installed_exe_sha256=None,
                              lifecycle_log_sha256={})
        self.installed_row = dict(base, phase='INSTALLED',
                                 installed_exe_sha256=self.wpf_sha,
                                 lifecycle_log_sha256=hashes)
        self.save()

    def save(self):
        self.built.write_text(json.dumps(self.built_row), encoding='utf-8')
        self.installed.write_text(json.dumps(self.installed_row), encoding='utf-8')

    def evaluate(self):
        return gate.check(self.built, self.installed, self.setup,
                          self.published, self.installed_exe, self.logs,
                          COMMIT, self.setup_sha)

    def held(self, code):
        with self.assertRaisesRegex(gate.Hold, code):
            self.evaluate()

    def test_valid_preflight_does_not_accept_e07(self):
        result = self.evaluate()
        self.assertEqual(result['status'], 'SHA_PREFLIGHT_PASS_NOT_E07_ACCEPTANCE')
        self.assertEqual(result['independent_e07_cases_accepted'], 0)
        self.assertIs(result['release_accepted'], False)

    def test_setup_different_physical_bytes_rejected(self):
        self.setup.write_bytes(pe(b'NSIS-tampered'))
        self.held('E07_INDEPENDENT_PHYSICAL_SETUP_SHA_DRIFT')

    def test_installed_binary_from_different_build_rejected(self):
        self.installed_exe.write_bytes(pe(b'WPF-changed'))
        self.held('E07_INDEPENDENT_INSTALLED_WPF_SHA_DRIFT')

    def test_both_handoffs_share_same_invalid_build_id_rejected(self):
        self.built_row['build_id'] = self.installed_row['build_id'] = 'NOX-V16-' + 'd'*24
        self.save()
        self.held('E07_INDEPENDENT_BUILDID_RECIPE_DRIFT')

    def test_cross_build_receipt_rejected(self):
        self.installed_row['build_id'] = 'NOX-V16-' + 'd'*24
        self.save()
        self.held('E07_INDEPENDENT_BUILD_INSTALLED_IDENTITY_DRIFT')

    def test_missing_lifecycle_log_rejected(self):
        self.logs['launch'].unlink()
        self.held('E07_INDEPENDENT_INPUT_MISSING')

    def test_changed_lifecycle_log_rejected(self):
        self.logs['rollback'].write_text('tampered', encoding='utf-8')
        self.held('E07_INDEPENDENT_LIFECYCLE_LOG_SHA_DRIFT:rollback')


    def test_one_log_cannot_impersonate_five_lifecycle_phases(self):
        first = self.logs['install']
        for name in gate.LOG_NAMES:
            self.logs[name] = first
            self.installed_row['lifecycle_log_sha256'][name] = digest(first.read_bytes())
        self.save()
        self.held('E07_INDEPENDENT_LIFECYCLE_LOG_ALIASED:launch')

    def test_lifecycle_log_cannot_alias_published_binary(self):
        self.logs['rollback'] = self.published
        self.installed_row['lifecycle_log_sha256']['rollback'] = self.wpf_sha
        self.save()
        self.held('E07_INDEPENDENT_LIFECYCLE_LOG_ALIASED:rollback')

    def test_lifecycle_log_cannot_alias_receipt(self):
        self.logs['update'] = self.built
        self.installed_row['lifecycle_log_sha256']['update'] = digest(self.built.read_bytes())
        self.save()
        self.held('E07_INDEPENDENT_LIFECYCLE_LOG_ALIASED:update')

    def test_hardlinked_lifecycle_log_cannot_impersonate_phase(self):
        link = self.root / 'hardlinked-rollback.log'
        try:
            link.hardlink_to(self.logs['install'])
        except OSError:
            self.skipTest('hardlinks unavailable')
        self.logs['rollback'] = link
        self.installed_row['lifecycle_log_sha256']['rollback'] = digest(link.read_bytes())
        self.save()
        self.held('E07_INDEPENDENT_LIFECYCLE_LOG_ALIASED:rollback')

    def test_duplicate_json_receipt_rejected(self):
        raw = self.built.read_text('utf-8')
        self.built.write_text(raw[:-1] + ', "release_accepted": true}', encoding='utf-8')
        self.held('E07_INDEPENDENT_AMBIGUOUS_RECEIPT_JSON_HOLD')

    def test_case_ambiguous_json_receipt_rejected(self):
        raw = self.built.read_text('utf-8')
        self.built.write_text(raw[:-1] + ', "Release_Accepted": true}', encoding='utf-8')
        self.held('E07_INDEPENDENT_AMBIGUOUS_RECEIPT_JSON_HOLD')

    def test_build_receipt_cannot_assert_release(self):
        self.built_row['release_accepted'] = True
        self.save()
        self.held('E07_INDEPENDENT_HANDOFF_CONTRACT_HOLD')

    def test_build_output_is_not_installed_binary(self):
        self.installed_exe = self.published
        self.held('E07_INDEPENDENT_INSTALLED_BINARY_NOT_SEPARATE')

    def test_symlink_ancestor_rejected(self):
        link = self.root / 'redirect'
        try:
            link.symlink_to(self.installed_exe.parent, target_is_directory=True)
        except OSError:
            self.skipTest('symlink not allowed on this host')
        self.installed_exe = link / self.installed_exe.name
        self.held('E07_INDEPENDENT_REPARSE_INPUT_HOLD')

    def test_identity_argument_pin_rejected(self):
        with self.assertRaisesRegex(gate.Hold, 'E07_INDEPENDENT_EXPECTED_IDENTITY_INVALID'):
            gate.check(self.built,self.installed,self.setup,self.published,
                       self.installed_exe,self.logs,COMMIT, '0'*63)


if __name__ == '__main__':
    unittest.main()
