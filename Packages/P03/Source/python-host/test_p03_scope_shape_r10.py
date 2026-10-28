"""NOX E03 W3-02 R10: malformed native scope is DENIED, never substring-approved.

Tests the REAL p03_onehost_port module next to this file.
No Ollama network, weights, installer or fake downloader.
"""
import unittest
from types import SimpleNamespace
from p03_onehost_port import P03OneHostPort, P03PortDenied


class NativeScopeShapeTests(unittest.TestCase):
    def setUp(self):
        self.port = object.__new__(P03OneHostPort)
        self.port.native_approve = lambda session, route, args: True

    @staticmethod
    def session(allowed, private_approved=frozenset()):
        return SimpleNamespace(tenant="tenant", principal="user", chat_id="chat",
                               allowed=allowed, private_approved=private_approved)

    def test_01_non_set_allowed_denied_without_type_error(self):
        for invalid in (None, 42, "models.pull", ["models.pull"], {"models.pull": True}):
            with self.subTest(value=repr(invalid)):
                with self.assertRaises(P03PortDenied):
                    self.port._ensure_native_scope(self.session(invalid), "models.pull", {})

    def test_02_allowed_set_must_contain_only_route_names(self):
        for invalid in (frozenset({"models.pull", 42}), {"models.pull", None}):
            with self.subTest(value=repr(invalid)):
                with self.assertRaises(P03PortDenied):
                    self.port._ensure_native_scope(self.session(invalid), "models.pull", {})

    def test_03_non_set_private_consent_never_authorizes_pull(self):
        for invalid in (None, 42, "models.pull", ["models.pull"], {"models.pull": True}):
            with self.subTest(value=repr(invalid)):
                with self.assertRaises(P03PortDenied):
                    self.port._ensure_native_scope(self.session(frozenset({"models.pull"}), invalid),
                                                   "models.pull", {})

    def test_04_private_consent_set_elements_must_be_strings(self):
        with self.assertRaises(P03PortDenied):
            self.port._ensure_native_scope(self.session(frozenset({"models.pull"}),
                                                        frozenset({"models.pull", 42})), "models.pull", {})

    def test_05_approved_set_scope_still_works(self):
        self.port._ensure_native_scope(self.session(frozenset({"models.pull"}),
                                                   frozenset({"models.pull"})), "models.pull", {})
        self.port._ensure_native_scope(self.session(frozenset({"models.catalog"})),
                                       "models.catalog", {})

    def test_06_read_only_never_uses_private_approval(self):
        self.port.native_approve = None
        self.port._ensure_native_scope(self.session(frozenset({"models.catalog"}), None),
                                       "models.catalog", {})

    def test_07_no_out_of_band_native_approval_fails(self):
        self.port.native_approve = lambda *_args: False
        with self.assertRaises(P03PortDenied):
            self.port._ensure_native_scope(self.session(frozenset({"models.pull"}),
                                                        frozenset({"models.pull"})), "models.pull", {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
