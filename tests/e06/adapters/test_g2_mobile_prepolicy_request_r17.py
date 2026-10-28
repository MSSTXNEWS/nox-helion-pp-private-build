"""E06 R17 source-only regressions for the REAL existing mobile bridge.
No listeners, user data, network fetches, SIP billing, Windows builds or extra host.
Requires source checkout; source-derived isolated reproduction separately verified.
"""
import pathlib
import sys
import unittest
ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "coordination" / "e06" / "adapters"))
from g2_space_mobile import PrivateMobileContract, G2Denied, G2Hold

class Ctx:
    def __init__(self, flags=None):
        self.flags=flags or {};self.calls=0;self.policies=0;self.advertise_calls=0;self.live=True
        self.payload={'want':['space.news']}
    def peer(self,session):
        self.calls+=1
        if self.flags.get('mutate_want') and self.calls==1:
            self.payload['want'][:]=['chat.model']
        if self.flags.get('revoke_second_peer') and self.calls==2: self.flags['bad_peer']=True
        proof={'identity':'native-user','verified_private_peer':not self.flags.get('bad_peer'),
          'trusted_origin':'https://private.example','observed_origin':'https://private.example',
          'expected_csrf':b'a'*32,'received_csrf':b'a'*32,
          'native_session_approved':True,'expires_at':200.0}
        if self.flags.get('bad_csrf'):proof['received_csrf']=b'z'*32
        if self.flags.get('nonascii_csrf'):
            proof['expected_csrf']='a'*32;proof['received_csrf']='é'*32
        return proof
    def policy(self,identity,**kw):self.policies+=1;return True
    def advertise(self,session):
        self.advertise_calls+=1
        if self.flags.get('revoke_after_final_advertise') and self.advertise_calls==2: self.live=False
        return {'space.news':{'enabled':True},'chat.model':{'enabled':True}}
    def contract(self):return PrivateMobileContract(self.policy,self.peer,self,lambda:100.,gateway_ready=lambda:self.live)

class Cases(unittest.TestCase):
    def test_mutated_payload_does_not_escalate(self):
        c=Ctx({'mutate_want':True}); self.assertEqual(c.contract().connect(None,c.payload)['allowed'],['space.news'])
    def test_bad_private_peer_denied_before_policy_side_effects(self):
        c=Ctx({'bad_peer':True})
        with self.assertRaises(G2Denied):c.contract().connect(None,c.payload)
        self.assertEqual(c.policies,0)
    def test_bad_csrf_denied_before_policy_side_effects(self):
        c=Ctx({'bad_csrf':True})
        with self.assertRaises(G2Denied):c.contract().connect(None,c.payload)
        self.assertEqual(c.policies,0)
    def test_nonascii_presented_csrf_fails_closed(self):
        c=Ctx({'nonascii_csrf':True})
        with self.assertRaises(G2Denied):c.contract().connect(None,c.payload)
        self.assertEqual(c.policies,0)
    def test_second_peer_revocation_does_not_touch_native_policy(self):
        c=Ctx({'revoke_second_peer':True})
        with self.assertRaises(G2Denied): c.contract().connect(None,c.payload)
        self.assertEqual(c.policies,1)
    def test_previous_lesson_final_gateway_revoke_stays_hold(self):
        c=Ctx({'revoke_after_final_advertise':True})
        with self.assertRaisesRegex(G2Hold,'REVOKED_AFTER_FINAL_ADVERTISEMENT'):
            c.contract().connect(None,c.payload)
        self.assertEqual(c.advertise_calls,2)
    def test_normal_private_path(self):
        c=Ctx(); self.assertEqual(c.contract().connect(None,c.payload)['allowed'],['space.news']);self.assertEqual(c.policies,2)
    def test_paid_call_still_denied(self):
        c=Ctx();self.assertRaises(G2Denied,c.contract().connect,None,{'want':['calls.dial']});self.assertEqual(c.policies,0)
    def test_gateway_not_ready_stays_hold(self):
        c=Ctx();c.live=False;self.assertRaises(G2Hold,c.contract().connect,None,c.payload)

if __name__=='__main__':unittest.main()
