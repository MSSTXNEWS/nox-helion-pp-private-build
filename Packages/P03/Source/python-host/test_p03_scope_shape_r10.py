"""NOX E03 W3-02 R10: malformed native scope is DENIED, never substring-approved.

Tests the REAL p03_onehost_port module next to this file.
No Ollama network, weights, installer or fake downloader.
"""
import unittest
from types import SimpleNamespace
from p03_onehost_port import P03OneHostPort, P03PortDenied, P03PortHold


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



    def test_r14_01_pull_callback_exception_holds(self):
        def broken(*_args):
            raise RuntimeError("private native callback diagnostic")
        self.port.native_approve = broken
        with self.assertRaises(P03PortHold) as caught:
            self.port._ensure_native_scope(
                self.session(frozenset({"models.pull"}), frozenset({"models.pull"})),
                "models.pull", {})
        self.assertEqual(str(caught.exception), "Native consent provider unavailable")

    def test_r14_02_stop_requires_native_scope_not_download_consent(self):
        def broken(*_args):
            raise ValueError("private device failure")
        self.port.native_approve = broken
        # STOP/cancel is intentionally not a sensitive download route. Existing
        # authenticated scope must remain able to cancel even if the
        # *download-consent* callback is broken or permission was revoked.
        self.port._ensure_native_scope(
            self.session(frozenset({"models.cancel"})),
            "models.cancel", {})
        with self.assertRaises(P03PortDenied):
            self.port._ensure_native_scope(
                self.session(frozenset()), "models.cancel", {})

    def test_r14_03_explicit_native_denial_remains_denied(self):
        def explicit_denial(*_args):
            raise P03PortDenied("Fresh permission denied")
        self.port.native_approve = explicit_denial
        with self.assertRaises(P03PortDenied):
            self.port._ensure_native_scope(
                self.session(frozenset({"models.pull"}), frozenset({"models.pull"})),
                "models.pull", {})

    def test_r14_04_truthy_nonboolean_does_not_approve(self):
        self.port.native_approve = lambda *_args: 1
        with self.assertRaises(P03PortDenied):
            self.port._ensure_native_scope(
                self.session(frozenset({"models.pull"}), frozenset({"models.pull"})),
                "models.pull", {})


class NativeOwnerRouteMapR11Tests(unittest.TestCase):
    """P03 must HOLD malformed one-host owner-map rows before any bind."""
    def setUp(self):
        self.port = object.__new__(P03OneHostPort)
        self.port.backend = None
        self.port.native_approve = None

    @staticmethod
    def host():
        routes = {r: {"owner": 3} for r in ("models.catalog", "models.licenses", "models.installed", "models.digest")}
        ports = {}
        host = SimpleNamespace(routes=routes, ports=ports)
        host.bind = lambda route, port: ports.__setitem__(route, port)
        return host

    def test_r11_01_bad_owner_row_types_fail_closed_without_partial_registration(self):
        for invalid in (None, 42, [], ["owner"], "owner", True):
            with self.subTest(row=repr(invalid)):
                host = self.host()
                host.routes["models.installed"] = invalid
                with self.assertRaises(P03PortHold):
                    self.port.register(host, tuple, receipt="LOCAL_FIXTURE_NOT_SOURCELOCK")
                self.assertEqual(host.ports, {})

    def test_r11_02_wrong_or_missing_owner_holds_without_bind(self):
        for invalid in ({"owner": 2}, {"owner": "3"}, {}):
            with self.subTest(row=invalid):
                host = self.host()
                host.routes["models.digest"] = invalid
                with self.assertRaises(P03PortHold):
                    self.port.register(host, tuple, receipt="LOCAL_FIXTURE_NOT_SOURCELOCK")
                self.assertEqual(host.ports, {})

    def test_r11_03_existing_foreign_port_remains_untouched(self):
        host = self.host()
        foreign = object()
        host.ports["models.catalog"] = foreign
        with self.assertRaises(P03PortHold):
            self.port.register(host, tuple, receipt="LOCAL_FIXTURE_NOT_SOURCELOCK")
        self.assertIs(host.ports["models.catalog"], foreign)
        self.assertEqual(len(host.ports), 1)

    def test_r11_04_valid_owner_rows_still_register_four_read_only_routes(self):
        host = self.host()
        registered = self.port.register(host, tuple, receipt="LOCAL_FIXTURE_NOT_SOURCELOCK")
        self.assertEqual(registered, frozenset(host.routes))
        self.assertEqual(set(host.ports), set(host.routes))


    def test_r12_01_exact_integer_owner_prevents_numeric_alias(self):
        # Python numeric equality makes 3.0 and 3+0j equal to 3.
        # P02 ingress requires type(owner) is int; P03 must agree.
        for fake_owner in (3.0, 3 + 0j):
            with self.subTest(owner=repr(fake_owner)):
                host = self.host()
                host.routes["models.installed"] = {"owner": fake_owner}
                with self.assertRaises(P03PortHold):
                    self.port.register(host, tuple, receipt="LOCAL_FIXTURE_NOT_SOURCELOCK")
                self.assertEqual(host.ports, {})

    def test_r12_02_legacy_bind_same_exact_owner_gate(self):
        for fake_owner in (3.0, 3 + 0j, None):
            with self.subTest(owner=repr(fake_owner)):
                host = self.host()
                host.routes["models.catalog"] = {"owner": fake_owner}
                with self.assertRaises(P03PortHold):
                    self.port._bind(host, tuple, "models.catalog",
                                    self.port.catalog, lambda: True, "fixture")
                self.assertEqual(host.ports, {})

    def test_r12_03_existing_valid_owner_int_still_binds(self):
        host = self.host()
        class NativeBound:
            def __init__(self, callback, available, receipt, owner):
                self.owner = owner
        self.port._bind(host, NativeBound, "models.catalog",
                        self.port.catalog, lambda: True, "fixture")
        self.assertEqual(set(host.ports), {"models.catalog"})
        self.assertEqual(host.ports["models.catalog"].owner, 3)


