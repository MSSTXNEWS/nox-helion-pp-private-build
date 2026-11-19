"""V112 regression against fixture SQLite and synthetic SSE. Never a live NOX receipt."""
import asyncio
import hashlib
import httpx
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import (
    _sse_delta, _timestamp, ensure_dialog_schema, owner_admission_readback,
    owner_quiesce_admission, owner_resume_admission, register_native_v29_chat,
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
        self.admission_state=folder/'admission-state'
        self.admission_state.mkdir(mode=0o700)
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
        self.block_native=False
        self.native_started=threading.Event()
        self.stream_entered=None
        self.stream_release=None
        async def native(payload):
            self.calls.append(payload)
            q=payload['messages'][-1]['content']
            answer='Готов. Это проверенный ответ.'
            async def chunks():
                if self.block_native:
                    self.native_started.set()
                    await asyncio.Event().wait()
                    yield 'unreachable'
                if self.stream_entered is not None and self.stream_release is not None:
                    self.stream_entered.set()
                    await asyncio.to_thread(self.stream_release.wait,8)
                if self.bulk_sse=='coalesced':
                    # Two individually valid 160 KB SSE comment frames in
                    # ONE network read: aggregate >300 KB is not oversize.
                    yield ('data: '+json.dumps({'choices':[{'delta':{'content':answer}}]},ensure_ascii=False)+'\n'
                           + (':'+'h'*160000+'\n')*2)
                elif self.bulk_sse=='oversized':
                    yield 'data: '+'x'*300000+'\n'
                elif self.bulk_sse=='unterminated_postdone':
                    # Terminal DONE plus a nonempty, un-terminated extra SSE row.
                    yield ('data: '+json.dumps({'choices':[{'delta':{'content':answer}}]},
                           ensure_ascii=False)+'\n\n')
                elif self.bulk_sse=='duplicate_done':
                    # First [DONE] is valid; a second terminal record must
                    # fail closed even when the original S03 proof exists.
                    yield ('data: '+json.dumps({'choices':[{'delta':{'content':answer}}]},
                          ensure_ascii=False)+'\n\ndata: [DONE]\n\n')
                elif self.bulk_sse=='multi_choice_truncated':
                    # Old parser emitted choice 0's text without examining
                    # the incomplete choice 1 in this same frame.
                    yield ('data: '+json.dumps({'choices':[
                           {'index':0,'delta':{'content':answer}},
                           {'index':1,'delta':{},'finish_reason':'length'}]},
                           ensure_ascii=False)+'\n\n')
                else:
                    yield ('data: '+json.dumps({'choices':[{'delta':{'content':answer[:11]}}]},ensure_ascii=False)+'\n\n')
                    yield ('data: '+json.dumps({'choices':[{'delta':{'content':answer[11:]}}]},ensure_ascii=False)+'\n\n')
                if self.bulk_sse=='finish_reason_length_after_delta':
                    # OpenAI-compatible finish_reason=length is a truncated
                    # generation, even if native fixture S03 later matches.
                    yield 'data: '+json.dumps({'choices':[{'delta':{},'finish_reason':'length'}]})+'\n\n'
                if self.bulk_sse=='malformed_data_after_delta':
                    # Previously ignored broken model data allowed false S03 done.
                    yield 'data: {broken-json\n\n'
                if self.bulk_sse=='upstream_error_after_delta':
                    # A model-side error after valid deltas is terminal even
                    # when a matching fixture S03 row is present.
                    yield 'data: '+json.dumps({'error':{'message':'fixture inference failed'}})+'\n\n'
                if self.bulk_sse=='invalid_choice_after_delta':
                    yield 'data: '+json.dumps({'choices':[{'delta':42}]})+'\n\n'
                if self.record:
                    from datetime import datetime,timezone
                    stamp=datetime.now(timezone.utc).isoformat()
                    with sqlite3.connect(self.db) as db:
                        db.execute('INSERT INTO s03_items VALUES(?,?,?,?)',(
                          'new-exchange-0001',hashlib.sha256((q+answer).encode()).hexdigest(),
                          'U:'+q+' A:'+answer,stamp))
                if self.bulk_sse=='invalid_utf8_comment':
                    # Original model answer and S03 fixture proof exist, but
                    # upstream sends invalid UTF-8 in a syntactically ignorable comment.
                    yield b': \xff\n\n'
                yield ('data: [DONE]\n\ndata: [DONE]' if self.bulk_sse=='unterminated_postdone'
                       else 'data: [DONE]\n\n')
                if self.bulk_sse=='trailing_utf8_partial':
                    # Incremental UTF-8 decoder must be finalized at EOF.
                    yield b'\xe2\x82'
            return StreamingResponse(chunks(),media_type='text/event-stream')
        register_native_v29_chat(self.app,{
          '_session_ok':lambda request:request.cookies.get('owner')=='yes',
          '_unauthorized':lambda:JSONResponse({'error':'AUTH'},status_code=401),
          '_proxy_completion':native,
          'nox_status':old_status,
        },site_dir=self.site,_admission_state_dir=self.admission_state,
          _admission_owner_uid=os.getuid())
        self.client=TestClient(self.app)
        self.addCleanup(self.client.close)
        self.cookie={'owner':'yes'}
        self.assertTrue(ensure_dialog_schema())

    def test_original_s03_db_context_closes_commits_and_rolls_back(self):
        # sqlite3.Connection is NOT itself a closing context manager.
        # Repeated owner WEB streams must not leak a SQLite file descriptor.
        from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import _db
        with _db(True) as writer:
            writer.execute('INSERT INTO s03_items(id,sha256,text,ts) VALUES(?,?,?,?)',
                           ('v112-db-success','a'*64,'committed record','2026-11-15'))
        with self.assertRaises(sqlite3.ProgrammingError):
            writer.execute('SELECT 1')
        with _db() as reader:
            found=reader.execute('SELECT text FROM s03_items WHERE id=?',
                                 ('v112-db-success',)).fetchone()
            self.assertEqual(found['text'],'committed record')
        with self.assertRaises(sqlite3.ProgrammingError):
            reader.execute('SELECT 1')
        with self.assertRaisesRegex(RuntimeError,'forced fixture rollback'):
            with _db(True) as failed:
                failed.execute('INSERT INTO s03_items(id,sha256,text,ts) VALUES(?,?,?,?)',
                               ('v112-db-rollback','b'*64,'must not persist','2026-11-15'))
                raise RuntimeError('forced fixture rollback')
        with self.assertRaises(sqlite3.ProgrammingError):
            failed.execute('SELECT 1')
        with _db() as check:
            self.assertIsNone(check.execute('SELECT id FROM s03_items WHERE id=?',
                                            ('v112-db-rollback',)).fetchone())

    def test_s03_exchange_receipt_collision_fails_closed(self):
        # The original OneHost dialog must never accept old text as saved=True
        # merely because an S03 exchange_id already has two rows.
        from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import _db, _save_exchange
        created=self.client.post('/api/ui/memory/dialogs/create',
                                 json={'confirmed':True,'title':'Receipt collision'},
                                 cookies=self.cookie)
        self.assertEqual(created.status_code,200)
        dialog_id=created.json()['dialog_id']
        exchange='s03-fixture-receipt-collision'
        self.assertTrue(_save_exchange(dialog_id,'old question','old answer',exchange))
        with _db() as db:
            before=db.execute('SELECT revision FROM nox_v29_dialogs WHERE dialog_id=?',
                              (dialog_id,)).fetchone()['revision']
        self.assertFalse(_save_exchange(dialog_id,'new question','new answer',exchange))
        # Identical retry is allowed without an artificial new revision.
        self.assertTrue(_save_exchange(dialog_id,'old question','old answer',exchange))
        with _db() as db:
            rows=db.execute('SELECT role,content FROM nox_v29_dialog_messages '
                            'WHERE dialog_id=? AND exchange_id=? ORDER BY role',
                            (dialog_id,exchange)).fetchall()
            revision=db.execute('SELECT revision FROM nox_v29_dialogs WHERE dialog_id=?',
                                (dialog_id,)).fetchone()['revision']
        self.assertEqual([(r['role'],r['content']) for r in rows],
                         [('assistant','old answer'),('user','old question')])
        self.assertEqual(revision,before)
        partial='s03-fixture-partial'
        with _db(True) as db:
            db.execute('INSERT INTO nox_v29_dialog_messages '
                       '(dialog_id,exchange_id,role,content,ts) VALUES(?,?,?,?,?)',
                       (dialog_id,partial,'user','orphan message','2026-11-15'))
        self.assertFalse(_save_exchange(dialog_id,'orphan message','answer',partial))
        with _db() as db:
            partial_rows=db.execute('SELECT role,content FROM nox_v29_dialog_messages '
                                    'WHERE dialog_id=? AND exchange_id=?',
                                    (dialog_id,partial)).fetchall()
        self.assertEqual(len(partial_rows),1)
        self.assertEqual(partial_rows[0]['role'],'user')

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

    def test_durable_global_fence_rejects_new_chat_and_other_admissions(self):
        store=self.app.state._nox_v112_admission_store
        from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import _AdmissionStore
        # A second app worker's independently created store sees the same durable fence.
        other_worker_store=_AdmissionStore(self.admission_state,owner_uid=os.getuid())
        epoch=other_worker_store.set_fence('7015284458')
        chat=self.client.post('/api/nox/chat/stream',cookies=self.cookie,json={})
        status=self.client.get('/api/nox/status',cookies=self.cookie)
        self.assertEqual(chat.status_code,503,chat.text)
        self.assertEqual(chat.json()['reason'],'HOLD_ADMISSION_FENCED')
        self.assertEqual(status.status_code,503,status.text)
        self.assertEqual(status.json()['reason'],'HOLD_ADMISSION_FENCED')
        self.assertEqual(self.calls,[])
        with self.assertRaisesRegex(RuntimeError,'HOLD_ADMISSION_OWNER_REQUIRED'):
            owner_admission_readback('7015284458',_store=store)
        with mock.patch('nox_runpod.teacher_mesh.v112.native_v29_full_bridge.os.geteuid',
                        return_value=0):
            receipt=owner_admission_readback('7015284458',_store=store)
            with self.assertRaisesRegex(RuntimeError,'HOLD_ADMISSION_FENCE_OWNED'):
                owner_admission_readback('7015284459',_store=store)
        self.assertTrue(receipt['fence_active'])
        self.assertEqual(receipt['fence_epoch'],epoch)
        self.assertEqual(receipt['in_flight_count'],0)
        self.assertEqual(receipt['active_stream_count'],0)
        self.assertEqual(receipt['status'],'QUIESCED')
        # Owner STOP remains an authenticated control path and does not create an admission.
        stop=self.client.post('/api/nox/stop',cookies=self.cookie,json={})
        self.assertEqual(stop.status_code,409)

    def test_quiesce_waits_for_stream_drain_and_retains_fence_on_timeout(self):
        store=self.app.state._nox_v112_admission_store
        self.stream_entered=threading.Event()
        self.stream_release=threading.Event()
        dialog=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'Fence drain','confirmed':True}).json()['dialog_id']
        stream_result={}
        stream_thread=threading.Thread(target=lambda:stream_result.setdefault('response',
            self.client.post('/api/nox/chat/stream',cookies=self.cookie,
                json={'message':'hold generation until released','dialog_id':dialog})),daemon=True)
        stream_thread.start()
        self.assertTrue(self.stream_entered.wait(3),'stream never entered its pinned upstream fixture')
        quiesce_result={}
        def quiesce():
            with mock.patch('nox_runpod.teacher_mesh.v112.native_v29_full_bridge.os.geteuid',
                            return_value=0):
                try:
                    quiesce_result['receipt']=owner_quiesce_admission(
                        '7015284459',timeout_seconds=4,_store=store)
                except Exception as exc:
                    quiesce_result['error']=exc
        quiesce_thread=threading.Thread(target=quiesce,daemon=True)
        quiesce_thread.start()
        deadline=time.monotonic()+2
        snapshot=None
        while time.monotonic()<deadline:
            snapshot=store.snapshot('7015284459')
            if snapshot['fence_active'] and snapshot['in_flight_count']:
                break
            time.sleep(.02)
        self.assertIsNotNone(snapshot)
        self.assertTrue(snapshot['fence_active'],
            f'snapshot={snapshot},quiesce={quiesce_result},alive={quiesce_thread.is_alive()}')
        self.assertEqual(snapshot['in_flight_count'],1)
        self.assertEqual(snapshot['active_stream_count'],1)
        blocked=self.client.get('/api/nox/status',cookies=self.cookie)
        self.assertEqual(blocked.status_code,503,blocked.text)
        self.assertTrue(quiesce_thread.is_alive(),'quiesce returned before the stream drained')
        self.stream_release.set()
        stream_thread.join(5); quiesce_thread.join(5)
        self.assertFalse(stream_thread.is_alive())
        self.assertFalse(quiesce_thread.is_alive())
        self.assertNotIn('error',quiesce_result,repr(quiesce_result.get('error')))
        receipt=quiesce_result['receipt']
        self.assertEqual(receipt['status'],'QUIESCED')
        self.assertEqual(receipt['zero_readbacks'],2)
        self.assertEqual(receipt['in_flight_count'],0)
        self.assertEqual(receipt['active_stream_count'],0)
        self.assertEqual(stream_result['response'].status_code,200)
        independent=owner_admission_readback
        with mock.patch('nox_runpod.teacher_mesh.v112.native_v29_full_bridge.os.geteuid',
                        return_value=0):
            readback=independent('7015284459',_store=store)
            resumed=owner_resume_admission('7015284459',receipt['fence_epoch'],_store=store)
        self.assertEqual(readback['status'],'QUIESCED')
        self.assertFalse(resumed['fence_active'])
        self.assertEqual(resumed['status'],'OPEN')

    def test_corrupt_or_symlink_state_fails_closed(self):
        from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import ADMISSION_FILE
        (self.admission_state/ADMISSION_FILE).symlink_to('/etc/passwd')
        response=self.client.get('/api/nox/status',cookies=self.cookie)
        self.assertEqual(response.status_code,503,response.text)
        self.assertEqual(response.json()['reason'],'HOLD_ADMISSION_STATE_UNAVAILABLE')
        self.assertEqual(self.calls,[])

    def test_stream_lease_write_failure_aborts_before_native_generation(self):
        store=self.app.state._nox_v112_admission_store
        dialog=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'Lease write failure','confirmed':True}).json()['dialog_id']
        with mock.patch.object(store,'mark_stream',side_effect=OSError('fixture state write failure')):
            response=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
                json={'message':'must not reach native model','dialog_id':dialog})
        self.assertEqual(response.status_code,503,response.text)
        self.assertEqual(response.json()['reason'],'HOLD_ADMISSION_STATE_UNAVAILABLE')
        self.assertEqual(self.calls,[],'native completion must not start after stream admission state failed')

    def test_quiesce_timeout_keeps_fence_until_exact_owner_resume(self):
        store=self.app.state._nox_v112_admission_store
        token=store.admit()
        with mock.patch('nox_runpod.teacher_mesh.v112.native_v29_full_bridge.os.geteuid',
                        return_value=0):
            with self.assertRaisesRegex(RuntimeError,'HOLD_ADMISSION_DRAIN_TIMEOUT'):
                owner_quiesce_admission('7015284460',timeout_seconds=.15,_store=store)
            store.release(token)
            receipt=owner_admission_readback('7015284460',_store=store)
            with self.assertRaisesRegex(RuntimeError,'HOLD_ADMISSION_FENCE_CHANGED'):
                owner_resume_admission('7015284460','0'*32,_store=store)
            opened=owner_resume_admission('7015284460',receipt['fence_epoch'],_store=store)
        self.assertTrue(receipt['fence_active'])
        self.assertEqual(receipt['in_flight_count'],0)
        self.assertEqual(opened['status'],'OPEN')

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
        dialog=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'SSE size limit','confirmed':True}).json()['dialog_id']
        r=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'message':'oversized single frame','dialog_id':dialog})
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

    def test_unterminated_postdone_tail_never_yields_false_s03_receipt(self):
        self.bulk_sse='unterminated_postdone'
        created=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'V167 dangling SSE tail','confirmed':True}).json()
        d=created['dialog_id']
        r=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'message':'unterminated after terminal','dialog_id':d})
        frames=[json.loads(x) for x in r.text.splitlines() if x.strip()]
        self.assertEqual(frames[-1],{'type':'error','error':'HOLD_SSE_FRAME_AFTER_DONE'})
        self.assertFalse(any(x.get('type')=='done' or x.get('saved') for x in frames))
        history=self.client.get('/api/ui/memory/dialogs/history',cookies=self.cookie,
            params={'dialog_id':d}).json()
        self.assertEqual(history['messages'],[])

    def test_upstream_model_error_must_not_claim_durable_s03_done(self):
        self.bulk_sse='upstream_error_after_delta'
        created=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'V168 upstream failure','confirmed':True}).json()
        d=created['dialog_id']
        r=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'message':'model error after partial answer','dialog_id':d})
        frames=[json.loads(x) for x in r.text.splitlines() if x.strip()]
        self.assertEqual(frames[-1],{'type':'error','error':'HOLD_UPSTREAM_SSE_ERROR'})
        self.assertFalse(any(x.get('type')=='done' or x.get('saved') for x in frames))
        hist=self.client.get('/api/ui/memory/dialogs/history',cookies=self.cookie,
            params={'dialog_id':d}).json()
        self.assertEqual(hist['messages'],[])

    def test_malformed_upstream_sse_cannot_claim_s03_saved(self):
        self.bulk_sse='malformed_data_after_delta'
        created=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'V169 malformed upstream','confirmed':True}).json()
        d=created['dialog_id']
        r=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'message':'malformed model data after answer','dialog_id':d})
        frames=[json.loads(x) for x in r.text.splitlines() if x.strip()]
        self.assertEqual(frames[-1],{'type':'error','error':'HOLD_UPSTREAM_SSE_MALFORMED'})
        self.assertFalse(any(x.get('type')=='done' or x.get('saved') for x in frames))
        history=self.client.get('/api/ui/memory/dialogs/history',cookies=self.cookie,
            params={'dialog_id':d}).json()
        self.assertEqual(history['messages'],[])


    def test_truncated_upstream_finish_reason_never_certifies_s03_saved(self):
        self.bulk_sse='finish_reason_length_after_delta'
        created=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'V171 truncated upstream','confirmed':True}).json()
        dialog_id=created['dialog_id']
        reply=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'message':'finish reason length after delta','dialog_id':dialog_id})
        frames=[json.loads(line) for line in reply.text.splitlines() if line.strip()]
        self.assertEqual(frames[-1],{'type':'error','error':'HOLD_UPSTREAM_FINISH_REASON'})
        self.assertTrue(any(frame.get('type')=='delta' for frame in frames))
        self.assertFalse(any(frame.get('type')=='done' or frame.get('saved') for frame in frames))
        history=self.client.get('/api/ui/memory/dialogs/history',cookies=self.cookie,
            params={'dialog_id':dialog_id}).json()
        self.assertEqual(history['messages'],[])

    def _assert_invalid_utf8_cannot_claim_durable_s03_success(self, mode):
        # One independently initialized fixture DB per test. A loop of two
        # requests shared a fixed test exchange_id and collided on SQLite PK.
        self.bulk_sse=mode
        created=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'V170 UTF8 corruption '+mode,'confirmed':True}).json()
        dialog_id=created['dialog_id']
        reply=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'message':'unicode integrity '+mode,'dialog_id':dialog_id})
        frames=[json.loads(line) for line in reply.text.splitlines() if line.strip()]
        self.assertEqual(frames[-1],{'type':'error','error':'HOLD_UPSTREAM_SSE_UTF8_INVALID'})
        self.assertFalse(any(f.get('type')=='done' or f.get('saved') for f in frames))
        hist=self.client.get('/api/ui/memory/dialogs/history',cookies=self.cookie,
            params={'dialog_id':dialog_id}).json()
        self.assertEqual(hist['messages'],[])

    def test_invalid_utf8_comment_fails_closed_even_with_s03_fixture(self):
        self._assert_invalid_utf8_cannot_claim_durable_s03_success('invalid_utf8_comment')

    def test_trailing_incomplete_utf8_fails_closed_even_with_s03_fixture(self):
        self._assert_invalid_utf8_cannot_claim_durable_s03_success('trailing_utf8_partial')

    def test_v177_multi_choice_sse_cannot_certify_s03(self):
        suspect={'choices':[
            {'index':0,'delta':{'content':'complete'}},
            {'index':1,'delta':{},'finish_reason':'length'}]}
        self.assertEqual(_sse_delta('data: '+json.dumps(suspect)),('malformed',''))
        self.assertEqual(_sse_delta('data: '+json.dumps(
            {'choices':[{'delta':{'content':'valid'}}]})),('delta','valid'))
        self.bulk_sse='multi_choice_truncated'
        created=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
                                 json={'title':'V177 single model response','confirmed':True})
        self.assertEqual(created.status_code,200,created.text)
        dialog_id=created.json()['dialog_id']
        reply=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
                               json={'message':'one reply one receipt','dialog_id':dialog_id})
        frames=[json.loads(line) for line in reply.text.splitlines() if line.strip()]
        self.assertEqual(frames[-1],{'type':'error','error':'HOLD_UPSTREAM_SSE_MALFORMED'})
        self.assertFalse(any(f.get('type')=='done' or f.get('saved') for f in frames))
        history=self.client.get('/api/ui/memory/dialogs/history',cookies=self.cookie,
                                params={'dialog_id':dialog_id})
        self.assertEqual(history.json()['messages'],[])

    def test_v176_malformed_choice_envelope_fails_closed(self):
        bad=({'choices':'invalid'}, {'choices':None}, {'choices':[None]},
             {'choices':[{'delta':42}]},
             {'choices':[{'delta':{'content':['not a string']}}]},
             {'status':'unrecognized model error'})
        for obj in bad:
            with self.subTest(obj=obj):
                self.assertEqual(_sse_delta('data: '+json.dumps(obj)),('malformed',''))
        for good in ({'choices':[],'usage':{'completion_tokens':3}},
                     {'usage':{'completion_tokens':3}},
                     {'choices':[{'delta':{},'finish_reason':'stop'}]}):
            self.assertEqual(_sse_delta('data: '+json.dumps(good)),('',''))

    def test_v176_invalid_choices_does_not_save_thread(self):
        self.bulk_sse='invalid_choice_after_delta'
        dialog=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'corrupt choices','confirmed':True}).json()['dialog_id']
        reply=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'message':'bad model stream','dialog_id':dialog})
        frames=[json.loads(x) for x in reply.text.splitlines() if x.strip()]
        self.assertTrue(any(f['type']=='delta' for f in frames))
        self.assertEqual(frames[-1],{'type':'error','error':'HOLD_UPSTREAM_SSE_MALFORMED'})
        self.assertFalse(any(f.get('type')=='done' or f.get('saved') for f in frames))
        history=self.client.get('/api/ui/memory/dialogs/history',cookies=self.cookie,
            params={'dialog_id':dialog}).json()
        self.assertEqual(history['messages'],[])

    def test_cross_dialog_id_is_rejected(self):
        before=len(self.calls)
        bad=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
          json={'message':'Атака','dialog_id':'f'*32})
        self.assertEqual(bad.status_code,409)
        self.assertEqual(len(self.calls),before)

    def test_dialog_inference_uses_durable_thread_not_browser_history(self):
        from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import _save_exchange
        created=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'Рабочий контекст','confirmed':True}).json()
        other=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'Другой разговор','confirmed':True}).json()
        dialog=created['dialog_id']
        self.assertTrue(_save_exchange(dialog,'Проект называется NOX.',
                                       'Продолжим работу над NOX.','context-seed'))
        self.assertTrue(_save_exchange(other['dialog_id'],'Другой проект.',
                                       'Чужой контекст.','other-context'))
        response=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'dialog_id':dialog,'message':'Как он называется?',
                  'history':[{'role':'assistant','content':'Подменённый ответ.'}]})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.calls[-1]['messages'],[
            {'role':'user','content':'Проект называется NOX.'},
            {'role':'assistant','content':'Продолжим работу над NOX.'},
            {'role':'user','content':'Как он называется?'}])
        self.assertEqual(json.loads(response.text.splitlines()[-1])['type'],'done')

    def test_dialog_context_holds_when_over_24_messages(self):
        from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import (
            _dialog_context,_save_exchange,
        )
        dialog=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'Переполнение контекста','confirmed':True}).json()['dialog_id']
        for index in range(13):
            self.assertTrue(_save_exchange(dialog,f'Вопрос {index}',f'Ответ {index}',
                                          f'overflow-{index}'))
        issue,history=_dialog_context(dialog)
        self.assertEqual(issue,'HOLD_HISTORY_LIMIT')
        self.assertEqual(history,[])

    def test_dialog_context_preserves_complete_pair_order_within_limit(self):
        from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import (
            _dialog_context,_save_exchange,
        )
        dialog=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'Контекст в лимите','confirmed':True}).json()['dialog_id']
        for index in range(12):
            self.assertTrue(_save_exchange(dialog,f'Вопрос {index}',f'Ответ {index}',
                                          f'within-limit-{index}'))
        issue,history=_dialog_context(dialog)
        self.assertIsNone(issue)
        self.assertEqual(len(history),24)
        self.assertEqual(history[0],{'role':'user','content':'Вопрос 0'})
        self.assertEqual(history[-1],{'role':'assistant','content':'Ответ 11'})
        self.assertEqual(
            [row['content'] for row in history],
            [text for index in range(12)
             for text in (f'Вопрос {index}',f'Ответ {index}')])

    def test_dialog_context_holds_incomplete_pair_within_message_limit(self):
        from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import (
            _db,_dialog_context,_save_exchange,
        )
        dialog=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'Неполная пара','confirmed':True}).json()['dialog_id']
        for index in range(11):
            self.assertTrue(_save_exchange(dialog,f'Вопрос {index}',f'Ответ {index}',
                                          f'complete-{index}'))
        with _db(True) as db:
            db.execute('INSERT INTO nox_v29_dialog_messages '
                       '(dialog_id,exchange_id,role,content,ts) VALUES(?,?,?,?,?)',
                       (dialog,'orphan','assistant','Незавершённая пара','2026-11-15'))
        issue,history=_dialog_context(dialog)
        self.assertEqual(issue,'HOLD_HISTORY_PAIR_INCOMPLETE')
        self.assertEqual(history,[])

    def test_dialog_context_holds_over_byte_budget(self):
        from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import (
            _dialog_context,_save_exchange,
        )
        dialog=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'Байтовый лимит','confirmed':True}).json()['dialog_id']
        for index in range(2):
            self.assertTrue(_save_exchange(dialog,'😀'*8000,'Ответ '+('😀'*8000),
                                          f'large-{index}'))
        issue,history=_dialog_context(dialog)
        self.assertEqual(issue,'HOLD_HISTORY_SIZE')
        self.assertEqual(history,[])

    def test_dialog_context_keeps_owner_and_archive_guards(self):
        from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import _db
        dialog=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'Владелец','confirmed':True}).json()['dialog_id']
        with _db(True) as db:
            db.execute('UPDATE nox_v29_dialogs SET archived=1 WHERE dialog_id=?',(dialog,))
        response=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'dialog_id':dialog,'message':'Не начинать вывод'})
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json()['error'],'HOLD_DIALOG_ARCHIVED')
        with _db(True) as db:
            db.execute('UPDATE nox_v29_dialogs SET archived=0,owner=? WHERE dialog_id=?',
                       ('different-owner',dialog))
        response=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'dialog_id':dialog,'message':'Не читать чужой контекст'})
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json()['error'],'HOLD_DIALOG_SCOPE_NOT_BOUND')
        self.assertEqual(self.calls,[])

    def test_no_fresh_s03_row_means_no_fake_done(self):
        self.record=False
        dialog=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'Missing S03 receipt','confirmed':True}).json()['dialog_id']
        r=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
          json={'message':'Другой уникальный вопрос','dialog_id':dialog})
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
        self.assertEqual(r.json()['status'],'HOLD')
        self.assertEqual(r.json()['gpu_stop_verified'],False)

    def test_parallel_stop_mismatch_cannot_cancel_active_attempt(self):
        asyncio.run(self._parallel_stop_mismatch_scenario())

    async def _parallel_stop_mismatch_scenario(self):
        transport=httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport,base_url='http://test',
                                     cookies=self.cookie) as client:
            dialog=(await client.post('/api/ui/memory/dialogs/create',
                json={'title':'Attempt-scoped STOP parallel','confirmed':True})).json()['dialog_id']
            attempt_a='a'*32
            attempt_b='b'*32
            self.block_native=True
            active=asyncio.create_task(client.post('/api/nox/chat/stream',
                json={'message':'Active attempt A','dialog_id':dialog,'attempt_id':attempt_a}))
            self.assertTrue(await asyncio.to_thread(self.native_started.wait,2),
                            'A must reach the blocked native iterator')
            parallel=await client.post('/api/nox/chat/stream',
                json={'message':'Parallel attempt B','dialog_id':dialog,'attempt_id':attempt_b})
            self.assertEqual(parallel.status_code,409)
            self.assertEqual(parallel.json()['error'],'HOLD_ACTIVE_SESSION_STREAM')
            mismatch=await client.post('/api/nox/stop',json={'attempt_id':attempt_b})
            self.assertEqual(mismatch.status_code,409)
            self.assertEqual(mismatch.json()['reason'],'HOLD_STOP_ATTEMPT_MISMATCH')
            self.assertNotIn('stream_cancellation_signalled',mismatch.json())
            await asyncio.sleep(.05)
            self.assertFalse(active.done(),'B STOP must leave A active')
            accepted=await client.post('/api/nox/stop',json={'attempt_id':attempt_a})
            self.assertEqual(accepted.status_code,200)
            self.assertEqual(accepted.json()['attempt_id'],attempt_a)
            self.assertTrue(accepted.json()['stream_cancellation_signalled'])
            response=await asyncio.wait_for(active,2)
            frames=[json.loads(x) for x in response.text.splitlines() if x.strip()]
            self.assertEqual(frames[-1]['error'],'STREAM_STOP_REQUESTED')
            self.assertEqual(frames[-1]['attempt_id'],attempt_a)
            self.assertNotIn('done',[x['type'] for x in frames])

    def test_late_stop_for_completed_attempt_cannot_cancel_next_stream(self):
        asyncio.run(self._late_stop_scenario())

    async def _late_stop_scenario(self):
        transport=httpx.ASGITransport(app=self.app)
        async with httpx.AsyncClient(transport=transport,base_url='http://test',
                                     cookies=self.cookie) as client:
            dialog=(await client.post('/api/ui/memory/dialogs/create',
                json={'title':'Attempt-scoped STOP late','confirmed':True})).json()['dialog_id']
            old_attempt='c'*32
            response=await client.post('/api/nox/chat/stream',json={
                'message':'Completed attempt C','dialog_id':dialog,'attempt_id':old_attempt})
            self.assertEqual(response.status_code,200)
            frames=[json.loads(x) for x in response.text.splitlines() if x.strip()]
            self.assertEqual(frames[-1]['type'],'done')
            self.assertEqual(frames[-1]['attempt_id'],old_attempt)

            next_attempt='d'*32
            next_prompt='Next active attempt D unique'
            self.block_native=True
            self.native_started.clear()
            active=asyncio.create_task(client.post('/api/nox/chat/stream',json={
                'message':next_prompt,'dialog_id':dialog,'attempt_id':next_attempt}))
            self.assertTrue(await asyncio.to_thread(self.native_started.wait,2),
                            'D must reach the blocked native iterator')
            late=await client.post('/api/nox/stop',json={'attempt_id':old_attempt})
            self.assertEqual(late.status_code,409)
            self.assertEqual(late.json()['reason'],'HOLD_STOP_ATTEMPT_MISMATCH')
            await asyncio.sleep(.05)
            self.assertFalse(active.done(),'late C STOP must leave D active')
            accepted=await client.post('/api/nox/stop',json={'attempt_id':next_attempt})
            self.assertEqual(accepted.status_code,200)
            self.assertEqual(accepted.json()['attempt_id'],next_attempt)
            stopped=await asyncio.wait_for(active,2)
            stopped_frames=[json.loads(x) for x in stopped.text.splitlines() if x.strip()]
            self.assertEqual(stopped_frames[-1]['error'],'STREAM_STOP_REQUESTED')
            self.assertEqual(stopped_frames[-1]['attempt_id'],next_attempt)
            with sqlite3.connect(self.db) as db:
                written=db.execute('SELECT 1 FROM nox_v29_dialog_messages '
                                   'WHERE dialog_id=? AND content=? LIMIT 1',
                                   (dialog,next_prompt)).fetchone()
            self.assertIsNone(written,'stopped attempt must bypass the S03 write path')

    def test_s03_timestamp_guard(self):
        self.assertLess(_timestamp('2025-01-01T00:00:00Z'), _timestamp('2026-11-14T00:00:00Z'))

if __name__=='__main__':
    unittest.main()
