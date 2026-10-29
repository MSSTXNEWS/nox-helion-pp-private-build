"""Real original service/ASR/SAPI contracts; worker and OS boundary fixtures only."""
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
import test_p02_owner_route_ports as fixture
from test_p02_loader_existing_pack_r29 import host, CATALOG
# Hash-verifies original ZIP and imports its real modules, without extracting.
import test_p02_native_voice_lifecycle_r29 as original_fixture
from helion_voice import adapters
from helion_voice.audio import encode_pcm_wav
from helion_voice.service import VoiceService
from p02_native_ingress import NativeIngress, ProtocolHold
from p02_owner_route_ports import register_with_existing_pack01
from p02_original_voice_port import OriginalVoicePort, NativePreviewDecision
from p02_runtime import OllamaClient

class OriginalVoiceContract(unittest.TestCase):
    def setUp(self):
        self.fx=fixture.RouteTests();self.fx.setUp();self.addCleanup(self.fx.tearDown)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        model=pathlib.Path(self.temp.name)/'whisper';model.mkdir()
        (model/'model.bin').write_bytes(b'fixture');(model/'config.json').write_text('{}')
        asr=adapters.LocalWhisperASR(model)
        asr.diagnose=lambda:{'state':'CONFIGURED_NOT_PHYSICALLY_TESTED'}
        self.service=VoiceService(asr,adapters.LocalOllamaTranslator('fixture-local'),adapters.WindowsSapiTTS())
        self.dispatcher=host.NoxPackHost(CATALOG)
        self.session=host.NativeSession('tenant','alice','chat',frozenset(self.dispatcher.routes),frozenset(self.dispatcher.routes))
        self.scope=lambda session:self.fx.scope
        self.ingress=NativeIngress(self.dispatcher,lambda:self.session,expected_run_id='original-port',enable_voice_stop=True)
        self.client=OllamaClient();self.client.models=lambda:['fixture-local']
        host.ExistingP02Adapter(self.client,self.fx.store).register(self.dispatcher,receipt='TEST')
        self.reviewed=[];self.spoken=[];self.workers=[]
        def worker(name,payload,session,timeout):
            self.workers.append(name)
            if name=='asr':return {'text':'Привет','language':payload['lang'],'model_id':'local-whisper:whisper','device_used':'cpu'}
            return {'text':'Hola','model_id':'fixture-local','transport':'127.0.0.1'}
        self.addCleanup(patch.stopall)
        patch('helion_voice.adapters._run_worker',side_effect=worker).start()
        patch('helion_voice.adapters.platform.system',return_value='Windows').start()
        def reviewed(scope, challenge):
            self.reviewed.append(challenge)
            original=self.ingress.voice_session_from_native(self.session)
            original.run=lambda argv,data,**kw:self.spoken.append((argv,data)) or b''
            return NativePreviewDecision(challenge['request_id'],challenge['text_sha256'],True)
        self.port=OriginalVoicePort(self.fx.ports,self.service,self.ingress,self.scope,
            use_local_model=True,native_model_authorize=lambda scope,model:True,native_review=reviewed)
        register_with_existing_pack01(self.dispatcher,host.BoundPort,self.scope,self.fx.ports,
            receipt='TEST',original_voice_port=self.port)
        self.fx.audio['a'*32]=encode_pcm_wav(b'\x01\x01'*1600)
        self.nonce=0
    def call(self,route='chat.voice',payload=None):
        self.nonce+=1
        body=dict(protocol='NOX-P02-NATIVE-v1',runId='original-port',requestId=f'{self.nonce:032x}',route=route,payload=payload if payload is not None else dict(capture_id='a'*32,source='ru',target='es'))
        return json.loads(self.ingress.handle(json.dumps(body).encode()))['result']
    def speak(self,**extra):
        return self.call(payload=dict(capture_id='a'*32,source='ru',target='es',speak=True,**extra))
    def test_original_preview_never_autoplays_or_invents_audio_storage(self):
        result=self.call()
        self.assertEqual(result['state'],'PREVIEW_ONLY')
        self.assertEqual(self.workers,['asr','translate'])
        self.assertFalse(result['audio_stored']);self.assertFalse(result['physical_audio_confirmed'])
        self.assertNotIn('output_audio_id',result);self.assertEqual(self.spoken,[]);self.assertEqual(self.reviewed,[])
    def test_original_sapi_dict_is_native_receipt_after_bound_native_review(self):
        result=self.speak()
        self.assertEqual(result['state'],'NATIVE_TTS_SUBPROCESS_COMPLETED')
        self.assertEqual(result['playback']['state'],'TTS_SUBPROCESS_COMPLETED')
        self.assertEqual(self.spoken[0][0][0],'powershell.exe')
        self.assertEqual(len(self.reviewed),1);self.assertFalse(result['physical_audio_confirmed'])
        self.assertNotIn('output_audio_id',result)
    def test_missing_consent_preserves_one_use_capture_and_has_no_worker(self):
        self.fx.ports.mic_consent=lambda *args:False
        with self.assertRaises(ProtocolHold):self.speak()
        self.assertIn('a'*32,self.fx.audio);self.assertEqual(self.workers,[])
    def test_missing_preview_ui_preserves_capture(self):
        self.port.review=None
        with self.assertRaises(ProtocolHold):self.speak()
        self.assertIn('a'*32,self.fx.audio);self.assertEqual(self.workers,[])
    def test_page_supplied_approval_is_rejected(self):
        with self.assertRaises(ProtocolHold):self.speak(approved_preview=True)
        self.assertIn('a'*32,self.fx.audio);self.assertEqual(self.spoken,[])
    def test_mismatched_native_preview_digest_never_speaks(self):
        self.port.review=lambda scope,c:NativePreviewDecision(c['request_id'],'0'*64,True)
        with self.assertRaises(ProtocolHold):self.speak()
        self.assertEqual(self.spoken,[])
    def test_stop_in_native_review_cancels_original_session_before_sapi(self):
        observed=[]
        def stop_review(scope,c):
            observed.append(self.call('chat.stop',{}))
            return NativePreviewDecision(c['request_id'],c['text_sha256'],True)
        self.port.review=stop_review
        with self.assertRaises(ProtocolHold):self.speak()
        self.assertTrue(observed[0]['voiceStopped']);self.assertEqual(self.spoken,[])
    def test_model_revocation_after_original_asr_prevents_translation(self):
        self.port.model_authorize=lambda scope,model:not self.workers
        with self.assertRaises(ProtocolHold):self.speak()
        self.assertEqual(self.workers,['asr']);self.assertEqual(self.spoken,[])
    def test_native_review_cannot_change_principal_before_playback(self):
        def changed(scope,c):
            object.__setattr__(scope,'principal','other')
            return NativePreviewDecision(c['request_id'],c['text_sha256'],True)
        self.port.review=changed
        with self.assertRaises(ProtocolHold):self.speak()
        self.assertEqual(self.spoken,[])

    def test_changed_model_identity_after_asr_never_enters_translator(self):
        worker=adapters._run_worker.side_effect
        def change(name,payload,session,timeout):
            result=worker(name,payload,session,timeout)
            if name=='asr':self.service.translator.model_id='replaced-model'
            return result
        adapters._run_worker.side_effect=change
        with self.assertRaises(ProtocolHold):self.speak()
        self.assertEqual(self.workers,['asr']);self.assertEqual(self.spoken,[])
    def test_native_callback_replacement_stops_before_capture_consumption(self):
        rogue=[]
        def consent(*args):
            self.fx.ports.take_audio=lambda *args:rogue.append(args) or b'fake'
            return True
        self.fx.ports.mic_consent=consent
        with self.assertRaises(ProtocolHold):self.speak()
        self.assertEqual(rogue,[]);self.assertIn('a'*32,self.fx.audio)
    def test_original_playback_receipt_still_rejected_by_byte_audio_pipeline(self):
        from p02_runtime import P02Error
        receipt=self.speak()['playback']
        self.fx.voice.tts=lambda *args:receipt
        with self.assertRaisesRegex(P02Error,'TTS_INVALID_RESULT'):
            self.fx.voice.run(self.fx.scope.identity,b'voice',source='ru',target='es',
                              voice='es-v',microphone_consent=True)

    def test_authorization_cannot_replace_next_native_permission_callback(self):
        rogue=[]
        def authorize(*args):
            self.fx.ports.mic_consent=lambda *args:rogue.append(args) or True
            return True
        self.fx.ports.authorize=authorize
        with self.assertRaises(ProtocolHold):self.speak()
        self.assertEqual(rogue,[]);self.assertIn('a'*32,self.fx.audio)

if __name__=='__main__':unittest.main()
