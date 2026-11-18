import asyncio
import hashlib
import json
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse,StreamingResponse
import native_v29_full_bridge as bridge
from owner_chat_request_ledger import RequestLedger,LedgerError

DIALOG='a'*32
ANSWER='Привет 🌌 — mañana!'

class LedgerBase:
    def setup_db(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'existing-s03.sqlite'
        with sqlite3.connect(self.path) as db:db.execute('CREATE TABLE s03_items(id TEXT PRIMARY KEY,sha256 TEXT,ts REAL,text TEXT)')
        self.mock=patch.dict(sys.modules,s03_memory=types.SimpleNamespace(DB=self.path));self.mock.start();self.addCleanup(self.mock.stop)
        self.assertTrue(bridge.ensure_dialog_schema())
        with bridge._db(True) as db:
            db.execute('INSERT INTO nox_v29_dialogs VALUES(?,?,?,?,?,?,?)',(DIALOG,bridge.OWNER,'test',0,1,bridge._now(),bridge._now()))
        self.ledger=RequestLedger(bridge._db,bridge.OWNER)
    def accept(self,rid='request-a'):
        return self.ledger.accept(rid,'Вопрос',DIALOG,{'message':'Вопрос','dialog_id':DIALOG},'session-a')

class LedgerTests(LedgerBase,unittest.TestCase):
    def setUp(self):self.setup_db()
    def test_concurrent_request_has_one_producer_and_one_accepted_event(self):
        with ThreadPoolExecutor(max_workers=8) as ex:rows=list(ex.map(lambda _:self.accept(),range(16)))
        self.assertEqual(sum(token is not None for _,token in rows),1)
        self.assertEqual(len({row['exchange_id'] for row,_ in rows}),1)
        self.assertEqual(len(self.ledger.events('request-a',0)[0]),1)
    def test_conflicting_request_never_restarts_or_replaces_payload(self):
        self.accept()
        # The context guard precedes the payload hash guard. Both must
        # refuse a reused request_id without replaying another request.
        with self.assertRaisesRegex(LedgerError,'REQUEST_ID_CONTEXT_CONFLICT'):
            self.ledger.accept('request-a','different',DIALOG,{'message':'different'},'session-a')
        with self.assertRaisesRegex(LedgerError,'REQUEST_ID_PAYLOAD_CONFLICT'):
            self.ledger.accept('request-a','Вопрос',DIALOG,
                               {'message':'Вопрос','dialog_id':DIALOG,'history':['changed']},'session-a')
        self.assertEqual(self.ledger.snapshot('request-a')['message'],'Вопрос')
        self.assertEqual(self.ledger.snapshot('request-a')['last_event_id'],1)
    def test_dead_producer_restarts_as_interrupted_without_second_claim(self):
        self.accept()
        with bridge._db(True) as db:db.execute('UPDATE nox_chat_requests SET producer_pid=2147483647')
        row=self.ledger.snapshot('request-a');self.assertEqual(row['state'],'interrupted')
        self.assertFalse(row['saved']);self.assertEqual(row['last_event_id'],2)
        replay,token=self.accept();self.assertIsNone(token);self.assertEqual(replay['state'],'interrupted')
        self.assertEqual(self.ledger.snapshot('request-a')['last_event_id'],2)
    def test_cursor_and_unicode_exact_order_durable_across_new_ledger_object(self):
        row,token=self.accept();self.ledger.append('request-a',token,{'type':'start'})
        for part in ('П','ривет ','🌌',' mañana'):
            self.ledger.append('request-a',token,{'type':'delta','text':part})
        reopened=RequestLedger(bridge._db,bridge.OWNER)
        events,snapshot=reopened.events('request-a',3)
        self.assertEqual([e['event_id'] for e in events],[4,5,6])
        self.assertEqual(snapshot['answer'],'Привет 🌌 mañana')
        with self.assertRaisesRegex(LedgerError,'CURSOR_AHEAD'):reopened.events('request-a',999)
    def test_replay_cursor_snapshot_uses_single_transaction_not_a_read_gap(self):
        row, token = self.accept('request-cursor-atomic')
        self.ledger.append('request-cursor-atomic', token, {'type':'start'})
        other = RequestLedger(bridge._db, bridge.OWNER)
        original_snapshot = self.ledger.snapshot

        def inject_post_snapshot_delta(rid):
            previous = original_snapshot(rid)
            # If replay obtains snapshot and event rows in separate
            # transactions, this insert becomes visible to the latter SELECT.
            other.append(rid, token, {'type':'delta','text':'later'})
            return previous

        with patch.object(self.ledger, 'snapshot', side_effect=inject_post_snapshot_delta) as gap:
            events, snapshot = self.ledger.events('request-cursor-atomic', 0)
        self.assertFalse(gap.called, 'replay must not use a separate snapshot transaction')
        self.assertEqual([event['event_id'] for event in events],
                         list(range(1, snapshot['last_event_id']+1)))
        self.assertTrue(all(event['event_id']<=snapshot['last_event_id'] for event in events))

    def test_s03_reconnect_event_page_limit_is_finite_and_integer(self):
        row, token = self.accept('request-page-bound')
        self.ledger.append('request-page-bound', token, {'type':'start'})
        for text in ('one', 'two', 'three'):
            self.ledger.append('request-page-bound', token, {'type':'delta','text':text})
        before = self.ledger.snapshot('request-page-bound')
        for bad in (-1, 0, 257, True, False, 1.0, '256', None):
            with self.subTest(limit=repr(bad)):
                with self.assertRaisesRegex(LedgerError, 'INVALID_EVENT_PAGE_LIMIT'):
                    self.ledger.events('request-page-bound', 0, bad)
        page, snap = self.ledger.events('request-page-bound', 0, 1)
        self.assertEqual([event['event_id'] for event in page], [1])
        self.assertEqual(snap['last_event_id'], before['last_event_id'])
        full, snap = self.ledger.events('request-page-bound', 0)
        self.assertEqual(len(full), 5)
        self.assertEqual(snap['last_event_id'], before['last_event_id'])

    def test_cursor_overflow_is_validation_error_not_sqlite_exception(self):
        self.accept('request-cursor-bound')
        for invalid in (-1, True, False, 2**63, 10**90, '1', None, 1.0):
            with self.subTest(after=repr(invalid)):
                with self.assertRaisesRegex(LedgerError, 'INVALID_EVENT_CURSOR'):
                    self.ledger.events('request-cursor-bound', invalid)
        # The largest representable SQLite signed integer is valid syntax,
        # but is ahead of the committed event cursor.
        with self.assertRaisesRegex(LedgerError, 'EVENT_CURSOR_AHEAD'):
            self.ledger.events('request-cursor-bound', 2**63-1)

    def test_atomic_pair_and_done_with_stable_exchange(self):
        row,token=self.accept();self.ledger.append('request-a',token,{'type':'delta','text':ANSWER})
        proof={'record_id':'native-record','sha256':'b'*64}
        with self.assertRaisesRegex(LedgerError,'S03_COMMIT'):self.ledger.complete('request-a',token,proof)
        with bridge._db() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM nox_v29_dialog_messages').fetchone()[0],0)
        with bridge._db(True) as db:db.execute('INSERT INTO s03_items VALUES(?,?,?,?)',(proof['record_id'],proof['sha256'],time.time(),'Вопрос '+ANSWER))
        done=self.ledger.complete('request-a',token,proof)
        self.assertEqual(done['exchange_id'],row['exchange_id']);self.assertEqual(done['s03_record_id'],'native-record')
        with bridge._db() as db:
            rows=db.execute('SELECT exchange_id,role,content FROM nox_v29_dialog_messages ORDER BY row_id').fetchall()
        self.assertEqual([r[0] for r in rows],[row['exchange_id']]*2)
        self.assertEqual([r[1] for r in rows],['user','assistant'])
        self.assertTrue(self.ledger.snapshot('request-a')['saved'])
    def test_owner_isolation_stop_never_certifies_gpu_and_stop_blocks_commit(self):
        row,token=self.accept()
        with self.assertRaisesRegex(LedgerError,'NOT_FOUND'):RequestLedger(bridge._db,'other').snapshot('request-a')
        stop=self.ledger.stop('request-a');self.assertFalse(stop['gpu_stop_verified']);self.assertTrue(stop['stop_recorded'])
        with self.assertRaisesRegex(LedgerError,'STREAM_STOP_REQUESTED'):self.ledger.complete('request-a',token,{})
        self.assertFalse(self.ledger.snapshot('request-a')['saved'])
    def test_durable_stop_fences_subsequent_start_and_delta_without_extra_event(self):
        row, token = self.accept('request-stop-fence')
        before = self.ledger.snapshot('request-stop-fence')
        self.assertEqual(before['last_event_id'], 1)
        self.ledger.stop('request-stop-fence')
        for event in ({'type':'start'}, {'type':'delta','text':'late GPU token'}):
            with self.assertRaisesRegex(LedgerError, 'STREAM_STOP_REQUESTED'):
                self.ledger.append('request-stop-fence', token, event)
        snapshot = self.ledger.snapshot('request-stop-fence')
        self.assertEqual(snapshot['last_event_id'], before['last_event_id'])
        self.assertEqual(snapshot['answer'], '')
        self.assertFalse(snapshot['saved'])
        terminal = self.ledger.append('request-stop-fence', token,
                                      {'type':'error','error':'STREAM_STOP_REQUESTED'})
        self.assertEqual(terminal['event_id'], 2)
        self.assertEqual(self.ledger.snapshot('request-stop-fence')['state'], 'error')

class ProducerProcessStateTests(unittest.TestCase):
    def test_only_runnable_kernel_states_prove_producer_identity(self):
        from owner_chat_request_ledger import identity
        pid = 42561
        actual_read = Path.read_text
        def evaluate(state, ticks=12345):
            stat_text = f"{pid} (nox SSE ) " + " ".join([state]+["0"]*18+[str(ticks)])
            def fake(path, *args, **kwargs):
                if str(path)==f"/proc/{pid}/stat": return stat_text
                if str(path)=="/proc/sys/kernel/random/boot_id": return "boot-id\n"
                return actual_read(path, *args, **kwargs)
            with patch.object(Path, "read_text", new=fake):
                return identity(pid)
        for state in ("Z","T","t","X","x","K","W","P","?"):
            with self.subTest(state=state): self.assertIsNone(evaluate(state))
        for state in ("R","S","D","I"):
            with self.subTest(state=state): self.assertEqual(evaluate(state),(pid,12345,"boot-id"))
        for ticks in (0,-1):
            with self.subTest(ticks=ticks): self.assertIsNone(evaluate("S",ticks))


class BridgeTests(LedgerBase,unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.setup_db();self.calls=0;self.release=asyncio.Event();self.release.set();self.opening_release=asyncio.Event();self.opening_release.set()
        self.app=FastAPI()
        async def proxy(payload):
            self.calls+=1
            await self.opening_release.wait()
            question=payload['messages'][-1]['content']
            async def stream():
                raw=('data: '+json.dumps({'choices':[{'delta':{'content':ANSWER}}]},ensure_ascii=False)+'\n\n').encode()
                # Split inside the multibyte emoji, exercising the real decoder.
                split=raw.index('🌌'.encode())+1
                yield raw[:split];yield raw[split:]
                await self.release.wait()
                with bridge._db(True) as db:
                    db.execute('INSERT INTO s03_items VALUES(?,?,?,?)',('native-'+str(self.calls),'b'*64,time.time(),question+' '+ANSWER))
                yield b'data: [DONE]\n\n'
            return StreamingResponse(stream(),media_type='text/event-stream')
        async def status():return {'primary_model':'fixture-only'}
        trusted={'_session_ok':lambda r:r.cookies.get('owner')=='test',
                 '_unauthorized':lambda:JSONResponse({'error':'unauthorized'},status_code=401),
                 '_proxy_completion':proxy,'nox_status':status}
        bridge.register_native_v29_chat(self.app,trusted,site_dir=self.tmp.name)
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app),base_url='http://test',cookies={'owner':'test'})
        self.addAsyncCleanup(self.client.aclose)
        self.body={'request_id':'request-live','dialog_id':DIALOG,'message':'Вопрос'}
    def frames(self,response):return [json.loads(row) for row in response.text.splitlines() if row.strip()]
    async def snapshot_until(self,predicate):
        for _ in range(100):
            response=await self.client.get('/api/nox/chat/requests/request-live')
            if response.status_code==200 and predicate(response.json()):return response.json()
            await asyncio.sleep(.01)
        self.fail('snapshot deadline')
    async def test_post_replay_get_resume_and_history_share_one_exchange(self):
        first=await self.client.post('/api/nox/chat/stream',json=self.body)
        self.assertEqual(first.status_code,200);frames=self.frames(first)
        self.assertEqual(frames[-1]['type'],'done')
        self.assertEqual([x['event_id'] for x in frames],list(range(1,len(frames)+1)))
        second=await self.client.post('/api/nox/chat/stream',json=self.body)
        self.assertEqual(self.frames(second),frames);self.assertEqual(self.calls,1)
        snapshot=(await self.client.get('/api/nox/chat/requests/request-live')).json()
        self.assertEqual(snapshot['answer'],ANSWER);self.assertEqual(snapshot['message'],'Вопрос')
        resume=await self.client.get('/api/nox/chat/requests/request-live/events?after_event_id=2')
        self.assertEqual(self.frames(resume),frames[2:])
        history=(await self.client.get('/api/ui/memory/dialogs/history',params={'dialog_id':DIALOG})).json()
        self.assertEqual({r['exchange_id'] for r in history['messages']},{snapshot['exchange_id']})
        fixture={'fixture_kind':'SOURCE_ASGI_SYNTHETIC_MODEL_REAL_SQLITE_LEDGER','request':self.body,
                 'ndjson':first.text,'snapshot':snapshot,'history':history}
        (Path(__file__).parents[1]/'source_boundary_fixture.json').write_text(json.dumps(fixture,ensure_ascii=False,indent=2)+'\n')
    async def test_disconnect_does_not_cancel_producer_or_trigger_new_inference(self):
        self.release.clear()
        request=asyncio.create_task(self.client.post('/api/nox/chat/stream',json=self.body))
        await self.snapshot_until(lambda row:bool(row['answer']))
        request.cancel()
        try:await request
        except asyncio.CancelledError:pass
        self.release.set();snapshot=await self.snapshot_until(lambda row:row['terminal'])
        self.assertEqual(snapshot['state'],'done');self.assertEqual(self.calls,1)
        resumed=await self.client.get('/api/nox/chat/requests/request-live/events?after_event_id=0')
        self.assertEqual(self.frames(resumed)[-1]['type'],'done')
    async def test_request_scoped_stop_persists_no_saved_or_gpu_halt_claim(self):
        self.release.clear()
        request=asyncio.create_task(self.client.post('/api/nox/chat/stream',json=self.body))
        await self.snapshot_until(lambda row:bool(row['answer']))
        wrong=await self.client.post('/api/nox/stop',json={'request_id':'other'});self.assertEqual(wrong.status_code,404)
        stop=await self.client.post('/api/nox/stop',json={'request_id':'request-live'})
        self.assertFalse(stop.json()['gpu_stop_verified'])
        response=await asyncio.wait_for(request,2)
        self.assertEqual(self.frames(response)[-1]['error'],'STREAM_STOP_REQUESTED')
        self.assertFalse((await self.client.get('/api/nox/chat/requests/request-live')).json()['saved'])
    async def test_stop_during_upstream_open_terminates_without_done(self):
        self.opening_release.clear()
        request=asyncio.create_task(self.client.post('/api/nox/chat/stream',json=self.body))
        await self.snapshot_until(lambda row:row['last_event_id']>=1)
        stopped=await self.client.post('/api/nox/stop',json={'request_id':'request-live'})
        self.assertEqual(stopped.status_code,200)
        response=await asyncio.wait_for(request,2)
        self.assertEqual(self.frames(response)[-1]['error'],'STREAM_STOP_REQUESTED')
        self.assertFalse(any(row['type']=='done' for row in self.frames(response)))

    async def test_overflow_cursor_rejected_before_durable_request_or_inference(self):
        # A malformed reconnect cursor must not admit/start a model request.
        # This was previously rejected only by ledger.events after begin().
        for invalid in (2**63, 10**90, -1, True, '1'):
            with self.subTest(after=repr(invalid)):
                result=await self.client.post('/api/nox/chat/stream',
                    json={**self.body,'after_event_id':invalid})
                self.assertEqual(result.status_code,422)
                self.assertEqual(result.json()['error'],'INVALID_EVENT_CURSOR')
                self.assertEqual(self.calls,0)
                self.assertEqual((await self.client.get(
                    '/api/nox/chat/requests/request-live')).status_code,404)
        valid=await self.client.post('/api/nox/chat/stream',json=self.body)
        self.assertEqual(valid.status_code,200)
        self.assertEqual(self.frames(valid)[-1]['type'],'done')
        self.assertEqual(self.calls,1)

    async def test_auth_bad_cursor_conflict_and_get_missing_do_not_invoke_model(self):
        missing=await self.client.get('/api/nox/chat/requests/missing/events');self.assertEqual(missing.status_code,404);self.assertEqual(self.calls,0)
        await self.client.post('/api/nox/chat/stream',json=self.body)
        bad=await self.client.post('/api/nox/chat/stream',json={**self.body,'message':'changed'})
        self.assertEqual(bad.status_code,409);self.assertEqual(self.calls,1)
        cursor=await self.client.get('/api/nox/chat/requests/request-live/events?after_event_id=999');self.assertEqual(cursor.status_code,409)
        self.client.cookies.clear()
        for path in ('/api/nox/chat/requests/request-live','/api/nox/chat/requests/request-live/events'):
            self.assertEqual((await self.client.get(path)).status_code,401)
