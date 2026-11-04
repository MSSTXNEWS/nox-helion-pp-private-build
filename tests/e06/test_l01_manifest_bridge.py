import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "coordination" / "e06") if "tests" in Path(__file__).parts else str(Path(__file__).resolve().parent))
from l01_manifest_bridge import emit, Hold

class OwnerManifest(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.root=Path(self.t.name);self.setup=self.root/'NOX-HELION-V16-DIAGNOSTIC-SETUP.exe'
        b=bytearray(8192);b[:2]=b'MZ';b[60:64]=(128).to_bytes(4,'little');b[128:132]=b'PE\0\0';b[132:134]=(0x8664).to_bytes(2,'little');b[152:154]=(0x20b).to_bytes(2,'little')
        self.setup.write_bytes(b)
        self.receipt=self.root/'ONEHOST_DIAGNOSTIC_RECEIPT.json'
        self.proof={'schema':'NOX-E06-ONEHOST-DIAGNOSTIC-NSIS-v1',
                    'one_visible_host':True,'release_accepted':False,
                    'status':'WINDOWS_INSTALLER_CANDIDATE_NOT_E07_ACCEPTED',
                    'installer_lifecycle_tested':False,'installer_bytes':len(b),
                    'installer_sha256':hashlib.sha256(b).hexdigest()}
        self.commit_receipt()
        self.out=self.root/'NOX-HELION-RELEASE.txt'
        self.url='https://github.com/MSSTXNEWS/nox-helion-pp-private-build/releases/download/v0.1.0/NOX-HELION-V16-DIAGNOSTIC-SETUP.exe'
    def commit_receipt(self):self.receipt.write_text(json.dumps(self.proof),encoding='utf-8')
    def run_gate(self, url=None,version=1):return emit(self.setup,self.receipt,self.url if url is None else url,version,self.out)
    def test_valid_candidate_sha_and_format(self):
        r=self.run_gate();raw=self.out.read_bytes();self.assertEqual(r['manifest_sha256_for_L01_rebuild_after_owner_review'],hashlib.sha256(raw).hexdigest());self.assertEqual(raw.splitlines()[0],b'NOX-HELION-BOOTSTRAP-V2');self.assertFalse(r['release_accepted'])
    def test_refuses_overwrite(self):
        self.run_gate();self.assertRaises(Hold,self.run_gate)
    def test_checksum_mismatch(self):
        self.setup.write_bytes(self.setup.read_bytes()+b'X');self.assertRaises(Hold,self.run_gate)
    def test_nsis_x86_stub_allowed(self):
        b=bytearray(self.setup.read_bytes()); b[132:134]=(0x14c).to_bytes(2,"little"); b[152:154]=(0x10b).to_bytes(2,"little")
        self.setup.write_bytes(b);self.proof["installer_sha256"]=hashlib.sha256(b).hexdigest();self.commit_receipt()
        self.assertEqual(self.run_gate()["status"],"MANIFEST_SOURCE_CANDIDATE_NOT_OWNER_APPROVED")
    def test_wrong_exe(self):
        self.setup.write_bytes(b'X'*8192);self.proof['installer_sha256']=hashlib.sha256(self.setup.read_bytes()).hexdigest();self.commit_receipt();self.assertRaises(Hold,self.run_gate)
    def test_foreign_origin(self):self.assertRaises(Hold,self.run_gate,self.url.replace('github.com','github.evil.com'))
    def test_wrong_repo(self):self.assertRaises(Hold,self.run_gate,self.url.replace('MSSTXNEWS','attacker'))
    def test_wrong_filename(self):self.assertRaises(Hold,self.run_gate,self.url.replace('DIAGNOSTIC-SETUP.exe','EVIL.exe'))
    def test_url_query(self):self.assertRaises(Hold,self.run_gate,self.url+'?token=x')
    def test_no_unsafe_downgrade(self):self.assertRaises(Hold,self.run_gate,version=0)
    def test_no_url_encoding_bypass(self):self.assertRaises(Hold,self.run_gate,self.url.replace('NOX-HELION','NOX%2dHELION'))
    def test_refuse_duplicate_release_acceptance_in_owner_receipt(self):
        # json.loads would otherwise trust the last conflicting occurrence.
        self.receipt.write_text('{"release_accepted":true,' + json.dumps(self.proof)[1:], encoding='utf-8')
        with self.assertRaisesRegex(Hold, "L02_RECEIPT_DUPLICATE_KEY_HOLD"):
            self.run_gate()
        self.assertFalse(self.out.exists())

    def test_refuse_duplicate_nested_receipt_key(self):
        self.receipt.write_text(json.dumps(self.proof)[:-1] + ',"ignored":{"owner":"A","owner":"B"}}', encoding='utf-8')
        with self.assertRaisesRegex(Hold, "L02_RECEIPT_DUPLICATE_KEY_HOLD"):
            self.run_gate()
        self.assertFalse(self.out.exists())

    def test_refuse_nonfinite_owner_receipt_extension(self):
        for raw in ('NaN', 'Infinity', '-Infinity'):
            with self.subTest(raw=raw):
                self.receipt.write_text(json.dumps(self.proof)[:-1] + ',"ignored":' + raw + '}', encoding='utf-8')
                with self.assertRaisesRegex(Hold, "L02_RECEIPT_NONFINITE_NUMBER_HOLD"):
                    self.run_gate()
                self.assertFalse(self.out.exists())

    def test_refuse_unauthorized_release_receipt(self):
        self.proof['release_accepted']=True;self.commit_receipt();self.assertRaises(Hold,self.run_gate)
    def test_refuse_unsafe_symlink(self):
        alias=self.root/'alias.exe';alias.symlink_to(self.setup)
        self.assertRaises(Hold,emit,alias,self.receipt,self.url,1,self.out)

if __name__=='__main__':unittest.main()