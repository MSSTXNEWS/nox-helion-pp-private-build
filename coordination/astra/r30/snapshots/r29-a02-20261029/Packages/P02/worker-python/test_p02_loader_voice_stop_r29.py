"""Existing PACK01 registration must convey native STOP to the existing voice port."""
import threading
import unittest
from dataclasses import dataclass
from test_p02_owner_route_ports import RouteTests
from p02_owner_route_ports import register_with_existing_pack01, RouteHold
from p02_runtime import Cancelled

@dataclass(frozen=True)
class Port:
    call: object
    available: object
    evidence_id: str
    owner: int

class Dispatcher:
    def __init__(self):
        self.ports={}
        self.routes={r:{'owner':2} for r in ('chat.voice','chat.rag','calls.history')}
    def bind(self,route,port):self.ports[route]=port

class VoiceStopWiring(unittest.TestCase):
    setUp=RouteTests.setUp
    tearDown=RouteTests.tearDown
    def bind(self, **kwargs):
        d=Dispatcher()
        register_with_existing_pack01(d,Port,lambda session:self.scope,self.ports,
                                     receipt='R29-EXACT-SOURCE',**kwargs)
        return d.ports
    def args(self):
        return {'capture_id':'a'*32,'source':'ru','target':'es','voice':'es-v'}

    def test_unbound_native_stop_keeps_voice_hold_without_consuming_capture(self):
        ports=self.bind()
        self.assertFalse(ports['chat.voice'].available())
        self.assertTrue(ports['chat.rag'].available())
        self.assertTrue(ports['calls.history'].available())
        with self.assertRaisesRegex(RouteHold,'NATIVE_VOICE_STOP_BINDING_REQUIRED'):
            ports['chat.voice'].call(object(),self.args())
        self.assertIn('a'*32,self.audio)

    def test_preexisting_native_stop_reaches_capture_gate(self):
        stop=threading.Event();stop.set();session=object();seen=[]
        ports=self.bind(native_stop_from_session=lambda value:seen.append(value) or stop)
        self.assertTrue(ports['chat.voice'].available())
        with self.assertRaisesRegex(RouteHold,'STOPPED_BEFORE_CAPTURE'):
            ports['chat.voice'].call(session,self.args())
        self.assertEqual(seen,[session]);self.assertIn('a'*32,self.audio)

    def test_stop_during_asr_prevents_llm_and_audio_output(self):
        stop=threading.Event();used=[]
        def asr(*args):
            self.assertIs(args[-1],stop);stop.set();return 'привет'
        self.voice.asr=asr
        self.voice.chat=lambda *args:used.append('llm') or 'hola'
        self.ports.store_output_audio=lambda *args:used.append('output') or 'b'*32
        port=self.bind(native_stop_from_session=lambda _:stop)['chat.voice']
        with self.assertRaises(Cancelled):port.call(object(),self.args())
        self.assertEqual(used,[])

    def test_invalid_resolved_stop_fails_before_capture(self):
        for result in (None,True,{},'page-stop'):
            port=self.bind(native_stop_from_session=lambda _,v=result:v)['chat.voice']
            with self.subTest(result=result),self.assertRaisesRegex(RouteHold,'NATIVE_VOICE_STOP_TOKEN_REQUIRED'):
                port.call(object(),self.args())
        self.assertIn('a'*32,self.audio)

if __name__=='__main__':unittest.main()
