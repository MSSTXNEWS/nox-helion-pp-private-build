"""V112 regression against fixture SQLite and synthetic SSE. Never a live NOX receipt."""
import hashlib
import json
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import (
    _timestamp, ensure_dialog_schema, register_native_v29_chat,
)

class V112Tests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder=Path(tmp.name)
        self.db=folder/'existing_s03.sqlite3'
        with sqlite3.connect(self.db) as db:
            db.execute('CREATE TABLE s03_items (id TEXT PRIMARY KEY, sha256 TEXT, text TEXT, ts TEXT)')
        mod=types.ModuleType('s03_memory')
        mod.DB=self.db
        previous=sys.modules.get('s03_memory')
        sys.modules['s03_memory']=mod
        self.addCleanup(lambda:sys.modules.pop('s03_memory',None) if previous is None
                        else sys.modules.__setitem__('s03_memory',previous))
        self.site=folder/'site'
        self.site.mkdir()
        (self.site/'index.html').write_text('<html><head></head><body>NOX</body></html>')
        (self.site/'chat.html').write_text('<html><head></head><body>Резонанс</body></html>')
        (self.site/'nox-chat.js').write_text('/* WEB source fixture, not a model */')
        nested=self.site/'pc'/'pages'/'cinema'
        nested.mkdir(parents=True)
        (nested/'index.html').write_text('<html><head></head><body>Кинотеатр</body></html>')
        self.app=FastAPI()
        @self.app.get('/api/nox/status')
        async def old_status():
            return {'model':'NOX PRIME 8B','ts':123}
        self.calls=[]
        self.record=True
        self.bulk_sse=''
        async def native(payload):
            self.calls.append(payload)
            q=payload['messages'][-1]['content']
            answer='Готов. Это проверенный ответ.'
            async def chunks():
                if self.bulk_sse=='coalesced':
                    # Two individually valid 160 KB SSE comment frames in
                    # ONE network read: aggregate >300 KB is not oversize.
                    yield ('data: '+json.dumps({'choices':[{'delta':{'content':answer}}]},ensure_ascii=False)+'\n'
                           + (':'+'h'*160000+'\n')*2)
                elif self.bulk_sse=='oversized':
                    yield 'data: '+'x'*300000+'\n'
                elif self.bulk_sse=='duplicate_done':
                    # First [DONE] is valid; a second terminal record must
                    # fail closed even when the original S03 proof exists.
                    yield ('data: '+json.dumps({'choices':[{'delta':{'content':answer}}]},
                          ensure_ascii=False)+'\n\ndata: [DONE]\n\n')
                else:
                    yield ('data: '+json.dumps({'choices':[{'delta':{'content':answer[:11]}}]},ensure_ascii=False)+'\n\n')
                    yield ('data: '+json.dumps({'choices':[{'delta':{'content':answer[11:]}}]},ensure_ascii=False)+'\n\n')
                if self.record:
                    from datetime import datetime,timezone
                    stamp=datetime.now(timezone.utc).isoformat()
                    with sqlite3.connect(self.db) as db:
                        db.execute('INSERT INTO s03_items VALUES(?,?,?,?)',(
                          'new-exchange-0001',hashlib.sha256((q+answer).encode()).hexdigest(),
                          'U:'+q+' A:'+answer,stamp))
                yield 'data: [DONE]\n\n'
            return StreamingResponse(chunks(),media_type='text/event-stream')
        register_native_v29_chat(self.app,{
          '_session_ok':lambda request:request.cookies.get('owner')=='yes',
          '_unauthorized':lambda:JSONResponse({'error':'AUTH'},status_code=401),
          '_proxy_completion':native,
          'nox_status':old_status,
        },site_dir=self.site)
        self.client=TestClient(self.app)
        self.addCleanup(self.client.close)
        self.cookie={'owner':'yes'}
        self.assertTrue(ensure_dialog_schema())

    def test_auth_is_essential(self):
        for url,method in [
            ('/api/nox/status','get'),
            ('/api/ui/capabilities','get'),
            ('/api/ui/memory/dialogs/status','get'),
            ('/api/ui/memory/dialogs','get'),
            ('/api/ui/memory/dialogs/create','post'),
            ('/api/nox/chat/stream','post'),
            ('/api/nox/stop','post'),
            ('/nox-web-v29/','get'),
            ('/nox-web-v29/native-owner.js','get'),
        ]:
            r=(self.client.post(url,json={}) if method=='post' else self.client.get(url))
            self.assertEqual(r.status_code,401,url)
        self.assertEqual(self.calls,[])

    def test_source_status_is_augmented_not_faked(self):
        r=self.client.get('/api/nox/status',cookies=self.cookie)
        self.assertEqual(r.status_code,200)
        data=r.json()
        self.assertEqual(data['ts'],123)
        self.assertEqual(data['primary_model'],'NOX PRIME 8B')
        self.assertEqual(data['backend'],'EXISTING_NATIVE_ONEHOST')
        self.assertTrue(data['native_p02_bound'])
        self.assertTrue(data['native_cognitive_memory_bound'])
        self.assertTrue(data['native_dialogs_ready'])
        self.assertTrue(self.client.get('/api/ui/memory/dialogs/status',cookies=self.cookie)
                        .json()['persistent_threads'])

    def test_stream_s03_and_owner_thread_roundtrip(self):
        create=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
               json={'title':'Привет NOX','confirmed':True})
        self.assertEqual(create.status_code,200,create.text)
        d=create.json()['dialog_id']
        self.assertRegex(d,r'^[0-9a-f]{32}$')
        r=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'message':'Привет NOX','dialog_id':d,'history':[]})
        self.assertEqual(r.status_code,200,r.text)
        frames=[json.loads(x) for x in r.text.splitlines() if x.strip()]
        self.assertEqual([x['type'] for x in frames],['preparing','start','delta','delta','done'])
        self.assertTrue(frames[-1]['saved'])
        self.assertTrue(frames[-1]['s03_integrated'])
        self.assertEqual(frames[-1]['dialog_id'],d)
        self.assertEqual(frames[-1]['exchange_id'],'new-exchange-0001')
        self.assertTrue(self.calls[-1]['_owner'])
        hist=self.client.get('/api/ui/memory/dialogs/history',
             cookies=self.cookie,params={'dialog_id':d}).json()
        self.assertEqual([x['role'] for x in hist['messages']],['user','assistant'])
        self.assertEqual(hist['messages'][0]['content'],'Привет NOX')
        self.assertEqual(hist['messages'][1]['content'],'Готов. Это проверенный ответ.')
        listed=self.client.get('/api/ui/memory/dialogs',cookies=self.cookie).json()
        self.assertEqual(listed['dialogs'][0]['dialog_id'],d)

    def test_coalesced_sse_transport_frames_preserve_native_s03_done(self):
        self.bulk_sse='coalesced'
        created=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'V165 SSE','confirmed':True}).json()
        r=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'message':'V165 coherent read', 'dialog_id':created['dialog_id']})
        self.assertEqual(r.status_code,200,r.text[:300])
        frames=[json.loads(x) for x in r.text.splitlines() if x.strip()]
        self.assertEqual([f['type'] for f in frames],['preparing','start','delta','done'])
        self.assertEqual(frames[-1]['exchange_id'],'new-exchange-0001')
        self.assertTrue(frames[-1]['s03_integrated'])
        self.assertEqual(''.join(f['text'] for f in frames if f['type']=='delta'),
                         'Готов. Это проверенный ответ.')

    def test_one_oversized_sse_frame_is_still_rejected(self):
        self.bulk_sse='oversized'
        self.record=False
        r=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'message':'oversized single frame'})
        frames=[json.loads(x) for x in r.text.splitlines() if x.strip()]
        self.assertEqual(frames[-1],{'type':'error','error':'HOLD_SSE_FRAME_LIMIT'})
        self.assertFalse(any(f.get('saved') for f in frames))

    def test_duplicate_upstream_sse_done_cannot_save_dialog_receipt(self):
        self.bulk_sse='duplicate_done'
        created=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'V166 terminal SSE','confirmed':True}).json()
        d=created['dialog_id']
        r=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'message':'upstream duplicate terminal','dialog_id':d})
        self.assertEqual(r.status_code,200,r.text[:300])
        frames=[json.loads(x) for x in r.text.splitlines() if x.strip()]
        self.assertEqual(frames[-1],{'type':'error','error':'HOLD_SSE_FRAME_AFTER_DONE'})
        self.assertFalse(any(x.get('type')=='done' or x.get('saved') for x in frames))
        history=self.client.get('/api/ui/memory/dialogs/history',cookies=self.cookie,
            params={'dialog_id':d}).json()
        self.assertEqual(history['messages'],[])

    def test_cross_dialog_id_is_rejected(self):
        before=len(self.calls)
        bad=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
          json={'message':'Атака','dialog_id':'f'*32})
        self.assertEqual(bad.status_code,409)
        self.assertEqual(len(self.calls),before)

    def test_no_fresh_s03_row_means_no_fake_done(self):
        self.record=False
        r=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
          json={'message':'Другой уникальный вопрос'})
        frames=[json.loads(x) for x in r.text.splitlines() if x.strip()]
        self.assertEqual(frames[-1]['type'],'error')
        self.assertEqual(frames[-1]['error'],'HOLD_S03_COMMIT_NOT_VERIFIED')
        self.assertFalse(any(x.get('saved') for x in frames))

    def test_dialog_revision_and_archive(self):
        created=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
          json={'title':'Вопрос','confirmed':True}).json()
        changed=self.client.post('/api/ui/memory/dialogs/update',cookies=self.cookie,
          json={'dialog_id':created['dialog_id'],'revision':created['revision'],
                'archived':True,'confirmed':True})
        self.assertTrue(changed.json()['archived'])
        duplicate=self.client.post('/api/ui/memory/dialogs/update',cookies=self.cookie,
          json={'dialog_id':created['dialog_id'],'revision':created['revision'],
                'archived':False,'confirmed':True})
        self.assertEqual(duplicate.status_code,409)

    def test_owner_only_static_html_bootstrap(self):
        ok=self.client.get('/nox-web-v29/chat.html',cookies=self.cookie)
        self.assertEqual(ok.status_code,200)
        self.assertIn('src="/nox-web-v29/native-owner.js"',ok.text)
        js=self.client.get('/nox-web-v29/native-owner.js',cookies=self.cookie)
        self.assertEqual(js.status_code,200)
        self.assertIn('NOX_NATIVE_OWNER = true',js.text)
        nested=self.client.get('/nox-web-v29/pc/pages/cinema/index.html',cookies=self.cookie)
        self.assertEqual(nested.status_code,200)
        self.assertIn('src="/nox-web-v29/native-owner.js"',nested.text)
        self.assertNotIn('src="./native-owner.js"',nested.text)

    def test_no_false_gpu_stop(self):
        r=self.client.post('/api/nox/stop',cookies=self.cookie,json={})
        self.assertEqual(r.status_code,409)
        self.assertNotIn('gpu_stop_verified',r.json())

    def test_s03_timestamp_guard(self):
        self.assertLess(_timestamp('2025-01-01T00:00:00Z'), _timestamp('2026-11-14T00:00:00Z'))

if __name__=='__main__':
    unittest.main()
