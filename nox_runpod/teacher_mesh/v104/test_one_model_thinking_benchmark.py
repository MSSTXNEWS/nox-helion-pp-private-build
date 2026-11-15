"""P0 source regression: SSH banner/zero samples must never prove TTFT."""
import json
import unittest
from nox_runpod.teacher_mesh.v104.one_model_thinking_benchmark import (
    REMOTE, native_timing_evidence,
)

GOOD = {'label':'default','state':'COMPLETED','stream_done':True,
        'ttft_ms':120.0,'content_chunks':3}
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

    def test_remote_source_compiles_without_connecting(self):
        remote = REMOTE.split("<<'PYREMOTE'\n",1)[1].rsplit('\nPYREMOTE',1)[0]
        compile(remote,'<read-only-v104-native>','exec')

if __name__ == '__main__':
    unittest.main()
