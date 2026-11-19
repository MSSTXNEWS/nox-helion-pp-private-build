"""A pending recovery observer may not replay or substitute initial training."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent
def load(name):
    spec=importlib.util.spec_from_file_location('observe_test_'+name,HERE/(name+'.py'))
    module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module);return module
observer=load('owner_training_recovery_observe');recovery=load('owner_training_recovery_entry')


class ObserveTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.state=self.root/'state';self.state.mkdir()
        for module in (observer,recovery):
            for name,value in [('ROOT',self.root),('STATE',self.state)]:
                patched=patch.object(module,name,value);patched.start();self.addCleanup(patched.stop)
        patched=patch.object(recovery,'ENTRY',self.root/'hybrid.py');patched.start();self.addCleanup(patched.stop)
        sources={}
        for i in range(20):
            p=recovery.ENTRY if i==0 else self.root/('source'+str(i));raw=b'hybrid' if i==0 else str(i).encode()
            p.write_bytes(raw);sources[str(p)]=observer.digest(raw)
        patched=patch.object(recovery,'HYBRID_AFTER',sources[str(recovery.ENTRY)]);patched.start();self.addCleanup(patched.stop)
        self.identity={'pid':44,'starttime':'900','cuda':'1','service':observer.SERVICE}
        self.context={'request':'123456','source_sha':'a'*40,'receipt_sha256':''}
        pointer={'request':'123456','source_sha':'a'*40,'max_steps':5,'resume':False,'sources':sources}
        self.previous={'schema':'NOX_OWNER_TRAINING_RESUME_V1','request':'123456','source_sha':'a'*40,
            'state':'BOUNDED_TRAINING_RUNNING_ACCEPTANCE_PENDING','training_started':True,'optimizer_steps_verified':False,
            'admission':pointer,'unstarted_recovery':{'hybrid_before_sha256':recovery.HYBRID_BEFORE,
                'hybrid_after_sha256':recovery.HYBRID_AFTER,'preparation_sha256':recovery.PREPARATION_SHA,
                'dataset_bytes':recovery.DATASET_BYTES,'failed_admission':{'request':recovery.FAILED_REQUEST,'source_sha':recovery.FAILED_SOURCE},
                'configuration_preflight':{'state':'INSTALLED_CONFIG_AND_SERIALIZATION_VERIFIED','hybrid_sha256':recovery.HYBRID_AFTER}},
            'steps':[{'kind':'single_native_training_started','data':{'max_steps':5,'process':self.identity}}]}
        (self.state/'owner_training_admission.json').write_text(json.dumps(pointer));self.seal()

    def seal(self):
        raw=json.dumps(self.previous).encode();(self.state/'owner_maintenance_123456.json').write_bytes(raw)
        self.context['receipt_sha256']=observer.digest(raw)

    def test_exact_recovery_source_pin_and_pending_receipt(self):
        self.assertEqual(observer.digest((HERE/'owner_training_recovery_entry.py').read_bytes()),observer.RECOVERY_SHA)
        _,pointer,identity=observer.pending_evidence(recovery,self.context)
        self.assertEqual(pointer['max_steps'],5);self.assertEqual(identity,self.identity)

    def test_changed_pending_receipt_or_any_current_source_is_rejected(self):
        wrong={**self.context,'receipt_sha256':'0'*64}
        with self.assertRaisesRegex(RuntimeError,'RECEIPT_PIN'):observer.pending_evidence(recovery,wrong)
        (self.root/'source19').write_bytes(b'changed')
        with self.assertRaisesRegex(RuntimeError,'SOURCE_CHANGED'):observer.pending_evidence(recovery,self.context)

    def test_failed_or_already_continued_receipt_cannot_enter_observation(self):
        for state in ('HOLD_TRAINING_CONFIG_RECOVERY','FIVE_STEPS_VERIFIED_CONTINUATION_STARTED'):
            self.previous['state']=state;self.seal()
            with self.assertRaisesRegex(RuntimeError,'PENDING_REQUIRED'):observer.pending_evidence(recovery,self.context)

    def test_pid_reuse_and_different_run_arguments_are_not_accepted(self):
        native='a'*64
        args=['python','hybrid.py','--native-sha',native,'--max-steps','5','--planned-steps','1000','--recover-unstarted']
        helper=types.SimpleNamespace(process=lambda pid:{'argv':args})
        review=types.SimpleNamespace(NATIVE_SHA=native,prove_training=lambda helper:dict(self.identity))
        self.assertEqual(observer.same_initial_process(helper,review,self.identity),self.identity)
        with self.assertRaisesRegex(RuntimeError,'PROCESS_CHANGED'):
            observer.same_initial_process(helper,review,{**self.identity,'starttime':'899'})
        args.append('--resume')
        with self.assertRaisesRegex(RuntimeError,'PROCESS_ARGUMENTS'):observer.same_initial_process(helper,review,self.identity)

    def test_missing_owner_context_never_loads_or_starts_anything(self):
        import os
        with patch.dict(os.environ,{},clear=True),patch.object(observer,'load_recovery') as loader:
            with self.assertRaisesRegex(RuntimeError,'OWNER_CONTEXT'):observer.main(self.context)
            loader.assert_not_called()


if __name__=='__main__':unittest.main()
