"""V105 no-fake-receipt tests; isolated SQLite, never actual owner S03."""
import hashlib
import importlib
import json
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.testclient import TestClient

from nox_runpod.teacher_mesh.v105.native_v29_chat_bridge import register_native_v29_chat


class NativeV29BridgeTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.db = Path(self.dir.name) / 'mock_existing_s03.sqlite3'
        with sqlite3.connect(self.db) as con:
            con.execute('CREATE TABLE s03_items (id TEXT PRIMARY KEY, sha256 TEXT, text TEXT, ts TEXT)')
        mod = types.ModuleType('s03_memory')
        mod.DB = self.db
        self.previous = sys.modules.get('s03_memory')
        sys.modules['s03_memory'] = mod
        self.addCleanup(self._restore)
        self.app = FastAPI()
        self.calls = []
        self.record_answer = True

        async def main(body):
            self.calls.append(body.copy())
            question = body['messages'][-1]['content']
            answer = 'Проверенный ответ NOX.'
            async def wire():
                encoded = json.dumps({'choices':[{'delta':{'content':answer}}]},ensure_ascii=False)
                yield 'data: ' + encoded + '\n\n'
                if self.record_answer:
                    with sqlite3.connect(self.db) as conn:
                        conn.execute('INSERT INTO s03_items VALUES(?,?,?,?)',
                          ('receipt-00001',hashlib.sha256((question+answer).encode()).hexdigest(),
                           'U:'+question+' A:'+answer,'2026-11-14T00:00:00Z'))
                yield 'data: [DONE]\n\n'
            return StreamingResponse(wire(),media_type='text/event-stream')
        def session(request):
            return request.cookies.get('nox_owner') == 'yes'
        register_native_v29_chat(self.app,{
          '_session_ok':session,
          '_unauthorized':lambda:JSONResponse({'error':'AUTH'},status_code=401),
          '_proxy_completion':main,
        })
        self.client=TestClient(self.app)
        self.addCleanup(self.client.close)

    def _restore(self):
        if self.previous is None:sys.modules.pop('s03_memory',None)
        else:sys.modules['s03_memory']=self.previous

    def test_native_auth_is_not_optional(self):
        for path in ('/api/nox/chat/stream','/api/nox/stop'):
            self.assertEqual(self.client.post(path,json={'message':'Тест'}).status_code,401)
        self.assertEqual(len(self.calls),0)

    def test_one_real_native_stream_and_row_receipt(self):
        r=self.client.post('/api/nox/chat/stream',
            cookies={'nox_owner':'yes'},json={'message':'Привет NOX','history':[]})
        self.assertEqual(r.status_code,200)
        frames=[json.loads(line) for line in r.text.splitlines() if line.strip()]
        self.assertEqual([f['type'] for f in frames],['preparing','start','delta','done'])
        self.assertEqual(frames[2]['text'],'Проверенный ответ NOX.')
        self.assertTrue(frames[3]['saved'])
        self.assertTrue(frames[3]['s03_integrated'])
        self.assertEqual(frames[3]['exchange_id'],'receipt-00001')
        self.assertTrue(self.calls[0]['_owner'])

    def test_no_s03_row_means_no_fake_done(self):
        self.record_answer=False
        r=self.client.post('/api/nox/chat/stream',
            cookies={'nox_owner':'yes'},json={'message':'Проверь реальный ответ'})
        frames=[json.loads(line) for line in r.text.splitlines() if line.strip()]
        self.assertEqual(frames[-1]['type'],'error')
        self.assertEqual(frames[-1]['error'],'HOLD_S03_COMMIT_NOT_VERIFIED')
        self.assertFalse(any(f.get('saved') for f in frames))

    def test_client_dialog_id_never_authorizes_cross_scope(self):
        r=self.client.post('/api/nox/chat/stream',
            cookies={'nox_owner':'yes'},
            json={'message':'Привет','dialog_id':'a'*32})
        self.assertEqual(r.status_code,409)
        self.assertEqual(len(self.calls),0)

    def test_unverified_stop_does_not_claim_gpu_cancelled(self):
        r=self.client.post('/api/nox/stop',cookies={'nox_owner':'yes'},json={})
        self.assertEqual(r.status_code,409)
        self.assertNotIn('gpu_stop_verified',r.json())


if __name__=='__main__':
    unittest.main()
