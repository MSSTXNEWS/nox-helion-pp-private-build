"""W12 R115: local consent file revocation must stop QLoRA before/in GPU steps."""
import hashlib, pathlib, tempfile, unittest, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "Packages" / "P04"))
import train_qlora as p04

class ConsentSnapshot(unittest.TestCase):
    def test_unchanged_approved_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)/"consent.json"
            p.write_bytes(b'{"consent_status":"GRANTED"}\n')
            self.assertIsNone(p04.require_training_consent_unchanged(p, hashlib.sha256(p.read_bytes()).hexdigest()))
    def test_explicit_revocation(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)/"consent.json"
            p.write_bytes(b'{"consent_status":"GRANTED"}\n')
            authorized = hashlib.sha256(p.read_bytes()).hexdigest()
            p.write_bytes(b'{"consent_status":"REVOKED"}\n')
            with self.assertRaisesRegex(RuntimeError, "P04_TRAINING_CONSENT_CHANGED"):
                p04.require_training_consent_unchanged(p, authorized)
    def test_deleted_consent(self):
        with tempfile.TemporaryDirectory() as d:
            p = pathlib.Path(d)/"consent.json"
            p.write_bytes(b'{"consent_status":"GRANTED"}\n')
            authorized = hashlib.sha256(p.read_bytes()).hexdigest()
            p.unlink()
            with self.assertRaisesRegex(RuntimeError, "P04_TRAINING_CONSENT_CHANGED"):
                p04.require_train¶»§q«^