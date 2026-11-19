import ast
from contextlib import redirect_stdout
import importlib.util
import io
import json
import math
from pathlib import Path
import types
import unittest
from unittest.mock import patch

HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('owner_training_scaler_probe',HERE/'owner_training_scaler_probe.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)
node=next(n for n in ast.parse(probe.CHILD).body if isinstance(n,ast.FunctionDef) and n.name=='project')
namespace={'math':math};exec(compile(ast.Module(body=[node],type_ignores=[]),'<numeric-projection>','exec'),namespace)
project=namespace['project']


class ScalerProbeTests(unittest.TestCase):
    def setUp(self):
        self.optimizer={'state':{},'param_groups':[{'params':[0,1,2]}]}
        self.scaler={'scale':2048.,'growth_factor':2.,'backoff_factor':.5,'growth_interval':2000,'_growth_tracker':0}
        self.hashes={name:'a'*64 for name in probe.FILES}

    def test_saved_backoff_scale_and_empty_optimizer_are_read_only_evidence(self):
        value=project(self.optimizer,self.scaler)
        self.assertEqual(value['optimizer_state_entries'],0);self.assertEqual(value['optimizer_parameter_count'],3)
        self.assertEqual(value['scaler']['scale'],2048.)
        self.assertEqual(self.scaler['scale'],2048.)
        self.scaler['scale']=.25
        self.assertEqual(project(self.optimizer,self.scaler)['scaler']['scale'],.25)

    def test_nonfinite_or_changed_state_is_rejected(self):
        for changed in ({'scale':float('nan')},{'scale':0},{'backoff_factor':1},{'_growth_tracker':-1}):
            with self.assertRaises(ValueError):project(self.optimizer,{**self.scaler,**changed})
        with self.assertRaises(ValueError):project({**self.optimizer,'state':{0:{}}},self.scaler)

    def test_native_child_uses_cpu_weights_only_and_exports_no_stderr(self):
        value={'schema':probe.SCHEMA,'state':probe.STATE,'checkpoint_global_step':5,
            'files_sha256':{name:self.hashes[name] for name in ('optimizer.pt','scaler.pt')},
            'cuda_initialized':False,'files_modified':False,**project(self.optimizer,self.scaler)}
        child=types.SimpleNamespace(returncode=0,stdout=json.dumps(value).encode(),stderr=b'PRIVATE_SENTINEL')
        with patch.object(probe.subprocess,'run',return_value=child) as run:
            self.assertEqual(probe.run_probe(probe.CHECKPOINT,self.hashes),value)
        kwargs=run.call_args.kwargs
        self.assertEqual(kwargs['env']['CUDA_VISIBLE_DEVICES'],'');self.assertEqual(kwargs['timeout'],45)
        calls=[n for n in ast.walk(ast.parse(probe.CHILD)) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
               and isinstance(n.func.value,ast.Name) and n.func.value.id=='torch' and n.func.attr=='load']
        self.assertEqual(len(calls),1)
        self.assertEqual({k.arg:ast.literal_eval(k.value) for k in calls[0].keywords},{'map_location':'cpu','weights_only':True})
        child.returncode=2;child.stdout=json.dumps({'state':'HOLD_SAVED_AMP_STATE_PREFLIGHT',
            'exception_class':'ValueError','failed_stage':'VALIDATE_SAVED_STATE',
            'reason_code':'SCALER_RANGE','numeric_observations':{'optimizer_is_dict':True,
            'parameter_counts':[3,0],'empty_parameter_groups':1}}).encode()
        output=io.StringIO()
        with patch.object(probe.subprocess,'run',return_value=child),redirect_stdout(output):
            with self.assertRaisesRegex(RuntimeError,'VALIDATE_SAVED_STATE_SCALER_RANGE') as caught:
                probe.run_probe(probe.CHECKPOINT,self.hashes)
        self.assertNotIn('PRIVATE_SENTINEL',str(caught.exception))
        self.assertNotIn('PRIVATE_SENTINEL',output.getvalue())
        self.assertEqual(json.loads(output.getvalue().split('=',1)[1])['data']['numeric_observations']['parameter_counts'],[3,0])

    def test_empty_decay_group_is_allowed_only_with_nonempty_unique_global_parameters(self):
        optimizer={'state':{},'param_groups':[{'params':[0,1,2]},{'params':[]}]}
        value=project(optimizer,self.scaler)
        self.assertEqual(value['optimizer_parameter_counts'],[3,0])
        self.assertEqual(value['optimizer_empty_parameter_groups'],1)
        self.assertEqual(value['optimizer_parameter_count'],3)
        self.assertEqual(optimizer['param_groups'][1]['params'],[])
        for groups in ([{'params':[]},{'params':[]}],[{'params':[0]},{'params':[0]}],
                       [{'params':[True]},{'params':[]}],[{'params':[-1]},{'params':[]}],
                       [{'params':[0]},{'params':None}]):
            with self.assertRaises(ValueError):project({'state':{},'param_groups':groups},self.scaler)

    def test_failure_projection_drops_unknown_text_and_exports_only_categories(self):
        failure={'state':'HOLD_SAVED_AMP_STATE_PREFLIGHT','exception_class':'UnpicklingError',
            'failed_stage':'LOAD_OPTIMIZER','reason_code':'UNCLASSIFIED_EXCEPTION','numeric_observations':{}}
        self.assertEqual(probe.safe_failure(failure),failure)
        for changed in ({'exception_message':'PRIVATE_SENTINEL'},
                        {'numeric_observations':{'raw_tensor':'PRIVATE_SENTINEL'}},
                        {'reason_code':'PRIVATE_SENTINEL'}):
            with self.assertRaisesRegex(RuntimeError,'OUTPUT'):probe.safe_failure({**failure,**changed})
        tree=ast.parse(probe.CHILD)
        reason=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='REASONS' for t in n.targets))
        codes=ast.literal_eval(reason.value)
        self.assertEqual(codes.get('PRIVATE_SENTINEL','UNCLASSIFIED_EXCEPTION'),'UNCLASSIFIED_EXCEPTION')
        self.assertNotIn('PRIVATE_SENTINEL',json.dumps(failure))

    def test_other_path_or_missing_hash_never_starts_child(self):
        with patch.object(probe.subprocess,'run',side_effect=AssertionError('scope bypass')):
            with self.assertRaisesRegex(RuntimeError,'SCOPE'):probe.run_probe(probe.CHECKPOINT.parent/'checkpoint-6',self.hashes)
            with self.assertRaisesRegex(RuntimeError,'SCOPE'):probe.run_probe(probe.CHECKPOINT,{})


if __name__=='__main__':unittest.main()
