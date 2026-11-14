"""Source boundary tests; fixtures do not attest an actual P03/GPU import."""
import importlib.util
import sys
from pathlib import Path
import unittest
from nox_selfbuilder.p04_forge_bridge import ExistingP04ModelTransaction, ForgeHold

ROOT = Path(__file__).resolve().parents[1]
if 'nox_native_bridge' not in sys.modules:
    spec = importlib.util.spec_from_file_location('nox_native_bridge', ROOT/'proposals/NOX-PACK01-50/native_bridge.py')
    module=importlib.util.module_from_spec(spec); sys.modules[spec.name]=module; spec.loader.exec_module(module)
sys.path.insert(0, str(ROOT/'Packages/P02/worker-python'))
from p02_onehost import OneHostP02
from nox_native_bridge import NativeSession

class Memory:
    def history(self,*a,**k): return []
    def add_message(self,*a,**k): pass
    def add_exchange(self,*a,**k): pass
    def store_file(self,*a,**k): pass
    def assert_model_switch_safe(self): pass
    def lineage_status(self): return {'status':'FIXTURE_ONLY'}
class Client:
    def stream(self,*a,**k): return iter(())
    def stop(self,*a,**k): return True
    def models(self): return ['base:local','tuned:local']

class ModelTransactionTests(unittest.TestCase):
    def setUp(self):
        self.scope=NativeSession('tenant','principal','chat')
        self.api=OneHostP02(Memory(),client=Client())
        self.api.list_models(self.scope,{'model':'base:local'})
        self.records={};self.digests={'base:local':'a'*64,'tuned:local':'b'*64}
        self.attestation={'status':'VERIFIED','merged_payload_sha256':'c'*64,'model_tag':'tuned:local','model_digest':'b'*64}
        self.allow=True
        self.tx=ExistingP04ModelTransaction(self.api,
            native_approve=lambda scope,action,args:self.allow,
            verify_import=lambda scope,sha:self.attestation,
            model_digest=lambda scope,tag:self.digests[tag],
            record_transaction=lambda scope,id,record:self.records.__setitem__(id,dict(record)),
            load_transaction=lambda scope,id:self.records.get(id))

    def test_unverified_hf_import_does_not_change_existing_model(self):
        self.attestation=None
        result=self.tx.activate(self.scope,transaction_id='tx1',merged_payload_sha256='c'*64)
        self.assertEqual(result['status'],'HOLD')
        self.assertEqual(self.api.selected_model(),'base:local')
        self.assertEqual(self.records,{})

    def test_same_existing_p02_select_and_explicit_rollback(self):
        result=self.tx.activate(self.scope,transaction_id='tx1',merged_payload_sha256='c'*64)
        self.assertEqual(result['status'],'SELECTED_PENDING_NATIVE_E07')
        self.assertEqual(self.api.selected_model(),'tuned:local')
        self.allow=False
        with self.assertRaises(ForgeHold):self.tx.rollback(self.scope,transaction_id='tx1')
        self.allow=True
        result=self.tx.rollback(self.scope,transaction_id='tx1')
        self.assertEqual(result['status'],'PREVIOUS_MODEL_SELECTION_RESTORED')
        self.assertEqual(self.api.selected_model(),'base:local')
        self.assertFalse(result['native_inference_verified'])

    def test_changed_previous_digest_denies_rollback(self):
        self.tx.activate(self.scope,transaction_id='tx1',merged_payload_sha256='c'*64)
        self.digests['base:local']='d'*64
        with self.assertRaises(ForgeHold):self.tx.rollback(self.scope,transaction_id='tx1')
        self.assertEqual(self.api.selected_model(),'tuned:local')

    def test_stop_during_model_selection_restores_previous_before_unlock(self):
        original=self.api.list_models
        def revoke(scope,args):
            result=original(scope,args)
            if args.get('model')=='tuned:local':self.api._stop_epoch+=1
            return result
        self.api.list_models=revoke
        with self.assertRaisesRegex(ForgeHold,'REVOKED_DURING_SELECTION'):
            self.tx.activate(self.scope,transaction_id='tx1',merged_payload_sha256='c'*64)
        self.assertEqual(self.api.selected_model(),'base:local')
        self.assertEqual(self.records['tx1']['status'],'PREVIOUS_MODEL_SELECTION_RESTORED')

    def test_duplicate_transaction_cannot_replace_rollback_identity(self):
        self.tx.activate(self.scope,transaction_id='tx1',merged_payload_sha256='c'*64)
        with self.assertRaises(ForgeHold):self.tx.activate(self.scope,transaction_id='tx1',merged_payload_sha256='c'*64)
        self.assertEqual(self.records['tx1']['previous_model'],'base:local')

if __name__=='__main__':unittest.main()
