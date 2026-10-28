"""R17 source-only native auth/origin fail-closed regression; NOT EXE/E07."""
from dataclasses import replace
import secrets
import unittest
from admission import APPROVED_ROUTE_POLICY, BASE_COMMIT, BASE_TREE, Capability, Denied, Host50Admission


class AuthFrameR17(unittest.TestCase):
    def setUp(self):
        actions = [{"taskId": f"NIP01-{i:02}", "routeId": route,
                    "owner": owner, "risk": risk, "settings": []}
                   for i, (route, owner, risk) in enumerate(APPROVED_ROUTE_POLICY, 1)]
        self.host = Host50Admission(
            {"version": "NOX-INTEGRATION-PACK-01", "actions": actions},
            {"sourceBaseCommit": BASE_COMMIT, "routes": [
                {"taskId": a["taskId"], "routeId": a["routeId"],
                 "owner": a["owner"],
                 "sourceBinding": "owner2:helion.chat" if a["routeId"] == "helion.chat" else None}
                for a in actions]},
            signing_key=secrets.token_bytes(32),
            allowed_origins={"https://nox.invalid"}, active_tree=BASE_TREE,
            capabilities={"helion.chat": Capability("helion.chat", 2,
                "owner2:helion.chat", "a" * 64, BASE_TREE, True, True)})
        self.session = self.host.issue_session(tenant="t", principal="p", chat="c",
            origin="https://nox.invalid", scopes=("helion.chat",), sensitive=())
        self.request = {"intent": "nox.feature.request", "routeId": "helion.chat",
                        "taskId": "NIP01-01", "settings": {}}

    def _expect_denied(self, session, origin):
        with self.assertRaises(Denied):
            self.host.admit(session=session, actual_origin=origin, request=self.request)
        self.assertFalse(self.host.pending)

    def test_nonstring_native_origin_is_denied(self):
        self._expect_denied(self.session, [])

    def test_nonascii_signed_seal_is_denied(self):
        self._expect_denied(replace(self.session, seal="é" * 64), self.session.origin)

    def test_unpaired_surrogate_in_signed_claim_is_denied(self):
        self._expect_denied(replace(self.session, nonce="\ud800"), self.session.origin)


if __name__ == "__main__":
    unittest.main()
