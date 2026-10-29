import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

import p04_owner_training_port as m

class Running:
    def poll(self): return None

class Tests(unittest.TestCase):
    def setUp(self):
        d=tempfile.TemporaryDirectory();self.addCleanup(d.cleanup);self.root=Path(d.name)
        self.worker=self.root/'train_qlora.py';self.worker.write_text('# original test pinned byte fixture')
        self.receipt=self.root/'receipt.json'
        self.raw=json.dumps({'status':'COMPLETED','training':{'evaluation_status':'VALID','baseline_eval_loss':2.0,'adapter_eval_loss':1.0}}).encode()
        self.receipt.write_bytes(self.raw)
        self.allow=True;self.stopped=False;self.sent=[]
        self.arguments=('model','model-lock','model-revision','dataset-manifest','rights-verifier','train-jsonl','holdout-jsonl','output-dir','events-jsonl','run-id','task-id','stop-marker')
        self.args=[]
        for k in self.arguments:
            val='a'*40 if k=='model-revision' else 'NOX-P04-20261030' if k in ('run-id','task-id') else '/native/'+k
            self.args.extend(('--'+k,val))
        self.plan=m.NativeQLoRAPlan(Path(sys.executable),self.worker,hashlib.sha256(self.worker.read_bytes()).hexdigest(),tuple(self.args),'NOX-P04-20261030')
        self.port=m.P04OriginalTrainingPorts(select_plan=lambda _s:self.plan,
            select_receipt=lambda _s:(self.receipt,hashlib.sha256(self.raw).hexdigest()),
            permission=lambda _s,_route:self.allow,stop=lambda:self.stopped,
            launcher=lambda argv:self.sent.append(argv) or Running())
    def test_real_original_cli_selected_without_second_trainer(self):
        out=self.port.start('session',{})
        self.assertEqual(out['status'],'ORIGINAL_QLORA_PROCESS_STARTED_NOT_TRAINED')
        self.assertFalse(out['accepted']);self.assertEqual(self.sent[0][1],str(self.worker))
    def test_no_page_args(self):
        with self.assertRaises(m.P04Denied):self.port.start('session',{'--output-dir':'C:/attack'})
    def test_no_consent(self):
        self.allow=False
        with self.assertRaises(m.P04Denied):self.port.start('session',{})
    def test_stop(self):
        self.stopped=True
        with self.assertRaises(m.P04Denied):self.port.start('session',{})
    def test_worker_hash_drift(self):
        self.worker.write_text('tampered')
        with self.assertRaises(m.P04Hold):self.port.start('session',{})
    def test_missing_required_flags(self):
        self.plan=m.NativeQLoRAPlan(self.plan.python_exe,self.worker,self.plan.worker_sha256,self.plan.argv_pairs[:-2],self.plan.run_id)
        with self.assertRaises(m.P04Hold):self.port.start('session',{})
    def test_duplicate_cli_key(self):
        self.plan=m.NativeQLoRAPlan(self.plan.python_exe,self.worker,self.plan.worker_sha256,self.plan.argv_pairs+('--run-id','NOX-P04-20261030'),self.plan.run_id)
        with self.assertRaises(m.P04Hold):self.port.start('session',{})
    def test_real_receipt_evaluation_not_accepted(self):
        result=self.port.evaluate('session',{})
        self.assertEqual(result['status'],'VALID');self.assertTrue(result['improved']);self.assertFalse(result['accepted'])
    def test_no_receipt_path_from_web(self):
        with self.assertRaises(m.P04Denied):self.port.evaluate('session',{'path':'../../secret'})
    def test_wrong_sha_hold(self):
        self.receipt.write_bytes(b'changed')
        with self.assertRaises(m.P04Hold):self.port.evaluate('session',{})
    def test_weak_evaluation_no_success(self):
        raw=json.dumps({'training':{'evaluation_status':'VALID','baseline_eval_loss':0.5,'adapter_eval_loss':0.9}}).encode()
        self.receipt.write_bytes(raw)
        self.port._receipt=lambda s:(self.receipt,hashlib.sha256(raw).hexdigest())
        result=self.port.evaluate('session',{})
        self.assertFalse(result['improved']);self.assertFalse(result['accepted'])


    def test_register_exact_onehost_native_and_receipt_not_accepted(self):
        import native_bridge as bridge
        catalog=json.loads((Path(__file__).with_name("catalog.json")).read_text("utf-8"))
        host=bridge.NoxPackHost(catalog,native_approve=lambda *_:True)
        routes=self.port.register(host,receipt="a"*64)
        self.assertEqual(routes,frozenset(("training.start","training.evaluate")))
        self.assertEqual(set(host.ports),set(routes))
        session=bridge.NativeSession("t","p","c",allowed=routes,private_approved=routes)
        result=host.execute("training.evaluate",{},session)
        self.assertEqual(result["status"],"VALID")
        self.assertIs(result["accepted"],False)
        with self.assertRaises(bridge.HostDenied):
            self.port.register(host,receipt="a"*64)

    def test_register_no_native_approve_fails_atomically(self):
        import native_bridge as bridge
        catalog=json.loads((Path(__file__).with_name("catalog.json")).read_text("utf-8"))
        host=bridge.NoxPackHost(catalog)
        with self.assertRaises(bridge.HostHold):
            self.port.register(host,receipt="a"*64)
        self.assertEqual(host.ports,{})

if __name__=='__main__':unittest.main()