class OwnerBackendExceptionR15Tests(unittest.TestCase):
    """Actual source module; owner callback failure must HOLD, not ACK."""
    def setUp(self):
        self.port = object.__new__(P03OneHostPort)
        self.port.native_approve = lambda *_: True
    @staticmethod
    def session(route):
        return SimpleNamespace(tenant="tenant", principal="user", chat_id="chat",
                               allowed=frozenset({route}), private_approved=frozenset({route}))
    def run_route(self, route, cb, available=lambda: True):
        names = {"models.cancel": "cancel", "models.retry": "retry",
                 "models.pull": "pull", "models.gguf.import": "import_gguf"}
        owner = SimpleNamespace(available=available)
        setattr(owner, names[route], cb)
        self.port.backend = owner
        return self.port.execute_backend(self.session(route), route, {})
    def test_r15_cancel_exception_holds(self):
        def broken(*_): raise RuntimeError("private STOP diagnostic")
        with self.assertRaisesRegex(P03PortHold, "Owner3 backend operation unavailable"):
            self.run_route("models.cancel", broken)
    def test_r15_retry_exception_holds(self):
        def broken(*_): raise TypeError("private retry diagnostic")
        with self.assertRaises(P03PortHold):
            self.run_route("models.retry", broken)
    def test_r15_pull_exception_holds(self):
        def broken(*_): raise ValueError("private pull diagnostic")
        with self.assertRaises(P03PortHold):
            self.run_route("models.pull", broken)
    def test_r15_gguf_exception_holds(self):
        def broken(*_): raise OSError("private GGUF diagnostic")
        with self.assertRaises(P03PortHold):
            self.run_route("models.gguf.import", broken)
    def test_r15_owner_attribute_exception_holds(self):
        class BadOwner:
            def __getattribute__(self, name):
                if name == "available": raise RuntimeError("private owner diagnostic")
                return object.__getattribute__(self, name)
            def cancel(self, *_): return True
        self.port.backend = BadOwner()
        with self.assertRaisesRegex(P03PortHold, "Owner3 backend contract unavailable"):
            self.port.execute_backend(self.session("models.cancel"), "models.cancel", {})
    def test_r15_explicit_deny_preserved(self):
        def denied(*_): raise P03PortDenied("DENIED")
        with self.assertRaises(P03PortDenied):
            self.run_route("models.retry", denied)
    def test_r15_explicit_hold_preserved(self):
        def hold(*_): raise P03PortHold("NATIVE_HOLD")
        with self.assertRaisesRegex(P03PortHold, "NATIVE_HOLD"):
            self.run_route("models.cancel", hold)
    def test_r15_owner_success_still_passes(self):
        self.assertEqual(self.run_route("models.cancel", lambda *_: {"ok": True}),
                         {"ok": True})
    def test_r15_health_refusal_never_invokes_worker(self):
        called = []
        with self.assertRaises(P03PortHold):
            self.run_route("models.pull", lambda *_: called.append(True), available=lambda: False)
        self.assertEqual(called, [])
    def test_r15_previous_r14_native_callback_lesson_applies(self):
        called = []
        self.port.backend = SimpleNamespace(available=lambda: True, pull=lambda *_: called.append(True))
        def broken(*_): raise RuntimeError("private consent diagnostic")
        self.port.native_approve = broken
        # A broken native callback still blocks *sensitive* downloads before
        # reaching the owner backend; STOP does not require download consent.
        with self.assertRaisesRegex(P03PortHold, "Native consent provider unavailable"):
            self.port.execute_backend(self.session("models.pull"), "models.pull", {})
        self.assertEqual(called, [])

if __name__ == "__main__":
    unittest.main(verbosity=2)
