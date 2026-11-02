"""Fail closed if original native A1 authorization races STOP or source HEAD.

Source-level test only: no mock grant may certify a Windows E07 result.
"""
import hashlib
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "src/nox_selfbuilder/a1_native_command.py"
SPEC = importlib.util.spec_from_file_location("nox_original_a1_gate_regression", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class A1NativeAuthorizeRace(unittest.TestCase):
    def command(self, mutate=None):
        cmd = object.__new__(MODULE.A1NativeCommand)
        state = {"stopped": False, "epoch": 2, "head": "a" * 40}
        cmd._stopped = lambda: state["stopped"]
        cmd._epoch = lambda: state["epoch"]
        cmd._head = lambda: state["head"]
        def authorize(session, action):
            if mutate is not None:
                mutate(state)
            return True
        cmd._authorize = authorize
        return cmd, state

    def test_stop_during_native_acl_denies(self):
        cmd, _ = self.command(lambda s: s.update(stopped=True, epoch=3))
        with self.assertRaisesRegex(MODULE.A1NativeHold, "A1_NATIVE_STOP_OR_HEAD_CHANGED_DURING_AUTH"):
            cmd._gate(None, "evolution.autonomy.read")

    def test_source_head_switch_during_native_acl_denies(self):
        cmd, _ = self.command(lambda s: s.update(head="b" * 40))
        with self.assertRaisesRegex(MODULE.A1NativeHold, "A1_NATIVE_STOP_OR_HEAD_CHANGED_DURING_AUTH"):
            cmd._gate(None, "evolution.autonomy.read")

    def test_unchanged_native_owner_grant_allowed(self):
        cmd, _ = self.command()
        self.assertEqual(cmd._gate(None, "evolution.autonomy.read"), (2, "a" * 40))

    def test_false_acl_remains_denied(self):
        cmd, _ = self.command()
        cmd._authorize = lambda *_: False
        with self.assertRaisesRegex(MODULE.A1NativeHold, "A1_NATIVE_ACL_OR_CONSENT_HOLD"):
            cmd._gate(None, "evolution.autonomy.read")

    def test_boolean_epoch_not_accepted_as_integer(self):
        cmd, state = self.command()
        state["epoch"] = True
        with self.assertRaisesRegex(MODULE.A1NativeHold, "A1_NATIVE_EPOCH_OR_SOURCE_HOLD"):
            cmd._gate(None, "evolution.autonomy.read")

    def test_e06_staged_source_pin_is_current(self):
        stage = (ROOT / "coordination/e06/stage_native_stdio.py").read_text("utf-8")
        original = SOURCE.read_bytes()
        blob = hashlib.sha1(b"blob " + str(len(original)).encode("ascii") + b"\0" + original).hexdigest()
        pinned = "('src/nox_selfbuilder/a1_native_command.py', 'nox_selfbuilder/a1_native_command.py', '" + blob + "')"
        self.assertEqual(stage.count(pinned), 1)


if __name__ == "__main__":
    unittest.main()
