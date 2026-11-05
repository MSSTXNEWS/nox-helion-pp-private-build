"""Focused negative/positive source-level tests for immutable R11 first-failure witness."""
import hashlib
import json
import shutil
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'coordination' / 'e06'))
from t06_nsis_registry_readonly_witness import SOURCE_PARTS, witness, _plain_components


class TestR11RegistryReadonlyWitness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root.joinpath(*SOURCE_PARTS)
        self.path.parent.mkdir(parents=True)

    def _capture(self, contents):
        self.path.write_bytes(contents)
        result = witness(self.root, expected_sha=hashlib.sha256(contents).hexdigest(),
                         expected_bytes=len(contents))
        self.assertFalse(result['release_accepted'])
        self.assertFalse(result['e07_tested'])
        return result

    def test_exact_immutable_line_observation_is_bounded_and_not_pass(self):
        raw = b'Name "NOX"\r\n  WriteRegStr HKCU "owner" "UninstallString" \'\\"$INSTDIR\\Uninstall.exe\\"\'\r\n'
        result = self._capture(raw)
        self.assertEqual(result['status'], 'WITNESS_CAPTURED_NOT_BUILD_ACCEPTANCE')
        self.assertEqual(result['marker_count'], 1)
        self.assertEqual(result['markers'][0]['line_number'], 2)
        self.assertIn('UninstallString', result['markers'][0]['line_escaped'])
        self.assertNotIn(str(self.root), json.dumps(result))

    def test_unknown_sha_hides_source_line(self):
        self.path.write_bytes(b'WriteRegStr x "UninstallString" "value"\n')
        result = witness(self.root)
        self.assertEqual(result['status'], 'R11_WITNESS_UNEXPECTED_SOURCE_SHA_HOLD')
        self.assertEqual(result['markers'], [])

    def test_unknown_or_multiple_markers_do_not_count_as_single_proof(self):
        missing = self._capture(b'Name "NOX"\n')
        self.assertEqual(missing['status'], 'R11_WITNESS_NO_UNINSTALLSTRING_MARKER_HOLD')
        duplicate = self._capture(b'UninstallString 1\nUninstallString 2\n')
        self.assertEqual(duplicate['status'], 'R11_WITNESS_MULTIPLE_UNINSTALLSTRING_MARKERS_HOLD')

    def test_bound_line_length_and_no_absolute_paths(self):
        raw = b'UninstallString ' + b'X' * 400
        result = self._capture(raw)
        self.assertEqual(result['marker_count'], 1)
        self.assertIsNone(result['markers'][0]['line_escaped'])
        self.assertEqual(result['markers'][0]['line_bytes'], len(raw))

    def test_missing_source_does_not_claim_evidence(self):
        result = witness(self.root)
        self.assertEqual(result['status'], 'WITNESS_NOT_AVAILABLE_HOLD')
        self.assertIsNone(result['source_sha256'])

    def test_symlinked_ancestor_rejected_without_follow(self):
        link = self.root / 'work' / 'e06' / 'staged'
        shutil.rmtree(link)  # disposable fixture only: make ancestor replaceable
        with tempfile.TemporaryDirectory() as outside:
            try:
                link.symlink_to(outside, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest('symlink creation unavailable')
            with self.assertRaisesRegex(ValueError, 'REPARSE_HOLD'):
                witness(self.root)

    def test_source_file_symlink_rejected(self):
        external = self.root / 'external.nsi'
        external.write_bytes(b'UninstallString secret')
        try:
            self.path.symlink_to(external)
        except (OSError, NotImplementedError):
            self.skipTest('symlink creation unavailable')
        with self.assertRaisesRegex(ValueError, 'REPARSE_HOLD'):
            witness(self.root)


if __name__ == '__main__':
    unittest.main()
