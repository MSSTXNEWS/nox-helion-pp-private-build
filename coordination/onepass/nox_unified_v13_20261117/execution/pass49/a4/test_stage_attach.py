import ast
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import tempfile
import time
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import nox_runpod.teacher_mesh.v135 as package
from nox_runpod.teacher_mesh.v135.resource_native_binding import ExistingTrainerBinding
import stage_existing_trainer as stage


class AttachTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.calls=[]
        self.original=dict(student_base_sha256='a'*64,student_shard_bytes=33,
            train_dataset_sha256='b'*64,holdout_dataset_sha256='c'*64,dev_dataset_sha256='d'*64)
        self.native_path=self.root/'native.json';self.native_path.write_text(json.dumps(self.original))
        tree=ast.parse((Path(__file__).parent/stage.REL/'train_full_base_zero3.py').read_text())
        nodes=ast.Module(body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='verify_owner'],type_ignores=[])
        self.digest=lambda n:hashlib.sha256(json.dumps(n,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        ns=dict(hmac=hmac,hashlib=hashlib,json=json,time=time,INSTANCE=60509551,_SHA=re.compile(r'^[0-9a-f]{64}$'),
            sha256_manifest=self.digest,fullbase_admission=lambda n:{'state':'READY_FOR_SIGNED_ONEHOST_TRAINING_START'})
        exec(compile(nodes,'actual_verify_owner','exec'),ns)
        self.fake=SimpleNamespace(_json=lambda p:json.loads(p.read_text()),SIGN_ENV='NOX_TEST_BINDING_SECRET',verify_owner=ns['verify_owner'],
            run=lambda args,**kwargs:self.calls.append((args,kwargs)) or 'existing-result')
        self.secret=b'synthetic-isolated-signature-key-32-bytes'
        self.env=patch.dict(os.environ,{self.fake.SIGN_ENV:self.secret.decode()});self.env.start()
        self.module=patch.object(package,'train_full_base_zero3',self.fake,create=True);self.module.start()
        self.receipt=dict(checkpoint_sha256='e'*64,cursor={'global_step':3})
    def tearDown(self): self.module.stop();self.env.stop();self.tmp.cleanup()
    def evidence(self,native):
        now=int(time.time());a=dict(action='nox.forge.fullbase.distill',instance_id=60509551,issued_at=now,expires_at=now+30,admission_sha256=self.digest(native))
        a['signature']=hmac.new(self.secret,json.dumps(a,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode(),hashlib.sha256).hexdigest()
        return {'native':native,'approval':a}
    def admitted(self):
        return {**self.original,'resource_pause_task_id':'6A03','resource_pause_checkpoint_sha256':'e'*64,'resource_pause_step':3}
    def binding(self,provider=None):
        return ExistingTrainerBinding('6A03',SimpleNamespace(native=str(self.native_path)),provider or (lambda r:self.evidence(self.admitted())))
    def test_no_training_until_existing_handler_calls_and_only_once(self):
        b=self.binding();self.assertEqual(self.calls,[])
        self.assertEqual(b.run_existing(),'existing-result');self.assertIs(self.calls[0][1]['resource_control'],b.control)
        with self.assertRaisesRegex(RuntimeError,'ALREADY_ENTERED'): b.run_existing()
        self.assertEqual(len(self.calls),1)
    def test_actual_hmac_readmission_accepts_bound_checkpoint(self):
        self.assertTrue(self.binding()._readmit(self.receipt))
    def test_concurrent_entry_calls_existing_handler_once(self):
        b=self.binding();barrier=threading.Barrier(8);errors=[]
        def enter():
            barrier.wait()
            try:b.run_existing()
            except RuntimeError as exc:errors.append(str(exc))
        threads=[threading.Thread(target=enter) for _ in range(8)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(2)
        self.assertEqual(len(self.calls),1);self.assertEqual(len(errors),7)
        self.assertTrue(all('ALREADY_ENTERED' in error for error in errors))
    def test_copied_across_process_refused_before_lock(self):
        b=self.binding()
        with patch('os.getpid',return_value=b._pid+1):
            with self.assertRaisesRegex(RuntimeError,'CROSSED_PROCESS'):b.run_existing()
        self.assertEqual(self.calls,[])
    def test_initial_admission_change_refused(self):
        b=self.binding();self.native_path.write_text('{}')
        with self.assertRaisesRegex(RuntimeError,'INITIAL_ADMISSION_CHANGED'):b.run_existing()
        self.assertEqual(self.calls,[])
    def test_unsigned_or_changed_signature_refused(self):
        e=self.evidence(self.admitted());e['approval']['signature']='0'*64
        with self.assertRaisesRegex(RuntimeError,'SIGNATURE'): self.binding(lambda r:e)._readmit(self.receipt)
    def test_signed_model_change_refused(self):
        n=self.admitted();n['student_base_sha256']='f'*64
        with self.assertRaisesRegex(RuntimeError,'MODEL_OR_CORPUS'): self.binding(lambda r:self.evidence(n))._readmit(self.receipt)
    def test_signed_wrong_checkpoint_refused(self):
        n=self.admitted();n['resource_pause_checkpoint_sha256']='f'*64
        with self.assertRaisesRegex(RuntimeError,'SAFE_POINT_BINDING'): self.binding(lambda r:self.evidence(n))._readmit(self.receipt)
    def test_expired_signed_admission_refused(self):
        e=self.evidence(self.admitted());e['approval']['expires_at']=int(time.time())-1
        e['approval']['issued_at']=e['approval']['expires_at']-30
        with self.assertRaisesRegex(RuntimeError,'EXPIRED'): self.binding(lambda r:e)._readmit(self.receipt)


class StageTests(unittest.TestCase):
    def test_mismatched_original_refused_without_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';(source/stage.REL).mkdir(parents=True)
            (source/stage.REL/'train_full_base_zero3.py').write_text('wrong source')
            with self.assertRaisesRegex(RuntimeError,'BLOB_MISMATCH'):stage.stage(source,root/'out')
            self.assertFalse((root/'out').exists())
    def test_existing_or_source_nested_output_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for output in (root,root/'inside'):
                with self.assertRaisesRegex(RuntimeError,'NEW_LOCAL_STAGE_ONLY'):stage.stage(root,output)
    def test_symlink_source_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'source').symlink_to(root,target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError,'NEW_LOCAL_STAGE_ONLY'):stage.stage(root/'source',root/'out')


if __name__=='__main__':unittest.main()
