"""CPU-only contract tests. No Vast access and NO inference about live GPU training."""
import copy
import hashlib
import io
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import torch
from overnight_forge import HostPorts, production_admission, train_segment, _digest_model

class Toy(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.emb=torch.nn.Embedding(12,8)
        self.head=torch.nn.Linear(8,12)
    def forward(self,input_ids,labels):
        x=self.head(self.emb(input_ids))
        return type('Output',(),{'loss':torch.nn.functional.cross_entropy(x.flatten(0,1),labels.flatten())})()

class NightTests(unittest.TestCase):
    def setUp(self):
        torch.manual_seed(2026)
        self.model=Toy();self.opt=torch.optim.AdamW(self.model.parameters(),lr=0.03,weight_decay=0.0)
        self.base=copy.deepcopy(self.model.state_dict());self.baseline=_digest_model(self.model)
        self.stop=False;self.approved=True;self.saved={};self.records=[]
        def holdout(model):
            model.eval()
            with torch.no_grad():
                ids=torch.tensor([[1,1,1,1],[2,2,2,2]])
                # independent examples from train stream, same underlying token mapping
                labels=torch.tensor([[3,3,3,3],[4,4,4,4]])
                value=model(ids,labels).loss.item()
            model.train()
            return {'verified':True,'loss':value,'regression_pass':True}
        def checkpoint(m,o,info):
            f=io.BytesIO();torch.save({'model':m.state_dict(),'optimizer':o.state_dict(),'info':info},f)
            buf=f.getvalue();self.saved['bytes']=buf
            return {'sha256':hashlib.sha256(buf).hexdigest()}
        def verify_restore(receipt):
            c=torch.load(io.BytesIO(self.saved['bytes']),map_location='cpu',weights_only=True)
            n=Toy();n.load_state_dict(c['model'])
            o=torch.optim.AdamW(n.parameters());o.load_state_dict(c['optimizer'])
            return _digest_model(n)==_digest_model(self.model)
        def rollback():
            self.model.load_state_dict(self.base)
            return _digest_model(self.model)==self.baseline
        self.host=HostPorts(
            stop_active=lambda:self.stop,authorize=lambda job:self.approved,
            inspect=lambda:{'instance_id':'UNIT_TEST_NOT_VAST'},holdout=holdout,
            checkpoint=checkpoint,verify_checkpoint=lambda r:r['sha256']==hashlib.sha256(self.saved['bytes']).hexdigest(),
            verify_restore=verify_restore,genesis_receipt=lambda r:self.records.append(r) or True,
            rollback=rollback)
    def batches(self,n=40):
        for _ in range(n):
            yield {'input_ids':torch.tensor([[1,2,1,2],[2,1,2,1]]),
                   'labels':torch.tensor([[3,4,3,4],[4,3,4,3]])}
    def test_real_cpu_tensor_update_and_restore_is_not_live(self):
        r=train_segment(model=self.model,optimizer=self.opt,batches=self.batches(),host=self.host,
            job={'request_sha256':'a'*64},max_optimizer_steps=10,gradient_accumulation=2,cpu_test_mode=True)
        self.assertEqual(r['state'],'CPU_UNIT_TEST_REAL_TENSOR_UPDATE',r)
        self.assertEqual(r['optimizer_steps'],10)
        self.assertNotEqual(r['candidate_weights_sha256'],self.baseline)
        self.assertTrue(r['holdout_loss_after']<r['holdout_loss_before'])
        self.assertFalse(r['active_model_switched'])
        self.assertEqual(len(self.records),1)
    def test_stop_does_not_train(self):
        self.stop=True
        r=train_segment(model=self.model,optimizer=self.opt,batches=self.batches(),host=self.host,
            job={'request_sha256':'a'*64},cpu_test_mode=True)
        self.assertEqual(r['state'],'HOLD_STOP_OR_OWNER')
        self.assertEqual(_digest_model(self.model),self.baseline)
    def test_no_owner_does_not_train(self):
        self.approved=False
        r=train_segment(model=self.model,optimizer=self.opt,batches=self.batches(),host=self.host,
            job={},cpu_test_mode=True)
        self.assertEqual(r['state'],'HOLD_STOP_OR_OWNER')
    def test_production_never_admits_without_telemetry(self):
        r=train_segment(model=self.model,optimizer=self.opt,batches=self.batches(),host=self.host,
            job={'request_sha256':'a'*64})
        self.assertEqual(r['state'],'HOLD_ADMISSION',r)
        self.assertEqual(r['optimizer_steps'],0)
    def test_optimizer_does_not_cover_all_parameters(self):
        self.opt=torch.optim.AdamW(self.model.head.parameters(),lr=0.03)
        r=train_segment(model=self.model,optimizer=self.opt,batches=self.batches(),host=self.host,
            job={},cpu_test_mode=True)
        self.assertEqual(r['state'],'HOLD_OPTIMIZER_NOT_ALL_PARAMETERS',r)
    def test_no_data_cannot_claim_training(self):
        r=train_segment(model=self.model,optimizer=self.opt,batches=[],host=self.host,
            job={},cpu_test_mode=True)
        self.assertEqual(r['state'],'HOLD_NO_REAL_OPTIMIZER_STEPS',r)
    def test_risk_policy_fail_closed(self):
        st={'instance_id':'60509551','gpus':[{'index':0,'name':'V100','sm':70,'protected_chat':True},
            {'index':1,'name':'V100','sm':70,'vram_free_mib':25000,'temp_c':56,'trainer_running':False}],
            'torch_cuda':'12.4','bf16_supported':False,'full_parameter_optimizer_memory_fit':True,
            'ram_free_mib':24000,'disk_free_bytes':90_000_000_000,'checkpoint_bytes_required':8_000_000_000}
        for k in ('base_weights_sha256','train_dataset_sha256','holdout_sha256','checkpoint_sha256','optimizer_state_sha256'):
            st[k]='a'*64
        for k in ('offsite_checkpoint_restored','s03_restore_verified','stop_available',
                  'owner_grant_verified','source_licenses_verified','holdout_disjoint'):
            st[k]=True
        self.assertEqual(production_admission(st,requested_job_sha='a'*64,params=100)['state'],'READY_FOR_ONEHOST')
        st['disk_free_bytes']=16_000_000_000
        self.assertEqual(production_admission(st,requested_job_sha='a'*64,params=100)['state'],'HOLD')
        self.assertIn('DISK_FOR_TWO_CHECKPOINTS_AND_RESERVE',production_admission(st,requested_job_sha='a'*64,params=100)['reasons'])

if __name__=='__main__': unittest.main()
