"""Real original Store + current native ingress; Ollama is an explicit fixture."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
import uuid
from helion.storage import Store
from nox_selfbuilder.onehost_store import OneHostStoreActor

REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'Packages/P02/worker-python'))
bridge_spec=importlib.util.spec_from_file_location('nox_native_bridge',REPO/'proposals/NOX-PACK01-50/native_bridge.py')
bridge=importlib.util.module_from_spec(bridge_spec);sys.modules[bridge_spec.name]=bridge;bridge_spec.loader.exec_module(bridge)
from p02_native_ingress import ProtocolHold

class FixtureOllama:
    def models(self):return ['fixture:model']
    def stream(self,model,messages):
        yield {'delta':'fixture reply','done':True}
    def stop(self):pass

class OneHostIntegration(unittest.TestCase):
    def test_native_routes_restore_isolate_and_reject_identity_claim(self):
        with tempfile.TemporaryDirectory() as d:
            runtime=Path(d);(runtime/'helion').mkdir();(runtime/'assets').mkdir()
            owner=runtime/'helion/e06_native_stdio_owner.py'
            shutil.copyfile(REPO/'coordination/e06/e06_native_stdio_owner.py',owner)
            seed=runtime/'assets/NOX_SOUL_CPU_REAL_WEIGHTS_TRAINED_V1_20261022.zip'
            seed_source=REPO/'assets'/seed.name
            if not seed_source.is_file():seed_source=REPO.parent/'donors/r4/assets'/seed.name
            shutil.copyfile(seed_source,seed)
            seed_sha=hashlib.sha256(seed.read_bytes()).hexdigest()
            spec=importlib.util.spec_from_file_location('k02_owner_fixture',owner)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            path=runtime/'helion.sqlite3'
            def request(ingress,route,payload):
                return json.loads(ingress.handle(json.dumps({'protocol':'NOX-P02-NATIVE-v1',
                    'requestId':uuid.uuid4().hex,'route':route,'payload':payload,'runId':'K02-INTEGRATION'}).encode()))['result']
            scope={'core_id':'core.atlas','persona_id':'persona.kairen_voss'}
            with OneHostStoreActor(lambda:Store(path)) as actor:
                ingress=module.create_existing_ingress(actor,'K02-INTEGRATION',client=FixtureOllama(),native_approve=lambda *_:True)
                state=request(ingress,'chat.model',{'model':'fixture:model'})
                self.assertEqual(state['lineage']['S03'],'ORIGINAL_STORE_READY')
                response=request(ingress,'helion.chat',{**scope,'text':'remember this'})
                self.assertEqual(response['answer'],'fixture reply')
                self.assertEqual(len(request(ingress,'chat.history',scope)['messages']),2)
                self.assertEqual(request(ingress,'chat.history',{'core_id':'core.core','persona_id':scope['persona_id']})['messages'],[])
                self.assertEqual(request(ingress,'chat.history',{**scope,'persona_id':'persona.adrian_marrow'})['messages'],[])
                with self.assertRaises(ProtocolHold):
                    request(ingress,'chat.history',{'principal':'other'})
                self.assertTrue(request(ingress,'chat.stop',{})['stopRequested'])
            with OneHostStoreActor(lambda:Store(path)) as actor:
                ingress=module.create_existing_ingress(actor,'K02-INTEGRATION',client=FixtureOllama(),native_approve=lambda *_:True)
                self.assertEqual(request(ingress,'chat.history',scope)['messages'][0]['content'],'remember this')
                self.assertEqual(request(ingress,'chat.history',{})['messages'],[])
            self.assertEqual(hashlib.sha256(seed.read_bytes()).hexdigest(),seed_sha)

if __name__=='__main__':unittest.main()
