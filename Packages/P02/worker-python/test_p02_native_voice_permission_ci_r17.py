"""R17 exact owner-source native consent boundary; offline unit test, no hardware/EXE."""
import importlib.util
import pathlib
import sys
import threading
import types
import unittest
from dataclasses import dataclass

class P02Error(Exception): pass
class P02Store:
    def history(self, *a): return []
@dataclass(frozen=True)
class Identity:
    tenant: str
    principal: str
    session_id: str
class LocalVoicePipeline:
    approved_models = True
    def __init__(self): self.calls = []
    def run(self, scope, audio, **kw):
        self.calls.append((scope, audio, kw))
        assert kw['microphone_consent'] is True
        return types.SimpleNamespace(transcript='привет', response='hola',
                                     audio=b'wav', target_lang='es', mode='translate')
class ChatBridge: pass

def owner():
    deps = {'p02_runtime':types.SimpleNamespace(P02Error=P02Error,P02Store=P02Store),
            'p02_capabilities':types.SimpleNamespace(Identity=Identity,LocalVoicePipeline=LocalVoicePipeline),
            'p02_chat_bridge':types.SimpleNamespace(ChatBridge=ChatBridge)}
    previous={k:sys.modules.get(k) for k in deps}
    try:
        sys.modules.update(deps)
        path=pathlib.Path(__file__).with_name('p02_owner_route_ports.py')
        spec=importlib.util.spec_from_file_location('p02_r17_native_proof',path)
        module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module
        spec.loader.exec_module(module)
        return module
    finally:
        for k,v in previous.items():
            if v is None:sys.modules.pop(k,None)
            else:sys.modules[k]=v

class VoiceConsentGate(unittest.TestCase):
    def setUp(self):
        self.m=owner();self.voice=LocalVoicePipeline();self.consumed=[];self.proofs=[]
        self.scope=self.m.NativeScope('t','u','chat','S-1-5-21-123','sess',Identity('t','u','sess'))
        self.args={'capture_id':'e'*32,'source':'ru','target':'es','voice':'local'}
    def ports(self,proof):
        return self.m.OwnerTwoPorts(store=P02Store(),native_authorize=lambda *a:True,
             voice_pipeline=self.voice,native_mic_consent=proof,
             native_take_audio=lambda scope,capture:(self.consumed.append(capture) or b'audio'),
             native_store_output_audio=lambda *a:'f'*32,owner_ready=lambda r:True)
    def test_missing_provider_holds_route(self):
        self.assertFalse(self.ports(None).available('chat.voice'))
    def test_denied_or_truthy_proof_does_not_consume(self):
        for proof in (lambda *a:False,lambda *a:1):
            with self.subTest(proof=proof):
                with self.assertRaises(PermissionError):self.ports(proof).captured_voice(self.scope,self.args)
        self.assertEqual(self.consumed,[])
    def test_provider_exception_fails_closed(self):
        def explode(*a):raise RuntimeError('secret')
        with self.assertRaisesRegex(self.m.RouteHold,'NATIVE_MIC_PERMISSION_CHECK_HOLD'):
            self.ports(explode).captured_voice(self.scope,self.args)
        self.assertEqual(self.consumed,[])
    def test_true_proof_scoped_and_forwarded(self):
        def proof(scope,capture):self.proofs.append((scope,capture));return True
        result=self.ports(proof).captured_voice(self.scope,self.args)
        self.assertEqual(self.proofs,[(self.scope,'e'*32)])
        self.assertEqual(self.consumed,['e'*32])
        self.assertTrue(self.voice.calls[0][2]['microphone_consent'])
        self.assertEqual(result['output_audio_id'],'f'*32)
    def test_stop_in_proof_cannot_consume(self):
        stop=threading.Event()
        def proof(*a):stop.set();return True
        with self.assertRaisesRegex(self.m.RouteHold,'STOPPED_BEFORE_CAPTURE'):
            self.ports(proof).captured_voice(self.scope,self.args,stop)
        self.assertEqual(self.consumed,[])
    def test_page_claims_never_authorize_audio(self):
        for key in ('audio','audio_path','microphone_consent','mic_consent'):
            with self.subTest(key=key):
                with self.assertRaises(PermissionError):
                    self.ports(lambda *a:True).captured_voice(self.scope,{**self.args,key:True})
        self.assertEqual(self.consumed,[])

if __name__=='__main__':unittest.main()
