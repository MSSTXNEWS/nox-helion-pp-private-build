"""Owner-only A1 boot: native consent races and concurrent IPC admission.
This is a Python source regression, NOT a Windows GUI/IPC/E07 receipt.
"""
import sys
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from nox_selfbuilder.a1_native_command import A1NativeCommand, A1NativeHold

class Session:
    tenant, principal, chat_id = "local", "owner", "original"
    def validate(self): return None

class Builder:
    def __init__(self): self.calls = []
    def bind_native_megapat_a(self, *a, **k):
        self.calls.append("bind")
        return {"state": "PORTS_BOUND_AWAITING_NATIVE_STARTUP"}
    def native_a_boot(self, *a, **k):
        self.calls.append("boot")
        return {"schema": "NOX-A-NATIVE-BOOT-v1", "state": "READY_FOR_EXISTING_IDLE_TICK"}
    def native_a_tick(self, *a, **k): raise AssertionError("tick not involved")

class NativeConsentEpoch(unittest.TestCase):
    def setUp(self):
        self.s = Session()
        self.owner = {"epoch": 2, "head": "a"*40, "stopped": False}
        self.factory_calls = 0
        self.builder = Builder()
        self.consent = lambda *a: True
        def factory(session):
            self.factory_calls += 1
            return {"initiative_bridge": object(), "firstboot": object()}
        self.command = A1NativeCommand(
            builder=self.builder, components=factory,
            consent=lambda *a: self.consent(*a),
            authorize=lambda *a: True,
            stopped=lambda: self.owner["stopped"],
            stop_epoch=lambda: self.owner["epoch"],
            source_head=lambda: self.owner["head"])
    def boot(self):
        return self.command.invoke(self.s, {"action": "selfbuilder.a1.boot"},
                                   now=datetime(2026, 11, 2, tzinfo=timezone.utc))
    def test_normal_single_owner_boot(self):
        self.assertEqual(self.boot()["state"], "READY_FOR_EXISTING_IDLE_TICK")
        self.assertEqual(self.builder.calls, ["bind", "boot"])
        self.assertEqual(self.factory_calls, 1)
    def test_wpf_prompt_precedes_acl_confirmation(self):
        # Some real owners update the ACL consent bit only after dialog YES.
        approved = {"value": False}
        self.command._authorize = lambda *a: approved["value"]
        def approve(*a):
            approved["value"] = True
            return True
        self.consent = approve
        self.assertEqual(self.boot()["state"], "READY_FOR_EXISTING_IDLE_TICK")
        self.assertEqual(self.builder.calls, ["bind", "boot"])
    def test_stop_reset_during_consent_never_regrants_old_dialog(self):
        def change(*a):
            self.owner["stopped"] = True
            self.owner["epoch"] += 1
            self.owner["stopped"] = False
            return True
        self.consent = change
        with self.assertRaisesRegex(A1NativeHold, "CONSENT_EPOCH_OR_HEAD_CHANGED"): self.boot()
        self.assertEqual(self.factory_calls, 0)
        self.assertFalse(self.command._bound)
    def test_head_switch_during_consent_denied(self):
        def change(*a):
            self.owner["head"] = "b"*40
            return True
        self.consent = change
        with self.assertRaisesRegex(A1NativeHold, "CONSENT_EPOCH_OR_HEAD_CHANGED"): self.boot()
        self.assertEqual(self.factory_calls, 0)
    def test_owner_scope_switch_during_consent_denied(self):
        def change(*a):
            self.s.principal = "different"
            return True
        self.consent = change
        # Capture the authenticated scope before the WPF dialog changes it.
        with self.assertRaisesRegex(A1NativeHold, "CONSENT_OWNER_CHANGED"): self.boot()
        self.assertEqual(self.factory_calls, 0)
    def test_parallel_boot_cannot_duplicate_native_factory(self):
        entered, release = threading.Event(), threading.Event()
        done, errors = [], []
        def block(*a):
            entered.set()
            if not release.wait(4): raise RuntimeError("test gate")
            return True
        self.consent = block
        def worker():
            try: done.append(self.boot())
            except BaseException as exc: errors.append(exc)
        th = threading.Thread(target=worker, daemon=True)
        th.start()
        try:
            self.assertTrue(entered.wait(3))
            with self.assertRaisesRegex(A1NativeHold, "BOOT_IN_PROGRESS"): self.boot()
        finally:
            release.set()
            th.join(5)
        self.assertFalse(th.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(len(done), 1)
        self.assertEqual(self.builder.calls, ["bind", "boot"])
        self.assertEqual(self.factory_calls, 1)
    def test_denied_dialog_does_not_permanently_lock_next_boot(self):
        self.consent = lambda *a: False
        with self.assertRaisesRegex(A1NativeHold, "FRESH_NATIVE_WPF_CONSENT_REQUIRED"): self.boot()
        self.assertEqual(self.factory_calls, 0)
        self.consent = lambda *a: True
        self.assertEqual(self.boot()["state"], "READY_FOR_EXISTING_IDLE_TICK")

if __name__ == "__main__": unittest.main()
