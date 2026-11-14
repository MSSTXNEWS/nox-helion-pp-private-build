"""Real P04 module regression: rights-verifier timeout/outage is a HOLD, never GPU training."""
import hashlib, importlib.util, json, subprocess, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[2]/"Packages"/"P04"/"train_qlora.py"
spec = importlib.util.spec_from_file_location("p04_r14", SRC)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)

class RightsAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.train, self.holdout = root/"train.jsonl", root/"holdout.jsonl"
        self.train.write_text('{"text":"train"}\n', encoding="utf-8")
        self.holdout.write_text('{"text":"holdout"}\n', encoding="utf-8")
        self.verifier = root/"verifier"
        self.verifier.write_text("placeholder", encoding="utf-8")
        self.manifest = root/"manifest.json"
        self.meta = {
            "schema":"nox-dataset-consent-v1", "rights_status":"APPROVED",
            "consent_status":"GRANTED", "dataset_id":"d", "dataset_revision":"r",
            "license_id":"L", "owner_approval_id":"A",
            "train_sha256":hashlib.sha256(self.train.read_bytes()).hexdigest(),
            "holdout_sha256":hashlib.sha256(self.holdout.read_bytes()).hexdigest()
        }
        self.manifest.write_text(json.dumps(self.meta), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def check(self):
        return worker.verify_manifest(self.manifest, self.train, self.holdout, self.verifier)

    def test_timeout_rejected_before_cuda(self):
        with patch.object(worker.subprocess, "run", side_effect=subprocess.TimeoutExpired("verifier", 30)) as invoke:
            with self.assertRaisesRegex(ValueError, "^RIGHTS_VERIFIER_UNAVAILABLE$"): self.check()
            invoke.assert_called_once()
            self.assertEqual(invoke.call_args.kwargs["timeout"], 30)
            self.assertEqual(invoke.call_args.kwargs["shell"], False)

    def test_oserror_rejected_before_cuda(self):
        for error in (FileNotFoundError("not found"), PermissionError("denied")):
            with self.subTest(error=type(error).__name__), patch.object(worker.subprocess, "run", side_effect=error):
                with self.assertRaisesRegex(ValueError, "^RIGHTS_VERIFIER_UNAVAILABLE$"): self.check()

    def test_verifier_denial_retained(self):
        with patch.object(worker.subprocess, "run", return_value=SimpleNamespace(returncode=1, stdout="")):
            with self.assertRaisesRegex(ValueError, "^RIGHTS_VERIFIER_REJECTED_MANIFEST$"): self.check()

    def test_positive_attestation_retained(self):
        attest = {
            "schema":"nox-rights-attestation-v1", "status":"VERIFIED",
            "manifest_sha256":hashlib.sha256(self.manifest.read_bytes()).hexdigest(),
            "dataset_id":self.meta["dataset_id"], "dataset_revision":self.meta["dataset_revision"],
            "license_id":self.meta["license_id"], "owner_approval_id":self.meta["owner_approval_id"],
            "train_sha256":self.meta["train_sha256"], "holdout_sha256":self.meta["holdout_sha256"],
            "intent":"training", "attestation_id":"verified-r14"
        }
        with patch.object(worker.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=json.dumps(attest))):
            self.assertEqual(self.check()["_rights_attestation_id"], "verified-r14")

    def test_unavailable_maps_to_hold(self):
        self.assertEqual(worker.classify_training_failure(ValueError("RIGHTS_VERIFIER_UNAVAILABLE")), "HOLD")
        self.assertEqual(worker.classify_training_failure(ValueError("UNKNOWN")), "ERROR")

if __name__ == "__main__": unittest.main()
