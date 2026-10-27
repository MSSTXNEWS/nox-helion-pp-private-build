import io
import json
import sqlite3
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from p02_runtime import P02Store, OllamaClient, P02Error, Cancelled, authorized_app_message

class FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *_): pass
    def do_GET(self):
        data = b'{"models":[{"name":"tiny:latest"}]}'
        self.send_response(200); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_POST(self):
        req=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        assert req['stream'] is True
        if req['model']=='broken':
            payload=b'{"message":{"content":"partial"},"done":false}\n'
        elif req['model']=='error':
            payload=b'{"error":"backend_failure","done":true}\n'
        else:
            payload=(b'{"message":{"content":"Hello"},"done":false}\n'
                     b'{"message":{"content":""},"done":true,"done_reason":"stop"}\n')
        self.send_response(200); self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)

class P02Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0), FakeOllama)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=5)
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory()
        self.db=sqlite3.connect(':memory:')
        self.store=P02Store(self.db,Path(self.dir.name)/'att')
        self.store.initialize();self.store.initialize();self.store.create_chat('tenant','alice','chat1')
    def tearDown(self):self.db.close();self.dir.cleanup()
    def test_sqlite_acl_history_retention(self):
        self.store.add_message('tenant','alice','chat1','user','Bonjour')
        self.assertEqual(self.store.history('tenant','alice','chat1')[0]['content'],'Bonjour')
        with self.assertRaises(PermissionError):self.store.history('tenant','eve','chat1')
        with self.assertRaises(PermissionError):self.store.history('else','alice','chat1')
        self.assertEqual(self.store.prune('tenant','alice','chat1',9999999999),1)
        self.assertEqual(self.store.history('tenant','alice','chat1'),[])
    def test_staged_attachment_id_hash_delete(self):
        content=b'%PDF-1.7\nhello'
        ack=self.store.store_file('tenant','alice','chat1','application/pdf',io.BytesIO(content))
        self.assertEqual(len(ack['stored_id']),32)
        self.assertEqual(self.store.read_file('tenant','alice','chat1',ack['stored_id']),content)
        with self.assertRaises(PermissionError):self.store.read_file('tenant','eve','chat1',ack['stored_id'])
        self.store.delete_chat('tenant','alice','chat1')
        self.assertEqual(self.store.collect_garbage(),1)
        self.assertEqual(self.store.collect_garbage(),0)
    def test_invalid_mime_and_quota(self):
        with self.assertRaises(P02Error):self.store.store_file('tenant','alice','chat1','application/pdf',io.BytesIO(b'MZbad'))
        with self.assertRaises(P02Error):self.store.store_file('tenant','alice','chat1','text/html',io.BytesIO(b'<script>'))
        with self.assertRaises(P02Error):self.store.store_file('tenant','alice','chat1','text/plain',io.BytesIO(b'x'*(25*1024*1024+1)))
        self.assertEqual(list(self.store.blobs.glob('*.blob')),[])
        self.assertEqual(list(self.store.staging.glob('*.stage')),[])
    def test_webview_policy(self):
        self.assertTrue(authorized_app_message('https://nox.invalid/app','chat.send',True,False))
        self.assertFalse(authorized_app_message('https://nox.invalid/app','history.delete',True,False))
        self.assertTrue(authorized_app_message('https://nox.invalid/app','history.delete',True,True))
        for origin in ('https://evil.example','https://nox.invalid.evil.example','file:///etc/passwd',
                       'https://nox.invalid:443/app','http://nox.invalid/app'):
            self.assertFalse(authorized_app_message(origin,'chat.send',True,True), origin)
    def test_ollama_models_stream_and_abort(self):
        ollama=OllamaClient(f'http://127.0.0.1:{self.server.server_port}')
        self.assertEqual(ollama.models(),['tiny:latest'])
        self.assertEqual(''.join(x['delta'] for x in ollama.stream('tiny:latest',[{'role':'user','content':'Hi'}])), 'Hello')
        with self.assertRaises(P02Error):list(ollama.stream('broken',[{'role':'user','content':'Hi'}]))
        with self.assertRaises(P02Error):list(ollama.stream('error',[{'role':'user','content':'Hi'}]))
        stop=threading.Event();stop.set()
        with self.assertRaises(Cancelled):list(ollama.stream('tiny:latest',[{'role':'user','content':'Hi'}],stop))
        with self.assertRaises(ValueError):OllamaClient('https://evil.example')

if __name__=='__main__':unittest.main(verbosity=2)

class ChatBridgeTests(unittest.TestCase):
    def test_chat_rag_and_error_flow(self):
        from p02_chat_bridge import ChatBridge
        class Fake:
            def stream(self, model, messages, stop):
                self.messages = messages
                yield {'delta':'OK', 'done':False}
                yield {'delta':'', 'done':True}
        db=sqlite3.connect(':memory:')
        with tempfile.TemporaryDirectory() as d:
            store=P02Store(db,Path(d)); store.initialize();store.create_chat('t','u','c')
            fake=Fake()
            bridge=ChatBridge(store,fake,lambda *args:'Relevant source')
            events=list(bridge.send('t','u','c','tiny','Hi'))
            self.assertEqual([x['type'] for x in events], ['chat.start','chat.delta','chat.complete'])
            self.assertEqual(len(store.history('t','u','c')),2)
            self.assertEqual(fake.messages[0]['role'],'system')
        db.close()
