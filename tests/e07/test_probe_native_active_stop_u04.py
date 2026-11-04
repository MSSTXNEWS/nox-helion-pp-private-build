"""Source-only active-STOP verifier tests; never count as physical NOX proof."""
import importlib.util
from pathlib import Path
import unittest

SRC = Path(__file__).resolve().parents[2] / 'coordination/e07/probe_native_active_stop.py'
spec = importlib.util.spec_from_file_location('nox_stop_probe', SRC)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
CHAT, STOP = 'a'*32, 'b'*32

def delta(text='real token'):
    return {'requestId': CHAT, 'status':'EVENT', 'event': {
        'route':'helion.chat','state':'streaming','delta':text}}

def stopped():
    return {'requestId':STOP,'status':'OK','result':{'stopRequested':True}}

def interrupted():
    return {'requestId':CHAT,'status':'HOLD','errorCode':'NATIVE_CHAT_STOP'}

class NativeActiveStopGate(unittest.TestCase):
    def test_valid_active_native_stop_receipt(self):
        self.assertEqual(mod.validate_stop_transcript([delta()], [stopped(), interrupted()], CHAT, STOP)['native_stop_ack'], 'PASS')
    def test_idle_stop_is_not_active_stop(self):
        with self.assertRaises(mod.GateHold): mod.validate_stop_transcript([], [stopped()], CHAT, STOP)
    def test_empty_delta_not_a_token(self):
        with self.assertRaises(mod.GateHold): mod.validate_stop_transcript([delta('  ')], [stopped(), interrupted()], CHAT, STOP)
    def test_completed_chat_before_stop_rejected(self):
        with self.assertRaises(mod.GateHold): mod.validate_stop_transcript([delta(), {'requestId':CHAT,'status':'OK'}], [stopped(),interrupted()], CHAT, STOP)
    def test_normal_chat_completion_after_stop_rejected(self):
        with self.assertRaises(mod.GateHold): mod.validate_stop_transcript([delta()], [stopped(), {'requestId':CHAT,'status':'OK'}], CHAT, STOP)
    def test_provider_abort_not_native_stop(self):
        with self.assertRaises(mod.GateHold): mod.validate_stop_transcript([delta()], [interrupted()], CHAT, STOP)
    def test_generic_chat_error_not_verified_interruption(self):
        with self.assertRaises(mod.GateHold): mod.validate_stop_transcript([delta()], [stopped(), {'requestId':CHAT,'status':'HOLD','errorCode':'NATIVE_PROVIDER_HOLD'}], CHAT, STOP)
    def test_duplicate_ack_rejected(self):
        with self.assertRaises(mod.GateHold): mod.validate_stop_transcript([delta()], [stopped(),stopped(), interrupted()], CHAT, STOP)

if __name__ == '__main__': unittest.main()
