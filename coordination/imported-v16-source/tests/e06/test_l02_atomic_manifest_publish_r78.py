"""R78: fail-closed L02 final-manifest publication after partial disk failures."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / 'coordination/e06/l01_manifest_bridge.py'
spec = importlib.util.spec_from_file_location('nox_l02_original', SRC)
l02 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(l02)


class L02AtomicPublish(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        self.setup = self.dir / 'NOX-HELION-V16-DIAGNOSTIC-SETUP.exe'
        buf = bytearray(4096)
        buf[:2] = b'MZ'
        buf[60:64] = (128).to_bytes(4, 'little')
        buf[128:132] = b'PE\0\0'
        buf[132:134] = (0x14c).to_bytes(2, 'little')
        buf[152:154] = (0x10b).to_bytes(2, 'little')
        self.setup.write_bytes(buf)
        self.sha = hashlib.sha256(buf).hexdigest()
        self.receipt = self.dir / 'diagnostic_receipt.json'
        self.proof = dict(
            schema=l02.SCHEMA, one_visible_host=True, release_accepted=False,
            status='WINDOWS_INSTALLER_CANDIDATE_NOT_E07_ACCEPTED',
            installer_lifecycle_tested=False, installer_bytes=len(buf),
            installer_sha256=self.sha,
        )
        self.receipt.write_text(json.dumps(self.proof), encoding='utf-8')
        self.out = self.dir / 'candidate-release.txt'
        self.url = 'https://github.com/MSSTXNEWS/nox-helion-pp-private-build/releases/download/v16.0.0/' + self.setup.name

    def emit(self):
        return l02.emit(self.setup, self.receipt, self.url, 16, self.out)

    def test_atomic_publication_leaves_no_partial_final_on_fsync_failure(self):
        with patch.object(l02.os, 'fsync', side_effect=OSError('ENOSPC')):
            with self.assertRaises(OSError):
                self.emit()
        self.assertFalse(self.out.exists(), 'No incomplete manifest may look published')
        self.assertEqual(list(self.dir.glob(self.out.name + '.*.tmp')), [], 'All temporary bytes should be reclaimed')
        result = self.emit()  # after disk error is gone, same-RunId retry works
        self.assertEqual(result['status'], 'MANIFEST_SOURCE_CANDIDATE_NOT_OWNER_APPROVED')

    def test_success_is_exact_five_lines_and_stays_candidate_only(self):
        result = self.emit()
        raw = self.out.read_bytes()
        self.assertEqual(raw, f'{l02.PREFIX}\n16\n{self.url}\n4096\n{self.sha}\n'.encode('ascii'))
        self.assertEqual(result['manifest_sha256_for_L01_rebuild_after_owner_review'], hashlib.sha256(raw).hexdigest())
        self.assertIs(result['release_accepted'], False)
        self.assertIs(result['loader_auto_pinned'], False)

    def test_existing_output_never_clobbered(self):
        self.out.write_bytes(b'OWNER_EXISTING')
        with self.assertRaises(l02.Hold):
            self.emit()
        self.assertEqual(self.out.read_bytes(), b'OWNER_EXISTING')

    def test_tampered_setup_is_denied_before_output(self):
        self.setup.write_bytes(self.setup.read_bytes() + b'X')
        with self.assertRaises(l02.Hold):
            self.emit()
        self.assertFalse(self.out.exists())


if __name__ == '__main__':
    unittest.main()
