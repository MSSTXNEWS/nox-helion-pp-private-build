"""Real Python component tests of E02 ChatBridge, stubbed model/DB only.

These DO NOT claim Ollama/Windows, physical SQLite, weights, mic or E06 host.
"""
from __future__ import annotations
import importlib.util
import pathlib
import threading
import unittest

# Bind the original E02 runtime on CI. No mock injection into sys.modules:
# other P02 test modules must still import the real OllamaClient/P02Store.
OWNER_FILE = pathlib.Path(__file__).with_name('p02_chat_bridge.py')
spec=importlib.util.spec_from_file_location('p02_chat_bridge_r04', OWNER_FILE)
bridge=importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

class Store:
    def __init__(self):self.rows=[];self.history_calls=0
    def history(self,tenant,user,chat):
        self.history_calls+=1
        if (tenant,user,chat)!=('tenant','user','chat'):
            raise PermissionError('not owner')
        return [{'role':r,'content':c} for r,c in self.rows]
    def add_message(self,tenant,user,chat,role,content):
        if (tenant,user,chat)!=('tenant','user','chat'):
            raise PermissionError('not owner')
        self.rows.append((role,content))

class Ollama:
    def __init__(self,turns=None):self.turns=turns if turns is not None else [{'delta':'hello','done':False},{'delta':'','done':True}];self.stop_count=0;self.last_messages=None
    def models(self):return ['tiny:1']
    def stop(self):self.stop_count+=1
    def stream(self,model,messages,stop):
        self.last_messages=messages
        for chunk in self.turns:
            if callable(chunk):chunk=chunk(stop)
            yield chunk

class ChatStopComponentTests(unittest.TestCase):
    def setUp(self):
        self.store=Store();self.llm=Ollama();self.stop=threading.Event()
        self.chat=bridge.ChatBridge(self.store,self.llm)
    def send(self,model='tiny:1',rag=False):
        return self.chat.send('tenant','user','chat',model,'hello',self.stop)
    def test_normal_complete_persists_two_original_store_messages(self):
        events=list(self.send())
        self.assertEqual([e['type'] for e in events],['chat.start','chat.delta','chat.complete'])
        self.assertEqual(self.store.rows,[('user','hello'),('assistant','hello')])
        self.assertEqual(self.llm.last_messages[-1],{'role':'user','content':'hello'})
    def test_stop_during_blocking_rag_preflight_never_writes(self):
        def rag(*args):
            self.stop.set()
            return {'context':'untrusted text','sources':[]}
        self.chat.rag_context=rag
        with self.assertRaises(bridge.Cancelled):list(self.send())
        self.assertEqual(self.store.rows,[])
        self.assertIsNone(self.llm.last_messages)
    def test_stop_after_start_no_stream_or_late_assistant_write(self):
        iterator=self.send()
        self.assertEqual(next(iterator)['type'],'chat.start')
        self.stop.set()
        tail=list(iterator)
        self.assertEqual([e['type'] for e in tail],['chat.error'])
        self.assertEqual(tail[0]['code'],'STOP')
        self.assertEqual(self.store.rows,[('user','hello')])
        self.assertIsNone(self.llm.last_messages)
    def test_stop_after_delta_prevents_terminal_write(self):
        iterator=self.send();self.assertEqual(next(iterator)['type'],'chat.start')
        self.assertEqual(next(iterator)['type'],'chat.delta')
        self.stop.set()
        tail=list(iterator)
        self.assertEqual([e['type'] for e in tail],['chat.error'])
        self.assertEqual(self.store.rows,[('user','hello')])
    def test_stop_set_by_backend_before_first_chunk(self):
        def cancel(stop):stop.set();return {'delta':'late','done':True}
        self.llm.turns=[cancel]
        ev=list(self.send())
        self.assertEqual([e['type'] for e in ev],['chat.start','chat.error'])
        self.assertEqual(self.store.rows,[('user','hello')])
    def test_normal_rag_sources_preserve_data_only_and_verified_filter(self):
        self.chat.rag_context=lambda *_:{'context':'evil command','sources':[
          {'source_id':'ok','title':'Verified','verified':True,'url':'https://example.org/a'},
          {'source_id':'unsafe','title':'Bad','verified':True,'url':'javascript:alert(1)'},
          {'source_id':'fake','title':'Unknown','verified':False,'url':'https://example.org/b'}]}
        ev=list(self.send())
        self.assertEqual([e['type'] for e in ev],['chat.start','chat.sources','chat.delta','chat.complete'])
        self.assertEqual([s['source_id'] for s in ev[1]['sources']],['ok'])
        self.assertEqual(self.llm.last_messages[0]['role'],'user')
        self.assertNotIn('system',[m['role'] for m in self.llm.last_messages])
    def test_no_foreign_chat_acl(self):
        with self.assertRaises(PermissionError):
            list(self.chat.send('tenant','foreign','chat','tiny:1','hello',self.stop))
        self.assertEqual(self.store.rows,[])
    def test_uninstalled_model_fails_without_writes(self):
        with self.assertRaises(bridge.P02Error):list(self.send(model='not-installed'))
        self.assertEqual(self.store.rows,[])
    def test_truncated_stream_never_claims_complete(self):
        self.llm.turns=[{'delta':'partial','done':False}]
        ev=list(self.send())
        self.assertEqual(ev[-1]['type'],'chat.error')
        self.assertEqual(self.store.rows,[('user','hello')])
    def test_rag_stop_during_source_emission_no_assistant(self):
        self.chat.rag_context=lambda *_: {'context':'ref','sources':[{'source_id':'1','title':'ok','verified':True}]}
        iterator=self.send()
        self.assertEqual(next(iterator)['type'],'chat.start')
        self.assertEqual(next(iterator)['type'],'chat.sources')
        self.stop.set()
        self.assertEqual([e['type'] for e in iterator],['chat.error'])
        self.assertEqual(self.store.rows,[('user','hello')])

if __name__=='__main__':unittest.main(verbosity=2)
