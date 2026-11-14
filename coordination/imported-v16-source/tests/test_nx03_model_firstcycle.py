"""NX-03 contract checks; the P02 double is NOT real installed Ollama/E07."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nox_selfbuilder.firstcycle_native import sha256
from nox_selfbuilder.p02_coder import P02Coder
from nox_selfbuilder.nx03_model_firstcycle import (
    run_native_model_cycle, parse_model_source, NX03Hold, TARGET, SCHEMA)

HEAD = "a" * 40
BEFORE = b"def summarize_status(items):\n    return len(items)\n"
AFTER = (b"def summarize_status(items):\n"
         b"    return {'ready': sum(1 for x in items if x.get('status') == 'READY')}\n")


class Session:
    def validate(self):
        return None


class ModelDouble(P02Coder):
    def __init__(self):
        self.raw = json.dumps({"schema": SCHEMA, "relative_path": TARGET,
                               "source": AFTER.decode("utf-8")})
        self.calls = 0
    def __call__(self, session, request):
        self.calls += 1
        assert request["native_write_authorized"] is False
        assert request["source_head"] == HEAD
        return self.raw


class NX03Tests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="nx03-contract-")
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.target = self.root / TARGET
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(BEFORE)
        self.coder = ModelDouble()
        self.allowed = {"selfbuilder.source.test", "selfbuilder.source.apply",
                        "selfbuilder.source.rollback"}
        self.epoch = 3
        self.head = HEAD
        self.stop = False
        self.actions = []
    def cycle(self):
        def ack(scope):
            return {**scope, "status": "SELFWRITE_ACK", "epoch": self.epoch}
        def authorize(session, action, scope):
            self.actions.append(action)
            return session == "native-owner" and action in self.allowed
        return run_native_model_cycle(
            coder=self.coder, native_session=Session(),
            session_token="native-owner", source_head=HEAD,
            task_id="NX03-TEST", task="Improve the read-only status summary",
            workspace=self.root, preimage_sha256=sha256(BEFORE),
            current_head=lambda: self.head, stop_epoch=lambda: self.epoch,
            stopped=lambda: self.stop, native_ack=ack, authorize=authorize,
            run_isolated_test=lambda source: source == AFTER)
    def test_model_candidate_apply_and_exact_rollback(self):
        result = self.cycle()
        self.assertEqual(result["status"], "MODEL_CANDIDATE_SANDBOX_ROLLBACK_VERIFIED")
        self.assertFalse(result["selfbuild_ready"])
        self.assertFalse(result["installed_windows_e07"])
        self.assertEqual(self.target.read_bytes(), BEFORE)
        self.assertEqual(self.actions, ["selfbuilder.source.test",
                                        "selfbuilder.source.apply",
                                        "selfbuilder.source.rollback"])
    def test_duplicate_json_rejected(self):
        with self.assertRaises(NX03Hold):
            parse_model_source('{"source":"x","source":"y"}')
        self.assertEqual(self.target.read_bytes(), BEFORE)
    def test_model_cannot_choose_path(self):
        self.coder.raw = json.dumps({"schema": SCHEMA, "relative_path": "../else.py",
                                      "source": AFTER.decode("utf-8")})
        with self.assertRaises(NX03Hold):
            self.cycle()
        self.assertEqual(self.target.read_bytes(), BEFORE)
    def test_model_import_rejected(self):
        self.coder.raw = json.dumps({"schema": SCHEMA, "relative_path": TARGET,
                                      "source": "import os\ndef summarize_status(items): return len(items)"})
        with self.assertRaises(NX03Hold):
            self.cycle()
    def test_stop_before_generation(self):
        self.stop = True
        with self.assertRaises(NX03Hold):
            self.cycle()
        self.assertEqual(self.coder.calls, 0)
    def test_head_drift_before_generation(self):
        self.head = "b" * 40
        with self.assertRaises(NX03Hold):
            self.cycle()
        self.assertEqual(self.coder.calls, 0)
    def test_apply_requires_independent_native_grant(self):
        self.allowed.remove("selfbuilder.source.apply")
        with self.assertRaises(Exception):
            self.cycle()
        self.assertEqual(self.target.read_bytes(), BEFORE)
    def test_rollback_denial_never_claims_success(self):
        self.allowed.remove("selfbuilder.source.rollback")
        with self.assertRaisesRegex(NX03Hold, "NX03_ROLLBACK_NOT_VERIFIED"):
            self.cycle()
        self.assertEqual(self.target.read_bytes(), AFTER)


if __name__ == "__main__":
    unittest.main()
