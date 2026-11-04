"""Targeted K03 source checks: one transport, scoped history, native stream frames."""
from pathlib import Path
import contextlib
import importlib.util
import io
import json
import struct
import sys
import threading
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'Packages/P02/worker-python'),str(ROOT/'Packages/P03/Source/python-host'),str(ROOT/'src')]
spec=importlib.util.spec_from_file_location('nox_native_bridge',ROOT/'proposals/NOX-PACK01-50/native_bridge.py')
native=importlib.util.module_from_spec(spec);sys.modules[spec.name]=native;spec.loader.exec_module(native)
from p02_onehost import create_onehost_p02
from p03_onehost_port import P03OneHostPort
from p02_native_ingress import NativeIngress, ProtocolHold
from p02_framed_worker import serve_native_frames
from p02_runtime import Cancelled, P02Timeout, OllamaClient
from unittest.mock import patch

class Store:
    def __init__(self): self.rows=[];self.context=[];self.safe=True
    def history(self,t,p,c,limit=80):return [{k:v for k,v in x.items() if k!='_scope'} for x in self.rows if x.get('_scope')==(t,p,c)][-limit:]
    def add_message(self,*a):raise AssertionError('Must use atomic original exchange')
    def add_exchange(self,t,p,c,prompt,answer,authorize):
        authorize();self.context.append((t,p,c));self.rows.extend([
            {'role':'user','content':prompt,'_scope':(t,p,c)},
            {'role':'assistant','content':answer,'_scope':(t,p,c)}])
    def store_file(self,*a):raise RuntimeError('ATTACHMENTS_HOLD')
    def assert_model_switch_safe(self):
        if not self.safe:raise RuntimeError('SEED_LINEAGE_HOLD')
    def lineage_status(self):return {'status':'PRESERVED'}
    def resolve_chat_id(self,core,persona):
        if core not in ('CORE','ATLAS') or persona not in ('p1','p2'):raise PermissionError('Unknown persona')
        return core+':'+persona
    @contextlib.contextmanager
    def model_context(self,model):yield

class Client:
    def __init__(self):self.stopped=False;self.streams=0
    def models(self):return ['coder:1']
    def stream(self,model,messages,stop=None):
        self.streams+=1
        yield {'delta':'hello','done':False}
        if self.stopped or stop is not None and stop.is_set():raise Cancelled('STOP')
        yield {'delta':' world','done':True}
    def stop(self):self.stopped=True

