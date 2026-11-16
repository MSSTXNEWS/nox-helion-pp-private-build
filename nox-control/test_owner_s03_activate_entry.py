import ast
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent
SPEC=importlib.util.spec_from_file_location('owner_s03_activate_entry',HERE/'owner_s03_activate_entry.py')
a=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(a)


class ActivationTests(unittest.TestCase):
    def test_reviewed_helper_sources_are_pinned(self):
        for name,sha in [('owner_native_repair.py',a.HELPER_SHA),('owner_task_lifecycle.py',a.LIFECYCLE_AFTER),('owner_event_outbox.py',a.OUTBOX_AFTER),('owner_s03_gateway.py',a.GATEWAY_SHA)]:
            self.assertEqual(hashlib.sha256((HERE/name).read_bytes()).hexdigest(),sha)

    def test_exact_lifecycle_binding_changes_and_real_memory_lock_precedes_it(self):
        source=('import threading\nLOCKS={}\nWORKERS=6\n# NOX_OWNER_TASK_LIFECYCLE_BIND_V1\nimport owner_task_lifecycle\n'
                'owner_task_lifecycle.bind_dispatcher(globals(), '+repr(a.OLD_SOURCE_PINS)+')\n')
        result=a.transform_dispatcher(source,a.digest(source.encode()))
        self.assertLess(result.index("LOCKS['shared_memory_index']"),result.index('owner_s03_gateway.bind_dispatcher'))
        self.assertLess(result.index('owner_s03_gateway.bind_dispatcher'),result.index('owner_task_lifecycle.bind_dispatcher'))
        self.assertEqual(result.count('WORKERS=6'),1)
        calls=[n for n in ast.walk(ast.parse(result)) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='bind_dispatcher']
        bound=next(n for n in calls if n.func.value.id=='owner_task_lifecycle')
        self.assertEqual(ast.literal_eval(bound.args[1]),a.NEW_SOURCE_PINS)
        with self.assertRaisesRegex(RuntimeError,'PREIMAGE'):a.transform_dispatcher(source,'a'*64)
        changed=source.replace(a.OUTBOX_BEFORE,'f'*64)
        with self.assertRaisesRegex(RuntimeError,'OLD_LIFECYCLE'):a.transform_dispatcher(changed,a.digest(changed.encode()))

    def test_live_recall_projection_never_returns_memory_text_or_ids(self):
        rows=[{'id':'PRIVATE_ID','text':'PRIVATE_HISTORY','how':'semantic'},{'id':'PRIVATE_PIN','text':'PRIVATE_IDENTITY','how':'pin'}]
        value=a.recall_projection(rows)
        self.assertNotIn('PRIVATE_',json.dumps(value));self.assertEqual(value['methods']['semantic'],1)
        with self.assertRaisesRegex(RuntimeError,'LIVE_SEMANTIC'):a.recall_projection([{'how':'fts'}])
        with self.assertRaisesRegex(RuntimeError,'LIVE_SEMANTIC'):a.recall_projection(rows+[{'how':'pin'},{'how':'pin'}])

    def test_prepare_receipt_requires_complete_index_and_exact_source_prediction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);scripts=root/'scripts';scripts.mkdir()
            native=b'original inspected source';(scripts/'s03_memory.py').write_bytes(native)
            record={'schema':'NOX_OWNER_S03_PREPARE_V1','state':'HISTORY_AND_INDEX_PREPARED','gateway_sha256':a.PREPARE_GATEWAY_SHA,
                    's03_before_sha256':a.digest(native),'s03_source_changed':False,'private_text_exported':False,
                    'training_examples_accepted':0,'synthetic_retrieval_acceptance':{'state':'SYNTHETIC_SEMANTIC_FIXTURES_VERIFIED'},
                    's03_after_activation_sha256':a.digest(b'patched source'),'status':{'stale_embeddings':0,'current_embeddings':15}}
            path=root/'prepare.json';path.write_text(json.dumps(record))
            class Gateway:
                patch_s03=staticmethod(lambda source:'patched source')
            with patch.object(a,'SCRIPTS',scripts),patch.object(a,'S03_BEFORE',a.digest(native)),patch.object(a,'S03_AFTER',a.digest(b'patched source')):
                _,source=a.verify_prepare(path,a.digest(path.read_bytes()),Gateway)
                self.assertEqual(source,b'patched source');self.assertEqual((scripts/'s03_memory.py').read_bytes(),native)
                record['status']['stale_embeddings']=1;path.write_text(json.dumps(record))
                with self.assertRaisesRegex(RuntimeError,'NOT_VERIFIED'):a.verify_prepare(path,a.digest(path.read_bytes()),Gateway)

    def test_missing_owner_context_cannot_load_or_pause_any_service(self):
        with patch.dict(os.environ,{},clear=True),patch.object(a,'module') as load:
            with self.assertRaisesRegex(RuntimeError,'CONTEXT'):a.main()
            load.assert_not_called()
        self.assertNotIn('nox-chat-8081',a.CONTROLLERS)
        self.assertNotIn('nox-train-volta-t866u',a.CONTROLLERS)

    def test_smoke_projection_retains_safe_failure_counts_without_private_values(self):
        value={'chat_alias_bound':True,'rows':8,'semantic_matches':0,'pin_count':2,
               'private_text_exported':False,'raw_memory':'PRIVATE_SENTINEL',
               'methods':{'fts':6,'pin':2,'private_key':'PRIVATE_SENTINEL'},
               'diagnostic':{'matching_index_rows':514,'embedding_dimensions':1024,'embedding_ms':42,
                             'embedding_error':'HOLD_S03_BGE_TIMEOUT','direct_error':'OperationalError',
                             'raw_error':'PRIVATE_SENTINEL','private_url':'PRIVATE_SENTINEL'}}
        result=a.smoke_projection(value)
        self.assertNotIn('PRIVATE_SENTINEL',json.dumps(result))
        self.assertEqual(result['diagnostic']['embedding_error'],'HOLD_S03_BGE_TIMEOUT')
        self.assertEqual(result['semantic_matches'],0)
        source=Path(a.__file__).read_text()
        self.assertLess(source.index("event('s03_proxy_source_smoke',smoke)"),
                        source.index("if smoke.get('chat_alias_bound')"))

    def test_candidate_diagnostic_isolated_and_preserves_database_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/'fixture.sqlite'
            with sqlite3.connect(db) as connection:
                connection.execute('CREATE TABLE nox_s03_vectors(model_identity TEXT,embedding BLOB,dimensions INTEGER)')
                connection.execute('INSERT INTO nox_s03_vectors VALUES(?,?,?)',('a'*64,struct.pack('<2f',1.,0.),2))
            before=db.read_bytes()
            candidate=('import contextlib,sqlite3\nDIMENSIONS=2\nDB='+repr(str(db))+'\n'
                       '@contextlib.contextmanager\ndef connection(path,seconds=1):\n'
                       ' c=sqlite3.connect("file:"+path+"?mode=ro",uri=True);c.row_factory=sqlite3.Row\n'
                       ' try: yield c\n finally: c.close()\n'
                       'def model_identity(): return "a"*64\n'
                       'def embed(texts,timeout=.65): return [[1.,0.]]\n'
                       'def recall(query,k=6,**kwargs): return [{"how":"semantic","text":"PRIVATE_SENTINEL"}]\n').encode()
            env={'NOX_OWNER_REQUEST_ID':'123','NOX_OWNER_SOURCE_SHA':'b'*40}
            with patch.dict(os.environ,env,clear=True),patch.object(a,'PYTHON',sys.executable), \
                 patch.object(a,'GATEWAY_SHA',a.digest(candidate)), \
                 patch.object(a,'BUNDLE',{'owner_s03_gateway.py':base64.b64encode(candidate).decode()}), \
                 patch.object(a,'emit') as emit:
                result=a.read_only_probe()
            self.assertEqual(before,db.read_bytes())
            self.assertFalse(result['live_sources_changed']);self.assertFalse(result['canonical_index_written'])
            self.assertEqual(result['observation']['semantic_matches'],1)
            self.assertEqual(result['observation']['diagnostic']['matching_index_rows'],1)
            self.assertEqual(result['observation']['diagnostic']['above_threshold'],1)
            self.assertNotIn('PRIVATE_SENTINEL',json.dumps(result))
            emit.assert_called_once()

    def test_identity_probe_distinguishes_stat_drift_without_relabelling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);db=root/'fixture.sqlite';model=root/'model.gguf';model.write_bytes(b'synthetic model')
            info=model.stat();old=[info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns-1]
            record={'model_id':'bge-m3','dimensions':2,'device':old[0],'inode':old[1],
                    'bytes':old[2],'mtime_ns':old[3],'ctime_ns':old[4]}
            old_identity=a.digest(json.dumps(record,sort_keys=True,separators=(',',':')).encode())
            with sqlite3.connect(db) as connection:
                connection.execute('CREATE TABLE nox_s03_vectors(model_identity TEXT)')
                connection.execute('INSERT INTO nox_s03_vectors VALUES(?)',(old_identity,))
                connection.execute('CREATE TABLE nox_s03_gateway_meta(key TEXT,value TEXT)')
                connection.execute('INSERT INTO nox_s03_gateway_meta VALUES(?,?)',('model_file_stat',json.dumps(old)))
            before=db.read_bytes()
            candidate=('import contextlib,hashlib,json,pathlib,sqlite3\nDIMENSIONS=2\nDB='+repr(str(db))+'\n'
                       'MODEL=pathlib.Path('+repr(str(model))+')\n_model_cache={"id":"bge-m3"}\n'
                       'def digest(raw): return hashlib.sha256(raw).hexdigest()\n'
                       'def encoded(value): return json.dumps(value,sort_keys=True,separators=(",",":")).encode()\n'
                       'def regular(path): return pathlib.Path(path).stat()\n'
                       'def file_sha(path): return digest(pathlib.Path(path).read_bytes())\n'
                       '@contextlib.contextmanager\ndef connection(path,seconds=1):\n'
                       ' c=sqlite3.connect("file:"+path+"?mode=ro",uri=True);c.row_factory=sqlite3.Row\n'
                       ' try: yield c\n finally: c.close()\n'
                       'def model_identity():\n s=regular(MODEL)\n'
                       ' return digest(encoded({"model_id":"bge-m3","dimensions":2,"device":s.st_dev,"inode":s.st_ino,"bytes":s.st_size,"mtime_ns":s.st_mtime_ns,"ctime_ns":s.st_ctime_ns}))\n').encode()
            with patch.dict(os.environ,{'NOX_OWNER_REQUEST_ID':'123','NOX_OWNER_SOURCE_SHA':'b'*40},clear=True), \
                 patch.object(a,'PYTHON',sys.executable),patch.object(a,'GATEWAY_SHA',a.digest(candidate)), \
                 patch.object(a,'BUNDLE',{'owner_s03_gateway.py':base64.b64encode(candidate).decode()}),patch.object(a,'emit'):
                result=a.identity_only_probe()
            self.assertEqual(before,db.read_bytes())
            observed=result['observation']
            self.assertEqual(observed['changed_stat_fields'],['ctime_ns'])
            self.assertTrue(observed['stored_stat_current_api_matches_index'])
            self.assertNotEqual(observed['current_model_identity'],old_identity)
            self.assertFalse(observed['vectors_relabelled']);self.assertFalse(observed['old_content_sha256_known'])
            changed=json.loads(json.dumps(observed));changed['indexed_identity_groups'][0]['model_identity']='PRIVATE_SENTINEL'
            with self.assertRaisesRegex(RuntimeError,'DIAGNOSTIC_GROUPS'):a.identity_projection(changed)


if __name__=='__main__':unittest.main()
