"""Fail-closed native STOP state for existing OneHost SelfBuilder.

UNKNOWN is not authorization to resume or generate; no workers, weights or
files are changed by these pure owner-scope regressions.
"""
import threading
import unittest
from types import SimpleNamespace
from src.nox_selfbuilder.onehost_builder import OneHostSelfBuilder

class NativeStopFailClosed(unittest.TestCase):
    def service(self, native_state):
        owner=OneHostSelfBuilder.__new__(OneHostSelfBuilder)
        owner._stop=threading.Event()
        owner.native_stop=lambda: native_state
        owner.queue=SimpleNamespace(is_busy=lambda:False)
        owner.authorize=lambda *_args: True
        return owner

    def test_none_is_hold(self):
        owner=self.service(None)
        self.assertTrue(owner._stopped())
        owner._stop.set()
        with self.assertRaisesRegex(PermissionError,"FRESH_IDLE_NATIVE_CONSENT_REQUIRED"):
            owner.reset_for_native_consent("owner")
        self.assertTrue(owner._stop.is_set())

    def test_false_is_only_permitted_native_state(self):
        owner=self.service(False)
        self.assertFalse(owner._stopped())
        owner._stop.set()
        owner.reset_for_native_consent("owner")
        self.assertFalse(owner._stopped())

    def test_nonboolean_values_do_not_grant(self):
        for value in ("",0,1,True,{},[]):
            with self.subTest(value=value):
                owner=self.service(value)
                self.assertTrue(owner._stopped())
                owner._stop.set()
                with self.assertRaises(PermissionError):
                    owner.reset_for_native_consent("owner")
                self.assertTrue(owner._stop.is_set())

if __name__=="__main__":
    unittest.main()
