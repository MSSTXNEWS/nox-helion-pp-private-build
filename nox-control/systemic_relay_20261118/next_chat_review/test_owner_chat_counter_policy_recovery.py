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

    def test_idle_path_reads_mutable_preimage_pins_not_static_guards(self):
        import ast
        from unittest.mock import patch
        m = self.m
        common = ("from pathlib import Path\nROOT=Path('/root/nox')\n"
                  "STATUS_DIR=ROOT/'status'\nCHAT_STATE=STATUS_DIR/'chat_state.json'\n"
                  "def mark_chat(busy):\n    return busy\n").encode()
        proxy = ("class _ChatActivityStream:\n    def aclose(self):\n"
                 "        return None\n").encode()
        def symbol_pin(raw, symbol):
            source = raw.decode()
            node = next(row for row in ast.parse(source).body
                        if isinstance(row, (ast.FunctionDef, ast.ClassDef)) and row.name == symbol)
            return m.sha((ast.get_source_segment(source, node) + '\n').encode())
        config = dict(m.SPEC)
        config['idle_gate'] = dict(config['idle_gate'],
                                   symbols={'common.py:mark_chat': symbol_pin(common, 'mark_chat'),
                                            'chat_proxy.py:_ChatActivityStream': symbol_pin(proxy, '_ChatActivityStream')})
        expected = {
            'common.py': config['before']['common.py'],
            'chat_proxy.py': config['before']['chat_proxy.py'],
        }
        used = []
        def read(path, pin=None, **kwargs):
            name = Path(path).name
            self.assertIn(name, expected)
            self.assertEqual(pin, expected[name])
            used.append(name)
            return (common if name == 'common.py' else proxy), (1, 2, 3)
        with patch.object(m, 'read', side_effect=read):
            self.assertEqual(str(m.activity_path(config)), '/root/nox/status/chat_state.json')
        self.assertEqual(used, ['common.py', 'common.py', 'chat_proxy.py'])

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
