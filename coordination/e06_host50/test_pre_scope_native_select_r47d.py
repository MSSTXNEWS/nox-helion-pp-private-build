"""R47 Host50: sensitive permission must precede native option verifier calls.
Source-only component regression; not real Windows WPF/native or E07 proof.
"""
import secrets
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from admission import (APPROVED_ROUTE_POLICY, BASE_COMMIT, BASE_TREE,
                       Capability, Denied, Host50Admission)


class NativeOptionPreScopeTests(unittest.TestCase):
    def make_host(self):
        actions = [
            {"taskId": f"NIP01-{i:02d}", "routeId": route,
             "owner": owner, "risk": risk, "settings": []}
            for i, (route, owner, risk) in enumerate(APPROVED_ROUTE_POLICY, 1)
        ]
        route = "models.pull"
        task = "NIP01-13"
        row = next(action for action in actions if action["routeId"] == route)
        self.assertEqual(row["taskId"], task)
        self.assertEqual(row["risk"], "sensitive")
        row["settings"] = [{
            "key": "model", "kind": "select", "source": "host.models.installed"
        }]
        binding = "owner3:models.pull"
        bindings = {"sourceBaseCommit": BASE_COMMIT, "routes": [
            {"taskId": action["taskId"], "routeId": action["routeId"],
             "owner": action["owner"],
             "sourceBinding": binding if action["routeId"] == route else None}
            for action in actions
        ]}
        caps = {route: Capability(route, 3, binding, "a" * 64,
                                  BASE_TREE, True, True)}
        host = Host50Admission(
            {"version": "NOX-INTEGRATION-PACK-01", "actions": actions},
            bindings, signing_key=secrets.token_bytes(32),
            allowed_origins={"https://nox.invalid"}, active_tree=BASE_TREE,
            capabilities=caps)
        request = {"intent": "nox.feature.request", "routeId": route,
                   "taskId": task, "settings": {"model": "installed-model"}}
        return host, request

    def session(self, host, *, sensitive):
        return host.issue_session(
            tenant="tenant", principal="person", chat="chat",
            origin="https://nox.invalid", scopes=("models.pull",),
            sensitive=("models.pull",) if sensitive else ())

    def test_denied_private_permission_never_probes_native_model(self):
        host, request = self.make_host()
        session = self.session(host, sensitive=False)
        calls = []
        def verifier(*args):
            calls.append(args)
            return True
        with self.assertRaisesRegex(Denied, "SENSITIVE_NATIVE_PERMISSION_REQUIRED"):
            host.admit(session=session, actual_origin=session.origin,
                       request=request, native_option_verifier=verifier)
        self.assertEqual(calls, [], "Denied native scope invoked owner callback")

    def test_denied_permission_precedes_missing_verifier(self):
        host, request = self.make_host()
        session = self.session(host, sensitive=False)
        with self.assertRaisesRegex(Denied, "SENSITIVE_NATIVE_PERMISSION_REQUIRED"):
            host.admit(session=session, actual_origin=session.origin,
                       request=request)

    def test_approved_native_scope_still_checks_option_twice(self):
        host, request = self.make_host()
        session = self.session(host, sensitive=True)
        calls = []
        def verifier(*args):
            calls.append(args)
            return True
        result = host.admit(session=session, actual_origin=session.origin,
                            request=request, native_option_verifier=verifier)
        self.assertEqual(result["state"], "ADMITTED_NOT_EXECUTED")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][1:], ("models.pull", "model",
                         "host.models.installed", "installed-model"))


if __name__ == "__main__":
    unittest.main()
