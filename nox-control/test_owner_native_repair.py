import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('owner_native_repair',Path(__file__).with_name('owner_native_repair.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class HaltTests(unittest.TestCase):
    def row(self,pid=10,script=None):
        return {'pid':pid,'ppid':1,'pgrp':10,'state':'S','starttime':'100','cuda':'1',
                'service':m.SERVICE,'argv':['python',str(script or m.TRAINER)]}

    def test_signal_identity_rejects_pid_reuse_foreign_gpu_role_and_script(self):
        row=self.row()
        self.assertTrue(m.same_process(row,dict(row)))
        for change in ({'starttime':'101'},{'cuda':'0'},{'service':'nox-proxy'},
                       {'argv':['python','/root/unrelated.py']}):
            self.assertFalse(m.same_process(row,{**row,**change}))
        self.assertFalse(m.same_process(row,None))

    def test_hold_is_durable_before_stop_and_never_starts_training(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);wrapper=root/'scripts/run_train_volta_t866u.sh';trainer=root/'scripts/train_qlora_35b_t866u.py'
            wrapper_row=self.row(script=wrapper);wrapper_row['argv']=['bash',str(wrapper)]
            child=self.row(11,trainer);child['ppid']=10
            calls=[]
            def command(args,timeout=12):
                self.assertTrue((root/'state/TRAIN_HOLD.flag').is_file())
                calls.append(args);return 0,''
            with patch.multiple(m,ROOT=root,WRAPPER=wrapper,TRAINER=trainer), \
                 patch.dict(os.environ,{'NOX_OWNER_REQUEST_ID':'123','NOX_OWNER_SOURCE_SHA':'a'*40}), \
                 patch.object(m,'health',return_value={'8080':200,'8081':200,'8082':200}), \
                 patch.object(m,'gpu',return_value={'rc':0,'gpus':[{'index':1,'used_mib':0,'free_mib':32000,'utilization':0}]}), \
                 patch.object(m,'progress',return_value={'global_step':0}), \
                 patch.object(m,'verify_sources',return_value={'stopasgroup':'true','killasgroup':'true'}), \
                 patch.object(m,'service_state',side_effect=[{'state':'RUNNING','pid':10},{'state':'STOPPED','pid':None}]), \
                 patch.object(m,'process_table',side_effect=[{10:wrapper_row,11:child},{}]), \
                 patch.object(m,'process',return_value=None), \
                 patch.object(m,'command',side_effect=command),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(m.main(),0)
            self.assertEqual(calls,[['supervisorctl','stop',m.SERVICE]])
            receipt=json.loads((root/'state/owner_maintenance_123.json').read_text())
            self.assertTrue(receipt['halt_verified']);self.assertTrue(receipt['hold_retained'])
            self.assertFalse(receipt['training_started']);self.assertEqual(receipt['weights_deleted'],0)

if __name__=='__main__':unittest.main()