class TestOneHost(unittest.TestCase):
    def setUp(self):
        self.store=Store();self.client=Client();self.events=[]
        self.api=create_onehost_p02(self.store,client=self.client,event_sink=self.events.append)
        self.scope=native.NativeSession('local','user','default',frozenset({'helion.chat','chat.model','chat.history','chat.stop'}),frozenset({'chat.history'}))
    def test_selection_and_scoped_stream_share_one_client(self):
        self.api.list_models(self.scope,{'model':'coder:1'})
        reply=self.api.chat(self.scope,{'text':'hi','core_id':'ATLAS','persona_id':'p2'})
        self.assertEqual(reply,{'answer':'hello world','done':True})
        self.assertIs(self.api.client,self.client);self.assertEqual(self.client.streams,1)
        self.assertEqual(self.store.context,[('local','user','ATLAS:p2')])
        self.assertEqual(''.join(x['delta'] for x in self.events),'hello world')
    def test_seed_gate_prevents_model_mutation(self):
        self.store.safe=False
        with self.assertRaisesRegex(RuntimeError,'SEED_LINEAGE_HOLD'):self.api.list_models(self.scope,{'model':'coder:1'})
        self.assertIsNone(self.api.selected_model())
    def test_invalid_persona_denied_before_transport(self):
        with self.assertRaises(PermissionError):self.api.chat(self.scope,{'text':'hi','core_id':'CORE','persona_id':'alien'})
        self.assertEqual(self.client.streams,0)
    def test_stop_during_delta_never_commits_exchange(self):
        self.api.list_models(self.scope,{'model':'coder:1'})
        self.api.event_sink=lambda event:self.api.stop(self.scope,{})
        with self.assertRaisesRegex(ProtocolHold,"NATIVE_CHAT_STOP"):self.api.chat(self.scope,{'text':'hi'})
        self.assertEqual(self.store.rows,[])
        self.assertTrue(self.api.stop_requested())
    def test_history_does_not_probe_offline_model(self):
        self.client.models=lambda:(_ for _ in ()).throw(ConnectionError())
        self.assertEqual(self.api.history(self.scope,{}),{'messages':[]})
    def test_offline_handshake_keeps_seed_and_s03_available(self):
        self.client.models=lambda:(_ for _ in ()).throw(ConnectionError())
        result=self.api.list_models(self.scope,{})
        self.assertEqual(result['provider_state'],'OFFLINE')
        self.assertEqual(result['models'],[])
        self.assertEqual(result['lineage']['status'],'PRESERVED')

    def test_coder_success_does_not_latch_shared_stop(self):
        self.api.list_models(self.scope,{'model':'coder:1'})
        coder=self.api.create_coder(lambda *args:True)
        self.assertEqual(coder(self.scope,{'task':'a','source_head':'head'}),'hello world')
        self.assertFalse(self.api.stop_event.is_set())
        self.assertIs(coder.ollama,self.client)

    def test_timeout_is_not_reported_as_user_stop(self):
        with patch('p02_runtime._OPENER.open', side_effect=TimeoutError()):
            with self.assertRaises(P02Timeout):OllamaClient().models()
        self.api.list_models(self.scope,{'model':'coder:1'})
        self.client.stream=lambda *args:(_ for _ in ()).throw(P02Timeout('deadline'))
        with self.assertRaisesRegex(ProtocolHold,'NATIVE_CHAT_TIMEOUT'):
            self.api.chat(self.scope,{'text':'hi'})
        self.assertFalse(self.api.stop_requested())
        self.assertEqual(self.store.rows,[])

    def test_installed_and_digest_use_same_existing_ollama(self):
        catalog={'version':'NOX-INTEGRATION-PACK-01','actions':[
            {'taskId':f'NIP01-{i:02d}','routeId':r,'owner':o,'risk':risk}
            for i,(r,o,risk) in enumerate(native.APPROVED_NATIVE_POLICY,1)]}
        host=native.NoxPackHost(catalog)
        port=P03OneHostPort(self.client)
        bound=port.register(host,native.BoundPort,receipt='source-receipt')
        self.assertNotIn('models.pull',bound)
        scope=native.NativeSession('local','user','default',frozenset({'models.installed','models.digest'}))
        self.client._open=lambda path:io.BytesIO(json.dumps({'models':[{'name':'coder:1','digest':'sha256:'+'a'*64}]}).encode())
        ingress=NativeIngress(host,lambda:scope,expected_run_id='k03',allow_modelcenter_reads=True)
        def invoke(route,args,nonce):
            return json.loads(ingress.handle(json.dumps({'protocol':'NOX-P02-NATIVE-v1','runId':'k03','requestId':nonce*32,'route':route,'payload':args}).encode()))['result']
        self.assertEqual(invoke('models.installed',{},'b')['models'][0]['tag'],'coder:1')
        digest=invoke('models.digest',{'modelTag':'coder:1'},'c')
        self.assertEqual(digest['ollamaReportedManifestDigest'],'sha256:'+'a'*64)
        self.assertFalse(digest['independentlyVerified'])
        self.assertIs(port.ollama,self.api.client)

    def test_events_share_nonce_and_do_not_replace_terminal(self):
        catalog={'version':'NOX-INTEGRATION-PACK-01','actions':[
            {'taskId':f'NIP01-{i:02d}','routeId':r,'owner':o,'risk':risk}
            for i,(r,o,risk) in enumerate(native.APPROVED_NATIVE_POLICY,1)]}
        host=native.NoxPackHost(catalog)
        host.bind('helion.chat',native.BoundPort(self.api.chat,lambda:True,'receipt',2))
        ingress=NativeIngress(host,lambda:self.scope,expected_run_id='k03')
        ingress.bind_event_sink=lambda sink:setattr(self.api,'event_sink',sink)
        self.api.list_models(self.scope,{'model':'coder:1'})
        nonce='a'*32
        request=json.dumps({'protocol':'NOX-P02-NATIVE-v1','runId':'k03','requestId':nonce,'route':'helion.chat','payload':{'text':'hi'}}).encode()
        output=io.BytesIO()
        serve_native_frames(ingress,io.BytesIO(struct.pack('>I',len(request))+request),output)
        raw=io.BytesIO(output.getvalue());frames=[]
        while head:=raw.read(4):frames.append(json.loads(raw.read(struct.unpack('>I',head)[0])))
        self.assertEqual([f['status'] for f in frames],['EVENT','EVENT','OK'])
        self.assertTrue(all(f['requestId']==nonce for f in frames))
        self.assertEqual(frames[-1]['result']['answer'],'hello world')

if __name__=='__main__':unittest.main()
