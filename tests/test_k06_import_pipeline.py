"""P04/P03 receipt/S03/P02 boundary fixture; not GPU or actual import proof."""
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch
import test_k06_forge_integration as forge_fixture
import test_k06_model_transaction as model_fixture
from nox_selfbuilder.p04_forge_bridge import ExistingP04Pipeline, ForgeHold
from nox_selfbuilder.onehost_store import OneHostStoreActor
from nox_selfbuilder.onehost_queue import NativeWorkQueue
from helion.storage import Store

class ImportPipelineTests(unittest.TestCase):
    setUp = forge_fixture.ForgeIntegrationTests.setUp

    def prepare_files(self):
        t=self.owner.trainer;out=self.job.output_dir;out.mkdir()
        self.job.model_lock.write_text('{"model_id":"local"}')
        self.job.train_jsonl.write_text('{"text":"train"}')
        self.job.holdout_jsonl.write_text('{"text":"holdout"}')
        adapter=out/'adapter';adapter.mkdir();(adapter/'weights').write_bytes(b'fixture-adapter')
        cp=out/'checkpoints/checkpoint-10';cp.mkdir(parents=True)
        (cp/'trainer_state.json').write_text('{"global_step":10}')
        for name in ('optimizer.pt','scheduler.pt','rng_state.pth','adapter_model.bin'):(cp/name).write_bytes(b'fixture-state')
        receipt={'schema':t.RECEIPT_SCHEMA,'run_id':'run1','status':'COMPLETED',
            'model':{'id':'local','revision':'a'*40,'snapshot_sha256':t.sha256_tree(self.model)},
            'dataset':{'train_sha256':t.sha256_file(self.job.train_jsonl),'holdout_sha256':t.sha256_file(self.job.holdout_jsonl),
                       'rights_attestation_id':'rights-fixture','rights_attestation_sha256':'d'*64},
            'checkpoint':{'status':'HASHED','path':'checkpoints/checkpoint-10','step':10,'tree_sha256':t.sha256_tree(cp)},
            'adapter_sha256':t.sha256_tree(adapter),'training':{'global_step':10,'evaluation_status':'VALID','train_loss':1.,'baseline_eval_loss':2.,'adapter_eval_loss':1.}}
        t.write_training_receipt(out,receipt)
        merged=out.parent/(self.job.run_id+'.merged');merged.mkdir()
        (merged/'model.safetensors').write_bytes(b'fixture-tensor-file-not-a-real-model')
        (merged/'config.json').write_text('{}')
        tree=t.sha256_tree(merged)
        merge={'schema':'NOX-QLORA-MERGE-RECEIPT-v1','status':'CREATED','merged_payload_sha256':tree,
               'training_receipt_sha256':t.sha256_file(out/'training-receipt.json'),'adapter_sha256':receipt['adapter_sha256'],
               'model_snapshot_sha256':receipt['model']['snapshot_sha256'],'baseline_eval_loss':2.,'adapter_eval_loss':1.}
        (merged/'merge-receipt.json').write_text(json.dumps(merge))
        receipts=self.root/'receipts';receipts.mkdir();id=uuid.uuid4().hex
        imported={'schema':'NOX_P03_INSTALL_RECEIPT_V1','operation':'safetensors-import','jobId':id,
                  'mergedPayloadSha256':tree,'localSha256':tree,'mergeReceiptSha256':t.sha256_file(merged/'merge-receipt.json'),
                  'trainingReceiptSha256':t.sha256_file(out/'training-receipt.json'),'rightsAttestationId':'rights-fixture',
                  'rightsAttestationSha256':'d'*64,'nativeApprovalId':'native-fixture','modelTag':'tuned:local','ollamaDigest':'sha256:'+'b'*64,
                  'importedFiles':[{'path':p.name,'sha256':t.sha256_file(p),'sizeBytes':p.stat().st_size} for p in sorted(merged.iterdir()) if p.name!='merge-receipt.json']}
        file=receipts/(id+'.json');file.write_text(json.dumps(imported))
        return receipts,file,merged

    def test_real_receipt_bytes_s03_import_record_and_p02_rollback(self):
        receipts,file,merged=self.prepare_files()
        scope=model_fixture.NativeSession('local','principal','chat')
        api=model_fixture.OneHostP02(model_fixture.Memory(),client=model_fixture.Client())
        api.list_models(scope,{'model':'base:local'})
        digest=lambda scope,tag:{'base:local':'a'*64,'tuned:local':'b'*64}[tag]
        with OneHostStoreActor(lambda:Store(self.root/'helion.sqlite3')) as actor:
            queue=NativeWorkQueue(actor,authorize=lambda *_:True,stop_requested=lambda:False)
            service=ExistingP04Pipeline(self.owner,queue,api,job_resolver=lambda *_:self.job,
                authorize=lambda *_:True,model_digest=digest,receipt_root=receipts)
            result=service.command(scope,{'action':'training.import.record','job_id':'run1','receipt_path':str(file)})
            self.assertEqual(result['status'],'IMPORTED_NOT_ACTIVATED')
            self.assertEqual(api.selected_model(),'base:local')
            result=service.command(scope,{'action':'training.activate','job_id':'run1'})
            self.assertEqual(result['status'],'SELECTED_PENDING_NATIVE_E07')
            self.assertEqual(api.selected_model(),'tuned:local')
            # Restored queue reads existing original S03 transaction, no second database.
            restored=NativeWorkQueue(actor,authorize=lambda *_:True,stop_requested=lambda:False)
            service.queue=restored
            result=service.command(scope,{'action':'training.rollback','job_id':'run1'})
            self.assertEqual(result['status'],'PREVIOUS_MODEL_SELECTION_RESTORED')
            self.assertEqual(api.selected_model(),'base:local')
            queue.close();restored.close()

    def test_imported_file_drift_rejected_before_selection(self):
        receipts,file,merged=self.prepare_files()
        scope=model_fixture.NativeSession('local','principal','chat')
        api=model_fixture.OneHostP02(model_fixture.Memory(),client=model_fixture.Client())
        with OneHostStoreActor(lambda:Store(self.root/'helion.sqlite3')) as actor:
            queue=NativeWorkQueue(actor,authorize=lambda *_:True,stop_requested=lambda:False)
            service=ExistingP04Pipeline(self.owner,queue,api,job_resolver=lambda *_:self.job,
                authorize=lambda *_:True,model_digest=lambda *_:'b'*64,receipt_root=receipts)
            (merged/'model.safetensors').write_bytes(b'modified')
            with self.assertRaises(ForgeHold):
                service.command(scope,{'action':'training.import.record','job_id':'run1','receipt_path':str(file)})
            self.assertIsNone(api.selected_model());queue.close()

if __name__=='__main__':unittest.main()
