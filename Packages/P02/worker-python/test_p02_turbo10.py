"""Deterministic owner #2 contract suite; no live provider, browser, or call."""
import hashlib
import io
import pathlib
import sqlite3
import tempfile
import threading
import time
import unittest
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from p02_host_probe import inspect_parts, inventory_extracted_tree
from p02_capabilities import (Identity, context_key, LocalVoicePipeline,
    ConsentGatedSip, authorize_private_mobile, authorized_local_video)
from p02_runtime import OllamaClient, P02Error, P02Store, Cancelled
from p02_chat_bridge import ChatBridge

class Turbo10(unittest.TestCase):
    def test_01_readonly_source_archive_receipt(self):
        with tempfile.TemporaryDirectory() as d:
            base=pathlib.Path(d)
            self.assertEqual(inspect_parts(base)['status'],'HOLD')
            data=[b'ab',b'cd',b'ef']
            for i,v in enumerate(data):
                (base / f'source_0{i}.part').write_bytes(v)
            res=inspect_parts(base,expected_bytes=6,
                expected_sha256=hashlib.sha256(b'abcdef').hexdigest())
            self.assertEqual((res['status'],res['bytes_seen']),('VERIFIED',6))
            self.assertEqual(inventory_extracted_tree(base/'not-extracted')['status'],'HOLD')

    def test_02_installed_model_only_before_persistence(self):
        class Fake:
            def models(self): return ['real:1']
            def stream(self,*a):
                yield {'delta':'OK','done':False}
                yield {'delta':'','done':True}
        with tempfile.TemporaryDirectory() as d:
            db=sqlite3.connect(':memory:')
            store=P02Store(db,d);store.initialize();store.create_chat('t','u','c')
            b=ChatBridge(store,Fake())
            with self.assertRaisesRegex(P02Error,'not installed'):
                list(b.send('t','u','c','phantom:1','hello'))
            self.assertEqual(store.history('t','u','c'),[])
            self.assertEqual([e['type'] for e in b.send('t','u','c','real:1','hello')],
                             ['chat.start','chat.delta','chat.complete'])
            db.close()

    def test_03_local_ollama_redirect_denied(self):
        class Redirect(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                self.send_response(302)
                self.send_header('Location','https://example.org/steal')
                self.end_headers()
        server=ThreadingHTTPServer(('127.0.0.1',0),Redirect)
        th=threading.Thread(target=server.serve_forever,daemon=True);th.start()
        try:
            with self.assertRaisesRegex(P02Error,'REDIRECT_DENIED'):
                OllamaClient('http://127.0.0.1:%d'%server.server_port).models()
        finally:
            server.shutdown();server.server_close();th.join(timeout=3)

    def test_04_sqlite_host_inventory_is_readonly(self):
        db=sqlite3.connect(':memory:')
        db.execute('CREATE TABLE conversations(id TEXT PRIMARY KEY)')
        with tempfile.TemporaryDirectory() as d:
            s=P02Store(db,d)
            before=list(db.execute("SELECT name FROM sqlite_master WHERE type='table'"))
            self.assertEqual(s.host_schema_inventory(),('conversations',))
            with self.assertRaisesRegex(P02Error,'HOST_CHAT_SCHEMA_MAPPING_REQUIRED'):
                s.initialize()
            self.assertEqual(before,list(db.execute("SELECT name FROM sqlite_master WHERE type='table'")))
        db.close()

    def test_05_no_duplicate_persona_context(self):
        cores=frozenset({'core-original-01','core-original-02'})
        personas=frozenset({'persona-01','persona-02'})
        id1=Identity('t','u','core-original-01','persona-01','s')
        id2=Identity('t','u','core-original-02','persona-01','s')
        id3=Identity('t','u','core-original-01','persona-02','s')
        k1=context_key(id1,cores,personas)
        self.assertEqual(len(k1),68)
        self.assertEqual(len({k1,context_key(id2,cores,personas),context_key(id3,cores,personas)}),3)
        with self.assertRaises(PermissionError):
            context_key(id1,frozenset(),personas)

    def test_06_voice_ru_es_and_maestro_on_one_local_host(self):
        id=Identity('t','u','core-original-01','p','s')
        calls=[]
        def asr(scope,audio,lang,stop):
            calls.append('asr');return 'Привет'
        def chat(scope,text,source,target,directive,stop):
            calls.append(directive);return 'Hola'
        def tts(scope,text,lang,voice,stop):
            calls.append('tts');return b'LOCAL-AUDIO'
        p=LocalVoicePipeline(asr,chat,tts,approved_models=True,
                             permitted_voices=frozenset({'approved-local-es'}))
        v=p.run(id,b'WAV',source='ru',target='es',voice='approved-local-es',
                microphone_consent=True)
        self.assertEqual((v.response,v.audio),('Hola',b'LOCAL-AUDIO'))
        v=p.run(id,b'WAV',source='es',target='ru',voice='approved-local-es',
                microphone_consent=True,mode='maestro',level='B1')
        self.assertIn('MAESTRO_CEFR_B1',calls)
        with self.assertRaises(PermissionError):
            p.run(id,b'WAV',source='ru',target='es',voice='approved-local-es')
        with self.assertRaises(PermissionError):
            LocalVoicePipeline(asr,chat,tts).run(id,b'WAV',source='ru',target='es',
                voice='approved-local-es',microphone_consent=True)

    def test_07_voice_stop_and_input_quota(self):
        id=Identity('t','u','core-original-01','p','s')
        def asr(scope,audio,lang,stop):
            stop.set();return 'hi'
        p=LocalVoicePipeline(asr,lambda *a: 'yes',lambda *a: b'a',
             approved_models=True,permitted_voices=frozenset({'voice'}))
        with self.assertRaises(Cancelled):
            p.run(id,b'OK',source='ru',target='es',voice='voice',
                  microphone_consent=True,stop=threading.Event())
        with self.assertRaises(ValueError):
            p.run(id,b'x'*(16*1024*1024+1),source='ru',target='es',voice='voice',microphone_consent=True)

    def test_08_sip_quote_and_one_use_consent(self):
        id=Identity('t','u','core-original-01','p','s')
        called=[]
        gate=ConsentGatedSip(lambda scope,quote,stop:called.append(quote.number) or 'placed',
                             user_approval=lambda scope,quote: True,
                             provider_quote_verify=lambda scope,quote: True)
        q=gate.new_quote('+34600123456','authorized interpretation call','0.75','EUR',
                         'provider-q-123',time.time()+30)
        self.assertEqual(q.max_cost,Decimal('0.75'))
        self.assertEqual(gate.place(id,q),'placed')
        self.assertEqual(called,['+34600123456'])
        with self.assertRaises(PermissionError): gate.place(id,q)
        with self.assertRaises(ValueError):
            gate.new_quote('112','any','-3','EUR','bad',time.time()+30)
        missing=ConsentGatedSip(None,user_approval=None)
        with self.assertRaisesRegex(P02Error,'HOLD'): missing.place(id,q)

    def test_09_mobile_peer_origin_csrf_and_video_consent(self):
        id=Identity('t','u','core-original-01','p','s')
        csrf=b'a'*32
        args={'verified_private_peer':True,'trusted_origin':'https://noxtest.tailnet.ts.net/',
              'observed_origin':'https://noxtest.tailnet.ts.net/',
              'expected_csrf':csrf,'received_csrf':csrf,'native_session_approved':True}
        self.assertTrue(authorize_private_mobile(id,**args))
        self.assertFalse(authorize_private_mobile(id,**(args|{'verified_private_peer':False})))
        self.assertFalse(authorize_private_mobile(id,**(args|{'received_csrf':b'fake'})))
        self.assertFalse(authorize_private_mobile(id,**(args|{'observed_origin':'https://evil.org/'})))
        with tempfile.TemporaryDirectory() as d:
            file=pathlib.Path(d)/'local.mp4';file.write_bytes(b'ftyp')
            with self.assertRaises(PermissionError):
                authorized_local_video(d,str(file),native_user_selected=False)
            self.assertEqual(authorized_local_video(d,str(file),native_user_selected=True),str(file))
            (pathlib.Path(d)/'evil.html').write_text('<script>')
            with self.assertRaises(P02Error):
                authorized_local_video(d,str(pathlib.Path(d)/'evil.html'),native_user_selected=True)

    def test_10_rag_provenance_and_reply_quota(self):
        class Fake:
            def __init__(self): self.cancelled=False
            def models(self):return ['tag']
            def stop(self):self.cancelled=True
            def stream(self,model,messages,stop):
                yield {'delta':'x'*1_000_001,'done':False}
                yield {'delta':'','done':True}
        with tempfile.TemporaryDirectory() as d:
            db=sqlite3.connect(':memory:');store=P02Store(db,d)
            store.initialize();store.create_chat('t','u','c')
            fake=Fake();bridge=ChatBridge(store,fake)
            events=list(bridge.send('t','u','c','tag','prompt'))
            self.assertEqual(events[-1]['code'],'OLLAMA_ERROR')
            self.assertTrue(fake.cancelled)
            self.assertEqual([e['role'] for e in store.history('t','u','c')],['user'])
            db.close()

if __name__ == '__main__':
    unittest.main(verbosity=2)
