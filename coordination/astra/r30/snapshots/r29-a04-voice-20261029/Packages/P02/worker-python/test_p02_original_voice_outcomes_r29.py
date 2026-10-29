"""Original typed failures remain distinct in actual existing native HOLD frames."""
import json
import unittest
from p02_native_ingress import ProtocolHold
from p02_framed_worker import _encode_status
import test_p02_original_voice_port_r29 as fixture
from helion_voice.control import VoiceCancelled, VoiceTimeout, VoicePermissionDenied

class OriginalVoiceOutcomes(unittest.TestCase):
    setUp=fixture.OriginalVoiceContract.setUp
    call=fixture.OriginalVoiceContract.call
    speak=fixture.OriginalVoiceContract.speak

    def encoded_failure(self):
        with self.assertRaises(ProtocolHold) as caught:self.speak()
        wire=json.loads(_encode_status(self.ingress,'f'*32,str(caught.exception)))
        self.assertEqual(wire['status'],'HOLD')
        self.assertNotIn('PRIVATE',json.dumps(wire))
        self.assertIsNone(self.ingress._active_voice)
        return wire['errorCode']

    def test_original_timeouts_at_each_stage_remain_timeout(self):
        wav=self.fx.audio['a'*32]
        worker=fixture.adapters._run_worker.side_effect
        review=self.port.review
        for stage in ('asr','translate','sapi'):
            self.fx.audio['a'*32]=wav
            def timeout_worker(name,payload,session,timeout):
                if name==stage:raise VoiceTimeout('PRIVATE provider detail')
                return worker(name,payload,session,timeout)
            fixture.adapters._run_worker.side_effect=timeout_worker
            def timeout_review(scope,challenge):
                decision=review(scope,challenge)
                if stage=='sapi':
                    def fail(*args,**kwargs):raise VoiceTimeout('PRIVATE provider detail')
                    self.ingress.voice_session_from_native(self.session).run=fail
                return decision
            self.port.review=timeout_review
            with self.subTest(stage=stage):self.assertEqual(self.encoded_failure(),'NATIVE_VOICE_TIMEOUT')

    def test_original_permission_and_cancel_types_have_distinct_static_codes(self):
        wav=self.fx.audio['a'*32]
        for error,code in ((VoicePermissionDenied,'NATIVE_PERMISSION_DENIED'),(VoiceCancelled,'NATIVE_VOICE_STOPPED')):
            self.fx.audio['a'*32]=wav
            def fail(*args):raise error('PRIVATE provider detail')
            fixture.adapters._run_worker.side_effect=fail
            with self.subTest(error=error.__name__):self.assertEqual(self.encoded_failure(),code)
        self.assertEqual(self.spoken,[])

    def test_actual_stop_wins_over_late_original_timeout(self):
        observed=[]
        def fail(*args):
            observed.append(self.call('chat.stop',{}))
            raise VoiceTimeout('PRIVATE late timeout')
        fixture.adapters._run_worker.side_effect=fail
        self.assertEqual(self.encoded_failure(),'NATIVE_VOICE_STOPPED')
        self.assertTrue(observed[0]['voiceStopped'])
        self.assertEqual(self.spoken,[])

if __name__=='__main__':unittest.main()
