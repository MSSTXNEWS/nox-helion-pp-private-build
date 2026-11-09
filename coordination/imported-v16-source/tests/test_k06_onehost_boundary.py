"""Actual OneHost/S03 route composition on CPU; no Windows/GPU acceptance claim."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import uuid
from dataclasses import asdict

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'Packages/P02/worker-python'))
sys.path.insert(0,str(ROOT/'Packages/P03/Source/python-host'))
if 'nox_native_bridge' not in sys.modules:
    spec=importlib.util.spec_from_file_location('nox_native_bridge',ROOT/'proposals/NOX-PACK01-50/native_bridge.py')
    m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
from nox_selfbuilder.onehost_store import OneHostStoreActor
from nox_selfbuilder.background_forge import ForgeJob
from helion.storage import Store

class Client:
    def models(self):return []
    def stream(self,*args,**kwargs):return iter(())
    def stop(self,*args,**kwargs):return True

class OneHostForgeBoundary(unittest.TestCase):
    def test_configured_native_job_reaches_existing_queue_and_actual_preflight(self):
        import os
        if os.name=='nt':self.skipTest('CPU-only unavailable Windows GPU boundary')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'helion').mkdir();p04=root/'Packages/P04';p04.mkdir(parents=True)
            for name in ('train_qlora.py','preflight_local_gpu.py','merge_qlora_adapter.py'):
                shutil.copyfile(ROOT/'Packages/P04'/name,p04/name)
            host=root/'helion/e06_native_stdio_owner.py'
            shutil.copyfile(ROOT/'coordination/e06/e06_native_stdio_owner.py',host)
            spec=importlib.util.spec_from_file_location('_k06_actual_onehost',host)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            data=root/'data';data.mkdir();forge=root/'forge';forge.mkdir();model=root/'model';model.mkdir()
            for name in ('lock','manifest','verify','train','holdout'):(root/name).write_text('{}')
            job=ForgeJob('training-run','P04-task',model,root/'lock','a'*40,root/'manifest',root/'verify',root/'train',root/'holdout',forge/'result')
            row={k:str(v) if isinstance(v,Path) else v for k,v in asdict(job).items()}
            (data/'onehost-native-config.json').write_text(json.dumps({'version':1,'forge_root':str(forge),'forge_jobs':[row]}))
            with OneHostStoreActor(lambda:Store(data/'helion.sqlite3')) as actor:
                ingress=module.create_existing_ingress(actor,'native-run',client=Client(),native_approve=lambda *_:True,data_dir=data)
                def request(route,payload):
                    frame={'protocol':'NOX-P02-NATIVE-v1','requestId':uuid.uuid4().hex,'route':route,'payload':payload,'runId':'native-run'}
                    return json.loads(ingress.handle(json.dumps(frame).encode()))
                response=request('training.start',{'job_id':'training-run'})
                self.assertIn('QUEUED',json.dumps(response))
                ingress.close()
                rows=actor.call(lambda store:store.conn.execute("SELECT metadata FROM audit WHERE action='NOX_NATIVE_WORK_RESULT' ORDER BY id DESC LIMIT 1").fetchall())
                self.assertEqual(json.loads(rows[0][0])['result']['reason'],'GPU_TRAINING_HOLD')
                self.assertFalse((forge/'result').exists())
                stop=request('chat.stop',{})
                self.assertTrue(ingress.p02.stop_requested())
                self.assertNotIn('error',stop)

if __name__=='__main__':unittest.main()
