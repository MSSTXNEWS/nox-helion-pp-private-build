"""P0 source regression: SSH banner/zero samples must never prove TTFT."""
import ast
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from nox_runpod.teacher_mesh.v104.one_model_thinking_benchmark import (
    REMOTE, native_timing_evidence,
)

GOOD = {'label':'default','state':'COMPLETED','stream_done':True,
        'ttft_ms':120.0,'content_chunks':3,'finish_reason':'stop',
        'usage_source':'HOLD_NO_STREAM_USAGE','completion_tokens':None,'reasoning_chunks':0}
SUMMARY = {'state':'READ_ONLY_MODEL_PROBES_COMPLETE','cases':2,
           'completed':2,'no_model_config_changed':True}

def rows(first=None, second=None, summary=None):
    a = GOOD if first is None else first
    b = dict(GOOD,label='no_thinking') if second is None else second
    s = SUMMARY if summary is None else summary
    return ['NATIVE_V104_CASE='+json.dumps(a),
            'NATIVE_V104_CASE='+json.dumps(b),
            'NATIVE_V104_RESULT='+json.dumps(s)]

class V104NativeTimingGate(unittest.TestCase):
    def test_two_complete_native_cases_accepted(self):
        self.assertTrue(native_timing_evidence(rows()))

    def test_busy_remote_not_counted_as_verified(self):
        self.assertFalse(native_timing_evidence([
            'NATIVE_V104_RESULT='+json.dumps({'state':'HOLD_CHAT_BUSY_NO_SYNTHETIC_PROBES'})]))

    def test_no_first_content_is_not_a_measurement(self):
        self.assertFalse(native_timing_evidence(rows(first=dict(GOOD,ttft_ms=None))))
        self.assertFalse(native_timing_evidence(rows(first=dict(GOOD,content_chunks=0))))

    def test_incomplete_or_unsupported_mode_fails_closed(self):
        self.assertFalse(native_timing_evidence(rows(second=dict(GOOD,label='no_thinking',state='HOLD_HTTP_400'))))
        self.assertFalse(native_timing_evidence(rows(summary=dict(SUMMARY,completed=1))))

    def test_duplicate_or_missing_case_fails_closed(self):
        self.assertFalse(native_timing_evidence(rows()+['NATIVE_V104_CASE='+json.dumps(GOOD)]))
        self.assertFalse(native_timing_evidence(rows()[:1]+rows()[2:]))

    def test_decode_tps_source_and_strict_evidence(self):
        self.assertIn("if include_usage:request['stream_options']={'include_usage':True}", REMOTE)
        verified = dict(GOOD,decode_tokens_per_sec=45.0,
                        usage_source='NATIVE_STREAM_USAGE',completion_tokens=40)
        self.assertTrue(native_timing_evidence(rows(first=verified)))
        self.assertFalse(native_timing_evidence(rows(first=dict(GOOD,decode_tokens_per_sec=45.0))))
        for rate in (-1, 0, '45', float('nan'), float('inf')):
            self.assertFalse(native_timing_evidence(rows(first=dict(verified,decode_tokens_per_sec=rate))))

    def test_fallback_is_only_allowed_without_fabricated_throughput(self):
        fallback = dict(GOOD,usage_negotiation='HTTP_400_FALLBACK_NO_USAGE',
                        usage_source='UNSUPPORTED_FALLBACK_NO_USAGE',completion_tokens=None,
                        decode_tokens_per_sec=None)
        self.assertTrue(native_timing_evidence(rows(first=fallback)))
        self.assertFalse(native_timing_evidence(rows(first=dict(fallback,decode_tokens_per_sec=35.0))))
        self.assertFalse(native_timing_evidence(rows(first=dict(fallback,usage_source='NATIVE_STREAM_USAGE'))))

    def test_requires_actual_finish_reason_and_no_reasoning_rate(self):
        self.assertFalse(native_timing_evidence(rows(first=dict(GOOD,finish_reason=None))))
        self.assertFalse(native_timing_evidence(rows(first=dict(GOOD,finish_reason='length'))))
        self.assertFalse(native_timing_evidence(rows(first=dict(GOOD,
            decode_tokens_per_sec=55.0,usage_source='NATIVE_STREAM_USAGE',
            completion_tokens=12,reasoning_chunks=1))))
        self.assertIn('HTTP_400_FALLBACK_NO_USAGE', REMOTE)
        self.assertIn('if include_usage:', REMOTE)


    def _execute_existing_remote_slot_guard(self, slots, stops=()):
        # Extract the actual native function from the shipped SSH payload,
        # rather than copy/paste a simulated gate into tests.
        remote = REMOTE.split("<<'PYREMOTE'\\n",1)[1].rsplit('\\nPYREMOTE',1)[0]
        tree = ast.parse(remote)
        funcs = [node for node in tree.body if isinstance(node,ast.FunctionDef)
                 and node.name == 'idle_slots']
        self.assertEqual(1,len(funcs))
        namespace = {'Path':Path,'STOP_PATHS':stops,'get':lambda path: slots}
        exec(compile(ast.Module(body=funcs,type_ignores=[]),
                     '<native-slot-guard>','exec'),namespace)
        return namespace['idle_slots']()

    def test_native_slot_gate_rejects_unknown_and_busy_and_conflicts(self):
        invalid = (None, [], {}, [{}], ['invalid'],
                   [{'is_processing':True}],
                   [{'processing':True}],
                   [{'is_processing':True,'processing':False}],
                   [{'is_processing':False,'processing':True}],
                   [{'processing':0}],
                   [{'is_processing':False},{}])
        for state in invalid:
            with self.subTest(slots=state):
                self.assertFalse(self._execute_existing_remote_slot_guard(state))
        self.assertTrue(self._execute_existing_remote_slot_guard(
            [{'is_processing':False}]))
        self.assertTrue(self._execute_existing_remote_slot_guard(
            [{'processing':False},{'is_processing':False,'processing':False}]))

    def test_native_stop_gates_every_synthetic_request(self):
        with TemporaryDirectory() as d:
            stop=Path(d)/'STOP'
            stop.write_text('1')
            self.assertFalse(self._execute_existing_remote_slot_guard(
                [{'is_processing':False}],stops=(str(stop),)))
        self.assertIn("if not idle_slots():return {'label':label",REMOTE)
        self.assertIn("if not idle_slots():\\n        results.append",REMOTE)
        self.assertIn("if not idle_slots():\\n            x={'label':label",REMOTE)

    def test_remote_source_compiles_without_connecting(self):
        remote = REMOTE.split("<<'PYREMOTE'\n",1)[1].rsplit('\nPYREMOTE',1)[0]
        compile(remote,'<read-only-v104-native>','exec')

if __name__ == '__main__':
    unittest.main()
