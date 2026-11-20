"""Offline owner-port safety checks; no network, no model or provider credentials."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from p02_runtime import P02Store
from p02_capabilities import Identity, LocalVoicePipeline
from p02_owner_route_ports import NativeScope, OwnerTwoPorts, RouteHold

class RouteTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.db=sqlite3.connect(':memory:')
        self.store=P02Store(self.db,Path(self.temp.name)/'store')
        self.store.initialize()
        self.store.create_chat('tenant','alice','chat')
        self.scope=NativeScope('tenant','alice','chat','S-1-5-21-123-456-789',
                               'session', Identity('tenant','alice','core-1','persona-1','session'))
        self.permissions={'chat.rag','chat.voice','calls.history'}
        self.ready={'chat.rag','chat.voice','calls.history'}
        self.audio={"a"*32:b'voice'}
        self.rows=[{'tenant':'tenant','principal':'alice','call_id':'id1',
                    'started_epoch':1000,'status':'completed','internal_secret':'not for JS'}]
        self.rag=type('RAG',(),{'context': lambda _,sid,chat,query,topk:{'context':'data',
                   'sources':[{'verified':True,'source_id':'file:1','title':'facts.md'}]}})()
        self.voice=LocalVoicePipeline(lambda *a:'привет',lambda *a:'hola',
                 lambda *a:b'audio',approved_models=True,permitted_voices=frozenset({'es-v'}))
        def take(scope,id):return self.audio.pop(id)
        self.ports=OwnerTwoPorts(store=self.store,
             native_authorize=lambda scope,route: route in self.permissions,
             rag_index=self.rag,voice_pipeline=self.voice,native_take_audio=take,
             native_store_output_audio=lambda scope,audio:'b'*32,
             native_call_history=lambda scope,n:self.rows[:n],
             owner_ready=lambda route:route in self.ready)
    def tearDown(self):self.db.close();self.temp.cleanup()
    def test_rag_existing_index_and_sources(self):
        value=self.ports.rag_context(self.scope,{'query':'facts'})
        self.assertEqual(value['sources'][0]['source_id'],'file:1')
        self.assertEqual(value['context'],'data')
    def test_rag_rejects_unverified_source(self):
        self.rag.context=lambda *a:{'context':'ok','sources':[{'verified':False,'source_id':'fake'}]}
        self.assertEqual(self.ports.rag_context(self.scope,{'query':'facts'})['sources'],[])
    def test_unavailable_routes_hold(self):
        self.ready.clear()
        for call,args in ((self.ports.rag_context,{'query':'hi'}),
                          (self.ports.captured_voice,{'capture_id':'a'*32}),
                          (self.ports.calls_history,{})):
            with self.assertRaises(RouteHold):call(self.scope,args)
    def test_requires_existing_host_chat_acl(self):
        bad=NativeScope('tenant','mallory','chat',self.scope.windows_sid,'session',
                        Identity('tenant','mallory','core-1','persona-1','session'))
        with self.assertRaises(PermissionError):self.ports.rag_context(bad,{'query':'hi'})
    def test_native_route_denial(self):
        self.permissions.clear()
        with self.assertRaises(PermissionError):self.ports.rag_context(self.scope,{'query':'hi'})
    def test_voice_capture_and_one_time_use(self):
        res=self.ports.captured_voice(self.scope,{'capture_id':'a'*32,
            'source':'ru','target':'es','voice':'es-v'})
        self.assertEqual(res['response'],'hola')
        self.assertEqual(res['output_audio_id'],'b'*32)
        self.assertNotIn('audio',res)
        with self.assertRaises(RouteHold):self.ports.captured_voice(self.scope,{
            'capture_id':'a'*32,'source':'ru','target':'es','voice':'es-v'})
    def test_voice_rejects_page_audio(self):
        with self.assertRaises(PermissionError):self.ports.captured_voice(self.scope,{
            'capture_id':'a'*32,'audio':b'evil'})
        self.assertEqual(self.audio['a'*32],b'voice')
    def test_call_history_sanitizes_provider_data(self):
        calls=self.ports.calls_history(self.scope,{})['calls']
        self.assertEqual(calls,[{'call_id':'id1','started_epoch':1000,'status':'completed'}])
    def test_cross_tenant_call_history_blocked(self):
        self.rows[0]['tenant']='another'
        with self.assertRaises(PermissionError):self.ports.calls_history(self.scope,{})
    def test_call_history_malformed_rejected(self):
        self.rows[0]['started_epoch']=True
        with self.assertRaises(PermissionError):self.ports.calls_history(self.scope,{})
    def test_sid_mismatch_blocked(self):
        bad=NativeScope('tenant','alice','chat','invalid','session',self.scope.identity)
        with self.assertRaises(PermissionError):self.ports.rag_context(bad,{'query':'facts'})
    def test_limits_bool_rejected(self):
        with self.assertRaises(ValueError):self.ports.calls_history(self.scope,{'limit':True})
        with self.assertRaises(ValueError):self.ports.rag_context(self.scope,{'query':'hi','top_k':True})
if __name__=='__main__':unittest.main(verbosity=2)

class ExistingDispatcherBindingTests(RouteTests):
    def test_registers_only_three_ports_and_uses_native_mapper(self):
        from p02_owner_route_ports import register_with_existing_pack01
        from dataclasses import dataclass
        @dataclass(frozen=True)
        class BoundPort:
            call: object
            available: object
            evidence_id: str
            owner: int
        class Dispatcher:
            def __init__(self):
                self.ports={}
                self.routes={x:{'owner':2} for x in ('chat.rag','chat.voice','calls.history')}
            def bind(self,route,port):self.ports[route]=port
        d=Dispatcher()
        scope=self.scope
        bound=register_with_existing_pack01(d,BoundPort,lambda _:scope,self.ports,receipt='E02-SOURCE-PIN')
        self.assertEqual(len(bound),3)
        self.assertEqual(d.ports['chat.rag'].call(object(),{'query':'facts'})['context'],'data')
        self.assertEqual(d.ports['calls.history'].call(object(),{})['calls'][0]['call_id'],'id1')
        from p02_owner_route_ports import RouteHold
        with self.assertRaises(RouteHold):
            register_with_existing_pack01(d,BoundPort,lambda _:scope,self.ports,receipt='OLD-RECEIPT')
    def test_refuses_foreign_dispatcher_route_owner(self):
        from p02_owner_route_ports import register_with_existing_pack01, RouteHold
        class Dispatcher:
            ports={}
            routes={'chat.rag':{'owner':1},'chat.voice':{'owner':2},'calls.history':{'owner':2}}
        with self.assertRaises(RouteHold):
            register_with_existing_pack01(Dispatcher(),lambda *args:None,
                                          lambda _:self.scope,self.ports,receipt='E02-PIN')