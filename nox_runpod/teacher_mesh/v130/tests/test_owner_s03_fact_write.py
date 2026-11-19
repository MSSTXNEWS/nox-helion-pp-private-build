"""V130 source-only S03 writer fixture; not a live Vast or private-data receipt."""
import hashlib,json,sqlite3,sys,tempfile,types,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from nox_runpod.teacher_mesh.v130 import owner_s03_fact_write as api

class V130Tests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        self.db=root/'original_s03.sqlite'
        self.stop=root/'STOP'
        with sqlite3.connect(self.db) as db:
            db.execute("CREATE TABLE s03_items(id TEXT PRIMARY KEY,segment TEXT,text TEXT,provenance TEXT,sha256 TEXT,meta TEXT,ts TEXT)")
        module=types.ModuleType('s03_memory')
        module.DB=self.db
        self.calls=0
        def remember(*,text,segment,provenance,salience,meta):
            self.calls+=1
            with sqlite3.connect(self.db) as db:
                db.execute("INSERT INTO s03_items VALUES(?,?,?,?,?,?,?)",(
                    uuid.uuid4().hex,segment,text,provenance,
                    hashlib.sha256((segment+'|'+text+'|'+provenance+'|'+json.dumps(meta,sort_keys=True)).encode('utf8')).hexdigest(),
                    json.dumps(meta,ensure_ascii=False),'2026-11-15T00:00:00Z'))
        module.remember=remember
        previous=sys.modules.get('s03_memory')
        sys.modules['s03_memory']=module
        self.addCleanup(lambda:sys.modules.pop('s03_memory',None) if previous is None
                         else sys.modules.__setitem__('s03_memory',previous))
        stop_patch=patch.object(api,'_STOP',(str(self.stop),))
        stop_patch.start();self.addCleanup(stop_patch.stop)
        self.app=FastAPI()
        api.register_nox_v130_owner_fact_write(self.app,{
            '_session_ok':lambda r:r.cookies.get('owner')=='yes',
            '_unauthorized':lambda:JSONResponse({'error':'AUTH'},status_code=401)})
        self.client=TestClient(self.app)
        self.addCleanup(self.client.close)
        self.payload={'fact_key':'OWNER-NOTE-TEST-1','content':'Сохранить проверенную заметку V130',
                      'valid_from':'2026-11-15T00:00:00.000Z',
                      'source_ref':'OWNER-CONFIRMED-NOTE'}
        self.payload['source_sha256']=hashlib.sha256(self.payload['content'].encode('utf8')).hexdigest()

    def post(self,data=None,**kw):
        return self.client.post('/api/nox/memory/facts',
             json=self.payload if data is None else data,cookies={'owner':'yes'},**kw)

    def test_unauthorized_is_401_and_no_data_written(self):
        response=self.client.post('/api/nox/memory/facts',json=self.payload)
        self.assertEqual(response.status_code,401)
        self.assertEqual(self.calls,0)

    def test_native_remember_durable_readback_and_idempotent(self):
        first=self.post()
        self.assertEqual(first.status_code,200,first.text)
        r=first.json()
        self.assertTrue(r['committed'])
        self.assertTrue(r['readback_verified'])
        self.assertFalse(r['duplicate'])
        self.assertEqual(self.calls,1)
        with sqlite3.connect(self.db) as db:
            row=db.execute("SELECT id,segment,text,provenance,meta FROM s03_items").fetchone()
        self.assertEqual(row[0],r['event_id'])
        self.assertEqual(row[1],'M2')
        self.assertEqual(row[2],self.payload['content'])
        self.assertEqual(row[3],'OWNER-CONFIRMED:'+self.payload['source_ref'])
        self.assertEqual(r['source_sha256'],self.payload['source_sha256'])
        self.assertNotEqual(r['record_sha256'],r['source_sha256'])
        self.assertEqual(json.loads(row[4])['fact_key'],self.payload['fact_key'])
        second=self.post()
        self.assertEqual(second.status_code,200,second.text)
        self.assertTrue(second.json()['duplicate'])
        self.assertEqual(second.json()['event_id'],r['event_id'])
        self.assertEqual(self.calls,1)

    def test_quarantined_or_wrong_source_metadata_is_not_confirmed_readback(self):
        self.assertEqual(self.post().status_code,200)
        with sqlite3.connect(self.db) as db:
            raw=db.execute('SELECT meta FROM s03_items').fetchone()[0]
        original=json.loads(raw)
        for key,value in (('schema','NOX_QUARANTINED_CANDIDATE_V1'),
                          ('source_ref','UNRELATED-SOURCE')):
            with self.subTest(key=key):
                with sqlite3.connect(self.db) as db:
                    db.execute('UPDATE s03_items SET meta=?',
                               (json.dumps({**original,key:value}),))
                self.assertEqual(api._matching(self.payload),[])
                with sqlite3.connect(self.db) as db:
                    db.execute('UPDATE s03_items SET meta=?',(raw,))
        self.assertEqual(self.calls,1)

    def test_stop_during_readback_scan_blocks_native_write(self):
        def stopped_after_scan(data):
            self.stop.write_text('STOP')
            return []
        with patch.object(api,'_matching',side_effect=stopped_after_scan):
            response=self.post()
        self.assertEqual(response.json()['reason'],'HOLD_NATIVE_STOP')
        self.assertEqual(self.calls,0)

    def test_hash_mismatch_no_memory_write(self):
        record={**self.payload,'content':'Изменённый текст'}
        response=self.post(record)
        self.assertEqual(response.status_code,422,response.text)
        self.assertIn('HOLD_FACT_CONTENT_SHA',response.text)
        self.assertEqual(self.calls,0)

    def test_stop_blocks_write(self):
        self.stop.write_text('STOP')
        response=self.post()
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.calls,0)

    def test_dangling_owner_stop_symlink_blocks_native_fact_write(self):
        # Path.exists() is False on a broken symlink. STOP must still block.
        self.stop.symlink_to(self.stop.parent/'missing-owner-stop-target')
        self.assertFalse(self.stop.exists())
        self.assertTrue(self.stop.is_symlink())
        response=self.post()
        self.assertEqual(response.status_code,409,response.text)
        self.assertIn('HOLD_NATIVE_STOP',response.text)
        self.assertEqual(self.calls,0,'must not invoke native remember under STOP')

    def test_owner_stop_symlink_existing_target_blocks_fact_write(self):
        target=self.stop.parent/'owner-stop-target'
        target.write_text('STOP')
        self.stop.symlink_to(target)
        self.assertTrue(api._stopped())
        response=self.post()
        self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(self.calls,0)

    def test_owner_stop_failure_to_stat_is_fail_closed(self):
        with patch.object(api.Path,'exists',side_effect=OSError('EACCES')):
            self.assertTrue(api._stopped())
            response=self.post()
            self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(self.calls,0)

    def test_cross_origin_rejected(self):
        response=self.post(headers={'Origin':'https://example.evil'})
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.calls,0)

    def test_browser_same_origin_through_reverse_proxy(self):
        # Sec-Fetch-Site is browser-generated, not controlled by regular JS.
        response=self.post(headers={'Origin':'https://owner.nox.example',
                                    'Sec-Fetch-Site':'same-origin'})
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()['readback_verified'])
        self.assertEqual(self.calls,1)

    def test_cross_site_browser_rejected(self):
        response=self.post(headers={'Sec-Fetch-Site':'cross-site'})
        self.assertEqual(response.status_code,403)
        self.assertEqual(self.calls,0)

    def test_unsupported_body_or_content_type_rejected(self):
        bad={**self.payload,'source_ref':''}
        self.assertEqual(self.post(bad).status_code,422)
        r=self.client.post('/api/nox/memory/facts',data='xx',cookies={'owner':'yes'},
                           headers={'Content-Type':'text/plain'})
        self.assertEqual(r.status_code,415)
        self.assertEqual(self.calls,0)

    def test_same_content_other_fact_key_does_not_fake_new_write(self):
        first=self.post()
        self.assertEqual(first.status_code,200)
        another={**self.payload,'fact_key':'OWNER-NOTE-TEST-2'}
        response=self.post(another)
        self.assertEqual(response.status_code,200)
        self.assertNotEqual(response.json()['event_id'],first.json()['event_id'])
        self.assertEqual(self.calls,2)

    def test_owner_fact_key_idempotency_paginates_beyond_100_same_text_rows(self):
        original=self.post()
        self.assertEqual(original.status_code,200,original.text)
        original_id=original.json()['event_id']
        # Real in-memory SQLite fixture; 112 independent owner-confirmed
        # notes with the same content/source bury the old fact-key row.
        with sqlite3.connect(self.db) as db:
            for n in range(112):
                meta={'schema':'NOX_OWNER_CONFIRMED_FACT_V1',
                      'owner_scope':'nox-single-owner',
                      'fact_key':f'OTHER-KEY-{n}',
                      'source_ref':self.payload['source_ref'],
                      'source_sha256':self.payload['source_sha256'],
                      'valid_from':self.payload['valid_from']}
                db.execute("INSERT INTO s03_items VALUES(?,?,?,?,?,?,?)",(
                    uuid.uuid4().hex,'M2',self.payload['content'],
                    'OWNER-CONFIRMED:'+self.payload['source_ref'],
                    hashlib.sha256(f'other-{n}'.encode()).hexdigest(),
                    json.dumps(meta),'2026-11-15T00:00:00Z'))
        again=self.post()
        self.assertEqual(again.status_code,200,again.text)
        self.assertTrue(again.json()['duplicate'])
        self.assertEqual(again.json()['event_id'],original_id)
        self.assertEqual(self.calls,1,'no second native remember() for buried key')

    def test_schema_mismatch_holds_and_preserves_db(self):
        with sqlite3.connect(self.db) as db:
            db.execute('ALTER TABLE s03_items RENAME TO s03_items_old')
        r=self.post()
        self.assertEqual(r.status_code,503)
        self.assertEqual(self.calls,0)



class CanonicalStopTests(unittest.TestCase):
    def test_existing_state_stop_marker_blocks(self):
        def exists(path):
            return str(path)=='/root/nox/state/STOP.flag'
        with patch.object(api.Path,'exists',exists), patch.object(api.Path,'is_symlink',return_value=False):
            self.assertTrue(api._stopped())

if __name__=='__main__':unittest.main()
