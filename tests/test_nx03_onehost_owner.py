"""OneHost native NX-03 binding tests: mocked model, NOT installed Windows E07."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from nox_selfbuilder.onehost_builder import OneHostSelfBuilder
from nox_selfbuilder.p02_coder import P02Coder
from nox_selfbuilder.firstcycle_native import sha256
from nox_selfbuilder.nx03_model_firstcycle import SCHEMA, TARGET

HEAD = "a" * 40
BEFORE = b"def summarize_status(items):\n    return len(items)\n"
AFTER = b"def summarize_status(items):\n    return {'ready': sum(1 for x in items if x.get('status') == 'READY')}\n"


class Session:
    tenant = "native-tenant"
    principal = "windows-owner"
    chat_id = "owner-chat"
    allowed = frozenset({"chat.commands"})
    def validate(self):
        return None


class CoderDouble(P02Coder):
    def __init__(self):
        self.called = 0
    def __call__(self, session, request):
        self.called += 1
        return json.dumps({"schema": SCHEMA, "relative_path": TARGET,
                           "source": AFTER.decode("utf-8")})


class SourceDouble:
    def __init__(self, root):
        self.root = root
        self.good = True
    def head(self):
        return HEAD
    def admitted(self, head):
        return head == HEAD and self.good


class NX03OneHostTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.workspace = self.root / "staging"
        self.workspace.mkdir()
        self.target = self.workspace / TARGET
        self.target.parent.mkdir(parents=True)
        self.target.write_bytes(BEFORE)
        self.coder = CoderDouble()
        self.session = Session()
        self.actions = []
        self.allowed = {"selfbuilder.source.test", "selfbuilder.source.apply",
                        "selfbuilder.source.rollback"}
        self.owner = OneHostSelfBuilder(
            queue=object(), coder=self.coder, memory_scope=lambda session: {},
            authorize=lambda session, action, scope: self.authorize(session, action, scope),
            stop_requested=lambda: False, stop_epoch=lambda: 5,
            source_root=self.root / "managed", workspace=self.workspace)
        (self.root / "managed").mkdir()
        self.owner.source = SourceDouble(self.root / "managed")
    def authorize(self, session, action, scope):
        self.actions.append(action)
        return session is self.session and action in self.allowed
    def execute_cycle(self):
        def native_ack(scope):
            return {**scope, "status": "SELFWRITE_ACK", "epoch": 5}
        return self.owner.native_p02_firstcycle(
            self.session, source_head=HEAD, task_id="NX03-OWNER",
            task="Improve approved read-only model status summary",
            preimage_sha256=sha256(BEFORE), native_ack=native_ack,
            run_isolated_test=lambda candidate: candidate == AFTER)
    def test_onehost_owner_applies_and_restores_bytes(self):
        receipt = self.execute_cycle()
        self.assertEqual(receipt["status"], "MODEL_CANDIDATE_SANDBOX_ROLLBACK_VERIFIED")
        self.assertEqual(self.target.read_bytes(), BEFORE)
        self.assertEqual(self.coder.called, 1)
        self.assertEqual(self.actions, ["selfbuilder.source.test",
                                        "selfbuilder.source.apply",
                                        "selfbuilder.source.rollback"])
        self.assertFalse(receipt["selfbuild_ready"])
    def test_dirty_source_holds_before_generation(self):
        self.owner.source.good = False
        with self.assertRaises(PermissionError):
            self.execute_cycle()
        self.assertEqual(self.coder.called, 0)
    def test_revoked_owner_holds_before_generation(self):
        self.owner.native_stop = lambda: True
        with self.assertRaises(PermissionError):
            self.execute_cycle()
        self.assertEqual(self.coder.called, 0)
    def test_missing_native_apply_grant_holds(self):
        self.allowed.remove("selfbuilder.source.apply")
        with self.assertRaises(Exception):
            self.execute_cycle()
        self.assertEqual(self.target.read_bytes(), BEFORE)
    def test_renderer_command_cannot_invoke_native_method(self):
        with self.assertRaisesRegex(ValueError, "UNKNOWN_SELFBUILDER_ACTION"):
            self.owner.command(self.session, {"action": "selfbuilder.native.p02.firstcycle"})
        self.assertEqual(self.coder.called, 0)


if __name__ == "__main__":
    unittest.main()
