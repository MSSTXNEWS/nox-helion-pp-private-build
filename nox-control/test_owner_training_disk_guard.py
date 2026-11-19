import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('owner_training_disk_guard',HERE/'owner_training_disk_guard.py')
g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);self.root=root;self.state=root/'state';self.output=root/'lora/qlora_t866u/runs_owner_hybrid'
        self.state.mkdir();self.output.mkdir(parents=True);(root/'scripts').mkdir()
        for name,value in {'ROOT':root,'STATE':self.state,'OUTPUT':self.output,
                           'HYBRID':root/'scripts/hybrid_training_entry.py','STATUS':self.state/'guard.json'}.items():
            p=patch.object(g,name,value);p.start();self.addCleanup(p.stop)
        self.lineage={'schema':'NOX_T866U_FP32_ADAPTER_CONTINUATION_V1','native_sha256':g.NATIVE_SHA,
                      'targets':{'trainable_parameters':10_000_000,'trainable_dtype':'float32'},
                      'training_config':{'optimizer':'paged_adamw_8bit'}}
        cp=self.output/'checkpoint-5';cp.mkdir()
        for name in g.NAMES:(cp/name).write_bytes(b'fixture')
        self.first={'schema':'NOX_T866U_FP32_ADAPTER_CONTINUATION_V1','global_step':5,'adapter_delta_verified':True,
                    'lineage_sha256':g.json_sha(self.lineage),'checkpoint':{'path':str(cp),
                    'files_sha256':{name:g.digest((cp/name).read_bytes()) for name in g.NAMES}}}
        self.pointer={'schema':'NOX_OWNER_TRAINING_ADMISSION_V1','request':'123','source_sha':'a'*40,
                      'max_steps':1000,'resume':True,'sources':{}}
        for path in (g.HYBRID,root/'scripts/run_train_volta_t866u.sh',self.state/'train_cpu_max.env'):
            path.write_bytes(b'approved source');self.pointer['sources'][str(path)]=g.digest(path.read_bytes())
        p=patch.object(g,'HYBRID_SHA',g.digest(b'approved source'));p.start();self.addCleanup(p.stop)
        self.sealed={'schema':'NOX_OWNER_TRAINING_RESUME_V1','request':'123','source_sha':'a'*40,
                     'state':'FIVE_STEPS_VERIFIED_CONTINUATION_STARTED','optimizer_steps_verified':True,
                     'admission':self.pointer,'five_step_receipt':self.first}
        self.write(self.output/'owner_lineage.json',self.lineage)
        self.write(self.state/'owner_training_admission.json',self.pointer)
        self.write(self.state/'task_boost_mode.json',{'training_allowed':True,'training_service':g.SERVICE})
        self.write(self.state/'owner_maintenance_123.json',self.sealed)
        self.context={'request':'123','source_sha':'a'*40,'receipt_sha256':g.digest((self.state/'owner_maintenance_123.json').read_bytes())}

    def write(self,path,value):path.write_text(json.dumps(value))

    def test_only_sealed_1000_continuation_is_admitted(self):
        pointer,lineage,first=g.admission(self.context);self.assertEqual(pointer,self.pointer)
        self.pointer['max_steps']=5;self.write(self.state/'owner_training_admission.json',self.pointer)
        with self.assertRaisesRegex(RuntimeError,'INITIAL_CONTINUATION'):g.admission(self.context)

    def test_lineage_and_sources_cannot_silently_change_budget(self):
        changed=copy.deepcopy(self.lineage);changed['targets']['trainable_parameters']=1
        self.write(self.output/'owner_lineage.json',changed)
        with self.assertRaisesRegex(RuntimeError,'LINEAGE_CHANGED'):g.admission(self.context)

    def test_budget_reserves_two_full_checkpoints_and_four_gib(self):
        value=g.checkpoint_budget(self.lineage,self.first)
        self.assertEqual(value['checkpoint_budget_bytes'],16*10_000_000+128*1024**2)
        self.assertEqual(value['required_free_bytes'],4*1024**3+2*value['checkpoint_budget_bytes']+256*1024**2)
        self.assertEqual(value['observed_checkpoint_bytes'],7*len(b'fixture'))

    def test_adequate_space_keeps_training_and_preserves_checkpoints(self):
        paths={p:p.read_bytes() for p in (self.output/'checkpoint-5').iterdir()}
        with patch.object(g,'trainer_process',return_value={'pid':77,'starttime':99}), \
             patch.object(g.os,'statvfs',return_value=types.SimpleNamespace(f_bavail=20*1024**3,f_frsize=1)):
            result=g.tick(self.context)
        self.assertEqual(result['state'],'CHECKPOINT_DISK_HEADROOM_ADMITTED')
        self.assertFalse((self.state/'TRAIN_PAUSE_REQUEST.flag').exists())
        self.assertEqual(paths,{p:p.read_bytes() for p in paths})

    def test_low_space_requests_checkpoint_pause_once_never_kills_or_deletes(self):
        with patch.object(g,'trainer_process',return_value={'pid':77,'starttime':99}), \
             patch.object(g.os,'statvfs',return_value=types.SimpleNamespace(f_bavail=5*1024**3,f_frsize=1)):
            # This fixture's threshold is about4.80GiB, so use one byte below it.
            threshold=g.checkpoint_budget(self.lineage,self.first)['required_free_bytes']
            with patch.object(g.os,'statvfs',return_value=types.SimpleNamespace(f_bavail=threshold-1,f_frsize=1)):
                result=g.tick(self.context);again=g.tick(self.context)
        self.assertEqual(result['state'],'CHECKPOINT_PAUSE_REQUESTED')
        self.assertEqual(again['state'],'EXISTING_TRAINING_PAUSE_RETAINED')
        flag=self.state/'TRAIN_PAUSE_REQUEST.flag';self.assertEqual(flag.stat().st_mode&0o777,0o600)
        self.assertEqual(len(list((self.output/'checkpoint-5').iterdir())),7)
        self.assertFalse(result['trainer_signalled']);self.assertEqual(result['checkpoints_deleted'],0)

    def test_foreign_pause_and_owner_maintenance_are_never_overwritten(self):
        pause=self.state/'TRAIN_PAUSE_REQUEST.flag';pause.write_bytes(b'owner media pause')
        with patch.object(g,'trainer_process',return_value={'pid':77,'starttime':99}), \
             patch.object(g.os,'statvfs',return_value=types.SimpleNamespace(f_bavail=1,f_frsize=1)):
            self.assertEqual(g.tick(self.context)['state'],'EXISTING_TRAINING_PAUSE_RETAINED')
        self.assertEqual(pause.read_bytes(),b'owner media pause')
        import fcntl
        fd=os.open(self.state/'owner_maintenance.lock',os.O_RDWR|os.O_CREAT,0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(g.tick(self.context)['state'],'OWNER_MAINTENANCE_ACTIVE')
        finally:os.close(fd)

    def test_existing_boost_noop_still_runs_guard_first(self):
        order=[];ns={'apply_protect_and_preempt':lambda *a,**k:order.append('existing') or [{'owner_scoped_control':True}]}
        with patch.object(g,'tick',side_effect=lambda c:order.append('disk') or {'state':'OBSERVED'}):
            g.bind_scheduler(ns,self.context);result=ns['apply_protect_and_preempt'](0,{},False,False)
        self.assertEqual(order,['disk','existing']);self.assertIn('training_disk_guard',result[-1])

    def test_exact_transform_has_no_signal_or_trainer_source_mutation(self):
        source='def main(): pass\nif __name__ == "__main__":\n    main()\n'
        changed=g.patch_scheduler(source,g.digest(source.encode()),self.context)
        self.assertEqual(changed.replace(g.binding_text(self.context),''),source)
        with self.assertRaisesRegex(RuntimeError,'PREIMAGE'):g.patch_scheduler(source,'0'*64,self.context)
        self.assertNotIn('os.kill',Path(g.__file__).read_text())


if __name__=='__main__':unittest.main()
