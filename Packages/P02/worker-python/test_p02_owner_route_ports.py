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
    def test_native_stop_before_capture_does_not_consume_one_use_audio(self):
        import threading
        stopped = threading.Event()
        stopped.set()
        with self.assertRaisesRegex(RouteHold, "NATIVE_VOICE_STOPPED_BEFORE_CAPTURE"):
            self.ports.captured_voice(self.scope, {
                'capture_id': 'a'*32, 'source': 'ru', 'target': 'es', 'voice': 'es-v'
            }, stop=stopped)
        self.assertEqual(self.audio['a'*32], b'voice')

    def test_native_stop_after_voice_run_does_not_publish_output(self):
        import threading
        from types import SimpleNamespace
        stopped = threading.Event()
        published = []
        def finish_after_stop(*args, **kwargs):
            stopped.set()
            return SimpleNamespace(audio=b'audio', transcript='privet',
                                   response='hola', target_lang='es', mode='translate')
        self.ports.voice.run = finish_after_stop
        self.ports.store_output_audio = lambda scope, audio: published.append(audio) or 'b'*32
        with self.assertRaisesRegex(RouteHold, "NATIVE_VOICE_STOPPED_BEFORE_OUTPUT"):
            self.ports.captured_voice(self.scope, {
                'capture_id': 'a'*32, 'source': 'ru', 'target': 'es', 'voice': 'es-v'
            }, stop=stopped)
        self.assertEqual(published, [])

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
    def test_rag_revoked_during_existing_provider_call_cannot_publish_context(self):
        def revoke_and_read(*args):
            self.permissions.discard("chat.rag")
            return {"context": "private data", "sources": []}
        self.rag.context = revoke_and_read
        with self.assertRaises(PermissionError):
            self.ports.rag_context(self.scope, {"query": "facts"})

    def test_rag_owner_readiness_revoked_during_provider_call(self):
        def revoke_readiness(*args):
            self.ready.discard("chat.rag")
            return {"context": "private data", "sources": []}
        self.rag.context = revoke_readiness
        with self.assertRaisesRegex(RouteHold, "RAG_REVOKED"):
            self.ports.rag_context(self.scope, {"query": "facts"})

    def test_call_history_revoked_during_existing_provider_call(self):
        def revoke_and_return(scope, limit):
            self.permissions.discard("calls.history")
            return self.rows[:limit]
        self.ports.call_history = revoke_and_return
        with self.assertRaises(PermissionError):
            self.ports.calls_history(self.scope, {})

    def test_voice_revoked_during_model_run_does_not_publish_audio(self):
        from types import SimpleNamespace
        published = []
        def revoke_during_asr(*args, **kwargs):
            self.permissions.discard("chat.voice")
            return SimpleNamespace(audio=b"private", transcript="x",
                                   response="y", target_lang="es", mode="translate")
        self.ports.voice.run = revoke_during_asr
        self.ports.store_output_audio = lambda scope, audio: published.append(audio) or "b"*32
        with self.assertRaises(PermissionError):
            self.ports.captured_voice(self.scope, {"capture_id": "a"*32})
        self.assertEqual(published, [])

    def test_voice_output_store_revocation_never_returns_ticket(self):
        from types import SimpleNamespace
        self.ports.voice.run = lambda *args, **kwargs: SimpleNamespace(
            audio=b"private", transcript="x", response="y", target_lang="es",
            mode="translate")
        def revoke_during_store(scope, audio):
            self.permissions.discard("chat.voice")
            return "b"*32
        self.ports.store_output_audio = revoke_during_store
        with self.assertRaises(PermissionError):
            self.ports.captured_voice(self.scope, {"capture_id": "a"*32})

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

    def test_real_frozen_pack01_host_registration_preserves_acl_and_single_owner(self):
        """The shipped native bridge uses MappingProxyType at both levels."""
        import importlib.util
        import json
        import sys
        from types import MappingProxyType
        from p02_owner_route_ports import register_with_existing_pack01, RouteHold
        root = Path(__file__).resolve().parents[3]
        pack = root / "proposals" / "NOX-PACK01-50"
        spec = importlib.util.spec_from_file_location(
            "nox_actual_pack01_p02_binding_test", pack / "native_bridge.py")
        native = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = native
        try:
            spec.loader.exec_module(native)
            host = native.NoxPackHost(json.loads((pack / "catalog.json").read_text("utf-8")))
            original_routes = host.routes
            self.assertIsInstance(original_routes, MappingProxyType)
            self.assertIsInstance(original_routes["chat.rag"], MappingProxyType)
            bound = register_with_existing_pack01(
                host, native.BoundPort, lambda _session: self.scope,
                self.ports, receipt="P02-OWNER-TEST-ONLY")
            self.assertEqual(bound, frozenset(("chat.rag", "chat.voice", "calls.history")))
            self.assertIs(host.routes, original_routes)
            self.assertEqual(len(host.ports), 3)
            session = native.NativeSession(
                "tenant", "alice", "chat",
                frozenset(("chat.rag",)), frozenset())
            result = host.execute("chat.rag", {"query": "facts"}, session)
            self.assertEqual(result["sources"][0]["source_id"], "file:1")
            with self.assertRaises(native.HostDenied):
                host.execute("calls.history", {}, session)
            with self.assertRaises(TypeError):
                host.routes["chat.rag"]["owner"] = 1
            ports_before = dict(host.ports)
            with self.assertRaises(RouteHold):
                register_with_existing_pack01(
                    host, native.BoundPort, lambda _session: self.scope,
                    self.ports, receipt="P02-OWNER-TEST-ONLY")
            self.assertEqual(host.ports, ports_before)
        finally:
            sys.modules.pop(spec.name, None)
