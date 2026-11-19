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
    _sse_delta, _timestamp, ensure_dialog_schema, register_native_v29_chat,
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
        self.context_nonce=None
        async def native(payload):
            self.calls.append(payload)
            messages=payload['messages']
            q=messages[-1]['content']
            answer='Готов. Это проверенный ответ.'
            if self.context_nonce:
                nonce=self.context_nonce
                first_q='first exact prompt '+nonce
                first_a='first exchange stores nonce '+nonce
                if q==first_q:
                    answer=first_a
                elif q=='second exact prompt':
                    exact_first_pair=[
                        {'role':'user','content':first_q},
                        {'role':'assistant','content':first_a},
                    ]
                    # The nonce is emitted only when the complete first pair
                    # is present immediately before the second prompt.
                    answer=('recovered nonce '+nonce
                            if messages[-3:-1]==exact_first_pair
                            else 'MISSING_CONTEXT')
            async def chunks():
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
                          'fixture-memory-'+str(len(self.calls)).zfill(4),
                          hashlib.sha256((q+answer).encode()).hexdigest(),
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
        },site_dir=self.site)
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

    def test_owner_dialog_exchange_receipt_collision_fails_closed(self):
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
            ('/api/ui/memory/dialogs/exchange-readback','post'),
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

    def test_stream_owner_dialog_receipt_and_thread_roundtrip(self):
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
        # Legacy wire field remains for UI compatibility; only these dialog fields prove persistence.
        self.assertFalse(frames[-1]['s03_integrated'])
        self.assertTrue(frames[-1]['owner_dialog_saved'])
        self.assertFalse(frames[-1]['canonical_s03_write_verified'])
        self.assertEqual(frames[-1]['dialog_id'],d)
        for key in ('turn_id','receipt_id','lease_epoch','exchange_id'):
            self.assertRegex(frames[-1][key],r'^[a-f0-9]{32}$')
        self.assertEqual(frames[-1]['writer'],'V112_OWNER_DIALOG_WRITER')
        self.assertRegex(frames[-1]['receipt_sha256'],r'^[a-f0-9]{64}$')
        self.assertTrue(self.calls[-1]['_owner'])
        hist=self.client.get('/api/ui/memory/dialogs/history',
             cookies=self.cookie,params={'dialog_id':d}).json()
        self.assertEqual(hist['store_scope'],'OWNER_DIALOG_TABLES_ONLY')
        self.assertFalse(hist['canonical_s03_readback_verified'])
        self.assertEqual([x['role'] for x in hist['messages']],['user','assistant'])
        self.assertEqual(hist['messages'][0]['content'],'Привет NOX')
        self.assertEqual(hist['messages'][1]['content'],'Готов. Это проверенный ответ.')
        proof=self.client.post('/api/ui/memory/dialogs/exchange-readback',cookies=self.cookie,
            json={key:frames[-1][key] for key in ('dialog_id','turn_id','receipt_id','lease_epoch')})
        self.assertEqual(proof.status_code,200,proof.text)
        self.assertEqual(proof.json()['messages'],[
            {'role':'user','content':'Привет NOX','exchange_id':frames[-1]['exchange_id']},
            {'role':'assistant','content':'Готов. Это проверенный ответ.','exchange_id':frames[-1]['exchange_id']}])
        self.assertTrue(proof.json()['durable']);self.assertTrue(proof.json()['verified'])
        self.assertEqual(proof.json()['store_scope'],'OWNER_DIALOG_TABLES_ONLY')
        self.assertFalse(proof.json()['canonical_s03_verified'])
        listed=self.client.get('/api/ui/memory/dialogs',cookies=self.cookie).json()
        self.assertEqual(listed['dialogs'][0]['dialog_id'],d)

    def test_fixture_two_sequential_turns_have_distinct_receipts_and_exact_readbacks(self):
        dialog=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'Two turn source fixture','confirmed':True}).json()['dialog_id']
        nonce='NOX-3A02-SAVED-TURN-7f83c'
        self.context_nonce=nonce
        prompts=('first exact prompt '+nonce,'second exact prompt')
        expected_answers=('first exchange stores nonce '+nonce,'recovered nonce '+nonce)
        receipts=[];expected=[]
        model_messages=[]
        for prompt_index,prompt in enumerate(prompts):
            model_messages.append({'role':'user','content':prompt})
            response=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
                json={'message':prompt,'dialog_id':dialog,'history':[]})
            self.assertEqual(response.status_code,200,response.text[:200])
            # The next inference must receive the durable prior pair, not browser history.
            self.assertEqual(self.calls[-1]['messages'],model_messages)
            frames=[json.loads(line) for line in response.text.splitlines() if line.strip()]
            done=frames[-1]
            self.assertEqual(done['type'],'done')
            receipt={key:done[key] for key in ('dialog_id','turn_id','receipt_id','lease_epoch')}
            proof=self.client.post('/api/ui/memory/dialogs/exchange-readback',cookies=self.cookie,json=receipt)
            self.assertEqual(proof.status_code,200,proof.text)
            messages=proof.json()['messages']
            self.assertEqual([row['role'] for row in messages],['user','assistant'])
            self.assertEqual(messages[0]['content'],prompt)
            self.assertEqual(messages[1]['content'],expected_answers[prompt_index])
            model_messages.append({'role':'assistant','content':expected_answers[prompt_index]})
            self.assertTrue(proof.json()['durable']);self.assertTrue(proof.json()['verified'])
            self.assertEqual(proof.json()['store_scope'],'OWNER_DIALOG_TABLES_ONLY')
            self.assertFalse(proof.json()['canonical_s03_verified'])
            receipts.append(done)
            expected.extend(messages)
            history=self.client.get('/api/ui/memory/dialogs/history',cookies=self.cookie,
                params={'dialog_id':dialog,'limit':6}).json()
            self.assertEqual(history['store_scope'],'OWNER_DIALOG_TABLES_ONLY')
            self.assertFalse(history['canonical_s03_readback_verified'])
            history=history['messages']
            self.assertEqual([(row['role'],row['content']) for row in history],
                [(row['role'],row['content']) for row in expected])
        for key in ('turn_id','receipt_id','exchange_id'):
            self.assertEqual(len({row[key] for row in receipts}),2)
        self.assertEqual(receipts[0]['lease_epoch'],receipts[1]['lease_epoch'])

    def test_independent_readback_holds_for_wrong_receipt_or_tampered_pair(self):
        from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import _db,_save_exchange
        dialog=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'Exact readback fixture','confirmed':True}).json()['dialog_id']
        ids={'turn_id':'1'*32,'receipt_id':'2'*32,'lease_epoch':'3'*32}
        exchange='4'*32
        self.assertTrue(_save_exchange(dialog,'exact user','exact assistant',exchange,
            turn_id=ids['turn_id'],receipt_id=ids['receipt_id'],lease_epoch=ids['lease_epoch']))
        body={'dialog_id':dialog,**ids}
        wrong=dict(body,receipt_id='5'*32)
        self.assertEqual(self.client.post('/api/ui/memory/dialogs/exchange-readback',
            cookies=self.cookie,json=wrong).status_code,409)
        good=self.client.post('/api/ui/memory/dialogs/exchange-readback',cookies=self.cookie,json=body)
        self.assertEqual(good.status_code,200,good.text)
        self.assertEqual([row['content'] for row in good.json()['messages']],
                         ['exact user','exact assistant'])
        with _db(True) as db:
            db.execute('UPDATE nox_v29_dialog_messages SET content=? '
                       'WHERE dialog_id=? AND exchange_id=? AND role=?',
                       ('tampered assistant',dialog,exchange,'assistant'))
        held=self.client.post('/api/ui/memory/dialogs/exchange-readback',cookies=self.cookie,json=body)
        self.assertEqual(held.status_code,409)

    def test_owner_dialog_receipt_provider_excludes_fuzzy_matching_and_s03_claims(self):
        source=Path(__file__).parents[1]/'native_v29_full_bridge.py'
        text=source.read_text()
        provider=text.split('class OwnerDialogExchangeReadback:',1)[1].split(
            'def _save_exchange(',1)[0]
        self.assertNotIn('instr(',provider)
        self.assertNotIn('FROM s03_items',provider)
        self.assertIn("'canonical_s03_verified':False",provider)
        self.assertIn('def _legacy_memory_readback(',text)
        stream=text.split("@app.post('/api/nox/chat/stream')",1)[1]
        self.assertIn("if not dialog_id:",stream)
        self.assertIn('OwnerDialogExchangeReadback(_db).read',stream)
        self.assertIn("'canonical_s03_write_verified':False",stream)

    def test_coalesced_sse_transport_frames_preserve_owner_dialog_done(self):
        self.bulk_sse='coalesced'
        created=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'V165 SSE','confirmed':True}).json()
        r=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'message':'V165 coherent read', 'dialog_id':created['dialog_id']})
        self.assertEqual(r.status_code,200,r.text[:300])
        frames=[json.loads(x) for x in r.text.splitlines() if x.strip()]
        self.assertEqual([f['type'] for f in frames],['preparing','start','delta','done'])
        self.assertRegex(frames[-1]['exchange_id'],r'^[a-f0-9]{32}$')
        self.assertFalse(frames[-1]['s03_integrated'])
        self.assertTrue(frames[-1]['owner_dialog_saved'])
        self.assertFalse(frames[-1]['canonical_s03_write_verified'])
        self.assertEqual(''.join(f['text'] for f in frames if f['type']=='delta'),
                         'Готов. Это проверенный ответ.')

    def test_one_oversized_sse_frame_is_still_rejected(self):
        self.bulk_sse='oversized'
        self.record=False
        dialog=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'oversized frame','confirmed':True}).json()['dialog_id']
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

    def test_dialog_context_is_recent_bounded_complete_pairs(self):
        from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import (
            _db,_dialog_context,_save_exchange,
        )
        dialog=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'Ограниченный контекст','confirmed':True}).json()['dialog_id']
        for index in range(14):
            self.assertTrue(_save_exchange(dialog,f'Вопрос {index}',f'Ответ {index}',
                                          f'bounded-{index}'))
        with _db(True) as db:
            db.execute('INSERT INTO nox_v29_dialog_messages '
                       '(dialog_id,exchange_id,role,content,ts) VALUES(?,?,?,?,?)',
                       (dialog,'orphan','assistant','Незавершённая пара','2026-11-15'))
        issue,history=_dialog_context(dialog)
        self.assertIsNone(issue)
        self.assertEqual(len(history),24)
        self.assertEqual(history[0],{'role':'user','content':'Вопрос 2'})
        self.assertEqual(history[-1],{'role':'assistant','content':'Ответ 13'})
        self.assertTrue(all(row['content']!='Незавершённая пара' for row in history))
    def test_dialog_context_preserves_full_multibyte_ru_and_es_text(self):
        from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import _save_exchange
        dialog=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'Полный многоязычный контекст','confirmed':True}).json()['dialog_id']
        question='Русский вопрос: '+('ёжик ' * 900)
        answer='Respuesta española: '+('niño café ☕ ' * 400)
        self.assertLessEqual(len(question),8000)
        self.assertLessEqual(len(answer),8000)
        self.assertTrue(_save_exchange(dialog,question,answer,'multibyte-full-context'))
        response=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'dialog_id':dialog,'message':'Продолжи','history':[]})
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.calls[-1]['messages'],[
            {'role':'user','content':question},
            {'role':'assistant','content':answer},
            {'role':'user','content':'Продолжи'}])
        frames=[json.loads(line) for line in response.text.splitlines() if line.strip()]
        self.assertEqual(frames[-1]['type'],'done')

    def test_dialog_context_oversized_message_holds_before_model(self):
        from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import _save_exchange
        dialog=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'Слишком длинный контекст','confirmed':True}).json()['dialog_id']
        oversized='Я'*1000000
        self.assertTrue(_save_exchange(dialog,oversized,'saved reply','oversized-message'))
        response=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'dialog_id':dialog,'message':'Не отправлять модели','history':[]})
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json(),{'error':'HOLD_DIALOG_CONTEXT_MESSAGE_LIMIT'})
        self.assertEqual(self.calls,[])

    def test_dialog_context_embedded_nul_cannot_bypass_message_limit(self):
        from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import _db,_save_exchange
        dialog=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'NUL length guard','confirmed':True}).json()['dialog_id']
        oversized='\\0'+'x'*8001
        self.assertTrue(_save_exchange(dialog,oversized,'saved reply','nul-message'))
        with _db() as db:
            stored=db.execute('SELECT content,length(content) AS sqlite_chars '
                              'FROM nox_v29_dialog_messages WHERE dialog_id=? '
                              "AND role='user'",(dialog,)).fetchone()
            self.assertEqual(stored['sqlite_chars'],0)
            self.assertEqual(len(stored['content']),8002)
        response=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'dialog_id':dialog,'message':'Не отправлять модели','history':[]})
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json(),{'error':'HOLD_DIALOG_CONTEXT_MESSAGE_LIMIT'})
        self.assertEqual(self.calls,[])

    def test_dialog_context_budget_overflow_holds_before_model(self):
        from nox_runpod.teacher_mesh.v112.native_v29_full_bridge import _save_exchange
        dialog=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'Бюджет полного контекста','confirmed':True}).json()['dialog_id']
        for index in range(8):
            self.assertTrue(_save_exchange(dialog,'q'*8000,'a'*8000,
                                           f'budget-pair-{index}'))
        response=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'dialog_id':dialog,'message':'Не отправлять модели','history':[]})
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json(),{'error':'HOLD_DIALOG_CONTEXT_BUDGET'})
        self.assertEqual(self.calls,[])

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

    def test_exact_dialog_writer_receipt_does_not_depend_on_legacy_match(self):
        self.record=False
        dialog=self.client.post('/api/ui/memory/dialogs/create',cookies=self.cookie,
            json={'title':'No fuzzy matcher','confirmed':True}).json()['dialog_id']
        r=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
          json={'message':'Другой уникальный вопрос','dialog_id':dialog})
        frames=[json.loads(x) for x in r.text.splitlines() if x.strip()]
        self.assertEqual(frames[-1]['type'],'done')
        proof=self.client.post('/api/ui/memory/dialogs/exchange-readback',cookies=self.cookie,
            json={key:frames[-1][key] for key in ('dialog_id','turn_id','receipt_id','lease_epoch')})
        self.assertEqual(proof.status_code,200,proof.text)
        self.assertEqual(proof.json()['messages'][0]['content'],'Другой уникальный вопрос')

    def test_no_dialog_legacy_caller_keeps_existing_s03_readback_behavior(self):
        r=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'message':'legacy no-dialog prompt'})
        self.assertEqual(r.status_code,200,r.text[:200])
        frames=[json.loads(line) for line in r.text.splitlines() if line.strip()]
        done=frames[-1]
        self.assertEqual(done['type'],'done')
        self.assertTrue(done['saved']);self.assertTrue(done['s03_integrated'])
        self.assertIsNone(done['dialog_id'])
        self.assertEqual(done['exchange_id'],'fixture-memory-0001')
        self.assertNotIn('receipt_id',done)

    def test_no_dialog_legacy_caller_still_holds_without_old_s03_write(self):
        self.record=False
        r=self.client.post('/api/nox/chat/stream',cookies=self.cookie,
            json={'message':'legacy missing S03 write'})
        frames=[json.loads(line) for line in r.text.splitlines() if line.strip()]
        self.assertEqual(frames[-1],{'type':'error','error':'HOLD_S03_COMMIT_NOT_VERIFIED'})
        self.assertFalse(any(frame.get('saved') for frame in frames))

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
