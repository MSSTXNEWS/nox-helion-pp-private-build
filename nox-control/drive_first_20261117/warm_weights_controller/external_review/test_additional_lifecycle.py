"""Two independent local lifecycle regressions; no native/network/model actions."""
import fcntl
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest

BASE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(BASE/'warm_weights_controller'),str(BASE/'integrations_bridge')]
from nox_warm.controller import Controller, Hold, Snapshot
from nox_integrations.memfd import MemfdHandle

class Review(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.body=b'local reviewed weights fixture';self.digest=hashlib.sha256(self.body).hexdigest()
        self.released=[];self.child_refs=[];self.handles={}
        groups=[]
        for group,mode in [('work','WORK'),('train','TRAIN')]:
            groups.append({'id':group,'role':'teacher','protected':False,'may_unload':True,'remote_path':group+'.bin','cache_path':group+'.bin','size_bytes':len(self.body),'sha256':self.digest,'ram_load_bytes':1,'gpu_load_bytes':0,'priority':1,'warm_bytes':0,'tier':'RAM','modes':[mode],'startup_preload':False})
            fd=os.memfd_create('nox-drive-review-'+group,os.MFD_ALLOW_SEALING|os.MFD_CLOEXEC)
            os.write(fd,self.body);fcntl.fcntl(fd,getattr(fcntl,'F_ADD_SEALS',1033),15)
            self.handles[group]=MemfdHandle(fd,size_bytes=len(self.body),sha256=self.digest,lease={'lease_id':'ram-'+group,'fencing_token':9},release_ram=self.release_ram)
        manifest={'schema':'NOX_WARM_MANIFEST_V1','source_policy':'DRIVE_FIRST','startup_storage':'ownedRAM','groups':groups,'mode_groups':{'WORK':['work'],'TRAIN':['train']},'budgets':{'system_reserve_bytes':0,'chat_reserve_bytes':0,'train_reserve_bytes':0}}
        self.c=Controller(manifest,self.root/'cache',self.root/'journal.json',snapshot=lambda:Snapshot(0,1024**3,1024**3,1024**3,0,0,0,0,0),hooks=self.hook,host_resource_admission=lambda req:{'granted':True,'scope':'host','lease_id':'mode-lease','fencing_token':9},host_release_resource=lambda receipt:{'released':True},owner_should_pause=lambda:False,persistent_host=True,owned_ram_registry=self.handles)
        self.c.adopt_verified_state('WORK',['work'],{'verified':True,'source':'fixture','observed_at':1})
    def release_ram(self,receipt):
        self.released.append(receipt['lease_id']);return {'released':True}
    def hook(self,name,payload):
        if name=='load':
            self.child_refs.append(os.dup(self.handles[payload['group']].fileno()))
            raise TimeoutError('simulated loader accepted memfd; ACK unknown')
        return {'ok':True,'operation_key':payload['operation_key']}
    def tearDown(self):
        for fd in self.child_refs:
            try:os.close(fd)
            except OSError:pass
        for handle in list(self.handles.values()):
            try:handle.close()
            except Exception:pass
        self.temp.cleanup()
    def test_uncertain_load_blocks_recycled_unload_receipt_and_ram_release(self):
        old_unload_receipt={'group':'train','verified':True,'loader_refs_released':True}
        with self.assertRaises(TimeoutError):self.c.transition('TRAIN','uncertain-load',apply=True)
        self.assertEqual(self.c.data['operations']['uncertain-load:load:train']['state'],'STARTED')
        self.assertNotIn('train',self.c.data['loaded'])
        # A real duplicated loader ref exists even though ACK/journal loaded is absent.
        self.assertEqual(os.pread(self.child_refs[0],len(self.body),0),self.body)
        with self.assertRaises(Hold):self.c.release_owned_ram('train',old_unload_receipt)
        self.assertEqual(self.released,[])
        self.assertIs(self.c._ram_handles['train'],self.handles['train'])
    def test_old_fence_cannot_settle_current_mode_lease(self):
        with self.assertRaises(TimeoutError):self.c.transition('TRAIN','uncertain-load',apply=True)
        delayed_receipt={'verified':True,'source':'fixture','observed_at':2,'settled_transition_id':'uncertain-load','pending_operations_settled':True,'resource_lease_settled':True,'settled_lease_id':'mode-lease','settled_fencing_token':8}
        with self.assertRaises(Hold):self.c.adopt_verified_state('WORK',['work'],delayed_receipt)
        self.assertEqual(self.c.data['transition']['status'],'HOLD')

if __name__=='__main__':unittest.main()
