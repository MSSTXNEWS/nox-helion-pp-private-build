import hashlib, hmac, os, sys, tempfile, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'src'))
from nox_selfbuilder.a1_wpf_owner_proof import (
    A1WpfOwnerProof, A1OwnerProofHold, transcript)

SID='S-1-5-21-11111-22222-33333-44444'
RUN='NOX-P02-0123456789abcdef0123456789abcdef'
KEY='b4'*32
class ReceiptTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'binary.exe'
        self.path.write_bytes(b'real binary bytes test fixture')
        self.t=1700000000
        self.v=A1WpfOwnerProof(KEY,RUN,self.path,sid_provider=lambda:SID,clock=lambda:self.t)
    def ticket(self,**updates):
        x=dict(schema='NOX-A1-WPF-OWNER-CONSENT-v1',run_id=RUN,
           action='selfbuilder.a1.boot',backend_sha256=hashlib.sha256(self.path.read_bytes()).hexdigest(),
           sid_sha256=hashlib.sha256(SID.encode()).hexdigest(),nonce='c3'*16,
           issued_unix=self.t,expires_unix=self.t+20,mac='')
        x.update(updates)
        x['mac']=hmac.new(bytes.fromhex(KEY),transcript(x),hashlib.sha256).hexdigest()
        return x
    def denies(self, ticket, action='selfbuilder.a1.boot'):
        with self.assertRaises(A1OwnerProofHold):self.v.verify(ticket,action)
    def test_correct_one_time(self):
        v=self.ticket();self.assertTrue(self.v.verify(v,v['action']));self.denies(v)
    def test_wrong_action(self):self.denies(self.ticket(action='selfbuilder.a1.tick'))
    def test_tamper_mac(self):self.denies({**self.ticket(),'mac':'0'*64})
    def test_other_run(self):self.denies(self.ticket(run_id='OTHER'))
    def test_other_binary(self):self.denies(self.ticket(backend_sha256='1'*64))
    def test_other_sid(self):self.denies(self.ticket(sid_sha256='1'*64))
    def test_future(self):self.denies(self.ticket(issued_unix=self.t+20,expires_unix=self.t+40))
    def test_expired(self):self.denies(self.ticket(issued_unix=self.t-40,expires_unix=self.t-20))
    def test_extra_field(self):self.denies({**self.ticket(),'admin':True})
    def test_missing_field(self):
        x=self.ticket();del x['mac'];self.denies(x)
    def test_bool_date(self):self.denies(self.ticket(issued_unix=True,expires_unix=21))
    def test_zero_secret(self):
        with self.assertRaises(A1OwnerProofHold):A1WpfOwnerProof(None,RUN,self.path,sid_provider=lambda:SID)
    def test_different_sid_from_os(self):
        self.v=A1WpfOwnerProof(KEY,RUN,self.path,sid_provider=lambda:'S-1-2-3',clock=lambda:self.t)
        self.denies(self.ticket())
    def test_no_page_authority(self):self.denies({**self.ticket(),'nativeConsent':True})
    def test_nongenuine_receipt_action(self):self.denies(self.ticket(action='system.pc_control'),'system.pc_control')
    def test_key_popped_from_child_env(self):
        self.t = int(time.time())
        os.environ['NOX_A1_WPF_OWNER_KEY']=KEY
        try:
            x=A1WpfOwnerProof.from_native_child(RUN,self.path)
            self.assertNotIn('NOX_A1_WPF_OWNER_KEY',os.environ)
            self.assertEqual(x._run_id, RUN)  # SID requires a real Windows token
        finally:os.environ.pop('NOX_A1_WPF_OWNER_KEY',None)
if __name__=='__main__':unittest.main()
