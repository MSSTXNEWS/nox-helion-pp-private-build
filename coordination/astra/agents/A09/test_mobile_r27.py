"""Actual A09/P02 modules with deterministic native host boundary fixtures."""
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[4]
OWNER = Path(os.environ.get('NOX_G2_OWNER_FIXTURE_ROOT', ROOT / 'Packages'))
sys.path.insert(0, str(OWNER / 'P02' if (OWNER / 'P02' / 'p02_capabilities.py').exists()
                       else ROOT / 'Packages/P02/worker-python'))
sys.path.insert(0, str(ROOT / 'coordination/e06/adapters'))
from p02_capabilities import Identity, authorize_private_mobile
from g2_space_mobile import PrivateMobileContract, G2Denied, G2Hold


class MobileBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.calls = 0
        self.after_advertise = lambda count: None
        self.proof = dict(identity=Identity('tenant', 'user', 'HELION', 'Persona', 'session'),
                          verified_private_peer=True, trusted_origin='https://nox.example',
                          observed_origin='https://nox.example', expected_csrf=b'x' * 32,
                          received_csrf=b'x' * 32, native_session_approved=True, expires_at=140.0)
        owner = self
        class Host:
            def advertise(self, session):
                owner.calls += 1
                owner.after_advertise(owner.calls)
                return {'chat.history': {'enabled': True}, 'space.news': {'enabled': True}}
        self.policy_calls = 0
        def policy(*args, **kwargs):
            self.policy_calls += 1
            return authorize_private_mobile(*args, **kwargs)
        self.contract = PrivateMobileContract(policy, lambda session: dict(self.proof), Host(),
                                              lambda: self.now, lambda: True)
        self.payload = {'want': ['chat.history']}

    def test_canonical_p02_identity_is_accepted_without_coercion(self):
        self.assertEqual(self.contract.connect(object(), self.payload)['allowed'], ['chat.history'])

    def test_invalid_native_identity_field_fails_closed(self):
        for field in ('tenant', 'principal', 'core_id', 'persona_id', 'session_id'):
            with self.subTest(field=field):
                values = dict(tenant='tenant', principal='user', core_id='HELION',
                              persona_id='Persona', session_id='session')
                values[field] = True
                self.proof['identity'] = Identity(**values)
                with self.assertRaises(G2Denied):
                    self.contract.connect(object(), self.payload)

    def test_identity_duck_type_is_not_native_identity(self):
        class FakeIdentity:
            tenant = principal = core_id = persona_id = session_id = 'x'
        self.proof['identity'] = FakeIdentity()
        with self.assertRaises(G2Denied):
            self.contract.connect(object(), self.payload)

    def test_caller_request_mutation_does_not_expand_allowed_capabilities(self):
        self.proof['identity'] = 'legacy-native-session'
        self.contract.policy = lambda *args, **kwargs: True
        self.after_advertise = lambda count: self.payload['want'].append('space.news') if count == 1 else None
        self.assertEqual(self.contract.connect(object(), self.payload)['allowed'], ['chat.history'])

    def test_expiry_during_final_advertisement_denies(self):
        self.proof['identity'] = 'legacy-native-session'
        self.contract.policy = lambda *args, **kwargs: True
        def expire(count):
            if count == 2:
                self.now = 140.0
        self.after_advertise = expire
        with self.assertRaises(G2Denied):
            self.contract.connect(object(), self.payload)

    def test_revocation_during_final_advertisement_denies(self):
        self.proof['identity'] = 'legacy-native-session'
        self.contract.policy = lambda *args, **kwargs: True
        def revoke(count):
            if count == 2:
                self.proof['native_session_approved'] = False
        self.after_advertise = revoke
        with self.assertRaises(G2Denied):
            self.contract.connect(object(), self.payload)

    def test_csrf_rotation_during_final_advertisement_denies(self):
        self.proof['identity'] = 'legacy-native-session'
        self.contract.policy = lambda *args, **kwargs: True
        def rotate(count):
            if count == 2:
                self.proof['expected_csrf'] = self.proof['received_csrf'] = b'y' * 32
        self.after_advertise = rotate
        with self.assertRaises(G2Denied):
            self.contract.connect(object(), self.payload)

    def test_invalid_clock_never_calls_owner_policy(self):
        self.now = True
        with self.assertRaises(G2Hold):
            self.contract.connect(object(), self.payload)
        self.assertEqual(self.policy_calls, 0)

    def test_oversized_csrf_never_calls_owner_policy(self):
        self.proof['received_csrf'] = b'x' * 10000
        with self.assertRaises(G2Denied):
            self.contract.connect(object(), self.payload)
        self.assertEqual(self.policy_calls, 0)

    def test_legacy_native_string_policy_contract_preserved(self):
        self.proof['identity'] = 'legacy-native-session'
        self.contract.policy = lambda *args, **kwargs: True
        self.assertEqual(self.contract.connect(object(), self.payload)['allowed'], ['chat.history'])

if __name__ == '__main__':
    unittest.main()
