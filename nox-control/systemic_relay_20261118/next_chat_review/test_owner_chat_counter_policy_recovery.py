"""Source-only preflight of guarded stale-counter/policy successor; no host actions."""
import importlib.util
from pathlib import Path
from unittest.mock import patch
import json, unittest, hashlib

ROOT=Path(__file__).resolve().parent
SRC=ROOT/'package_counter_reconcile_policy_v1/owner_chat_counter_policy_entry.py'

def load():
    spec=importlib.util.spec_from_file_location('_nox_chat_counter_policy_preflight',SRC)
    value=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value

class CounterPolicyCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m=load()

    def test_exact_preservation_contract_and_source_pins(self):
        m=self.m
        self.assertEqual(set(m.TARGETS), {'slim','common.py','chat_proxy.py','chat_counter'})
        self.assertEqual(m.SPEC['before']['chat_counter'],
                         'a3a4bb542d6c95a2de769e427c393e4d1412d6d452b90ac07fe8c8b312b1f1cc')
        self.assertEqual(m.SPEC['stale_counter_reconciliation']['minimum_age_seconds'],3600)
        self.assertEqual(m.SPEC['stale_counter_reconciliation']['count'],4)
        self.assertNotIn('common.py',m.SPEC['guarded_sources'])
        self.assertNotIn('chat_proxy.py',m.SPEC['guarded_sources'])
        self.assertEqual(set(m.SPEC['before'])-set(m.TARGETS),{'ui'})
        self.assertEqual(m.SPEC['before']['ui'],m.SPEC['after_ui_sha256'])
        module=m.module('_counter_pure_source', m.COUNTER_PATCH_SOURCE.encode())
        self.assertEqual(set(module.SOURCE_PINS),{'common.py','chat_proxy.py'})
        self.assertIn('LOCK_EX',m.COUNTER_PATCH_SOURCE)
        self.assertIn('self._release()',m.COUNTER_PATCH_SOURCE)

    def test_stale_gate_allows_exact_stable_no_clients_only(self):
        m=self.m
        doc={'inflight':4,'last_start':1.0,'last_end':2.0,'last_ts':2.0}
        raw=json.dumps(doc,sort_keys=True).encode()
        identity=(1,2,3,4)
        expected='a3a4bb542d6c95a2de769e427c393e4d1412d6d452b90ac07fe8c8b312b1f1cc'
        # In tests the bytes are a controlled fixture, so pin the fixture hash
        # without changing the native installer's immutable expected pin.
        copy=dict(m.SPEC)
        copy['stale_counter_reconciliation']=dict(m.SPEC['stale_counter_reconciliation'],
                                                  expected_sha256=hashlib.sha256(raw).hexdigest())
        with patch.object(m,'read',return_value=(raw,identity)), \
             patch.object(m,'activity_path',return_value='/tmp/fake-counter'), \
             patch.object(m,'_zero_proxy_clients',return_value={'clients':0}) as zero, \
             patch.object(m.time,'time',return_value=7200.0), \
             patch.object(m.time,'sleep'):
            out=m.proxy_idle(copy)
        self.assertTrue(out['stale_reconcile'])
        self.assertEqual(out['inflight_before'],4)
        self.assertEqual(out['samples'],2)
        self.assertEqual(zero.call_count,2)

    def test_changed_counter_and_foreign_state_fail_closed(self):
        m=self.m
        doc={'inflight':5,'last_start':1.0,'last_end':2.0,'last_ts':2.0}
        raw=json.dumps(doc,sort_keys=True).encode()
        with patch.object(m,'read',return_value=(raw,(1,2,3,4))),\
             patch.object(m,'activity_path',return_value='/tmp/counter'),\
             patch.object(m.time,'time',return_value=7200.0):
            with self.assertRaisesRegex(Exception,'CHAT_COUNTER_NOT_RECOVERABLE'):
                m.proxy_idle(m.SPEC)

if __name__=="__main__":
    unittest.main()
