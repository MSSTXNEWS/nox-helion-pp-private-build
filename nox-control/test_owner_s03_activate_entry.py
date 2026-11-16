import ast
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
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


if __name__=='__main__':unittest.main()
