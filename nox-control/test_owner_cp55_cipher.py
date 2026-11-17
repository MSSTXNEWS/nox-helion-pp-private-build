import io,json,os,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import owner_cp55_cipher as c

class BackupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name);cls.keydir=cls.root/'key'
        c.prepare(cls.keydir,'a'*64);cls.public=json.loads((cls.keydir/'public.json').read_bytes())
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=self.root);self.p=Path(self.temp.name)
        self.db=self.p/'db.sqlite'
        with sqlite3.connect(self.db) as db:db.execute('create table facts(x)');db.execute('insert into facts values (?)',('Юникод NOX private S03',))
        self.cp=self.p/'cp';self.cp.write_bytes(b'private optimizer state '+os.urandom(20000))
        self.rows=[(self.db,'s03.sqlite',None),(self.cp,'checkpoint55/optimizer.pt',c.sha(self.cp.read_bytes()))]
    def tearDown(self):self.temp.cleanup()
    def seal(self):
        parts=c.Parts(self.p/'parts');r=c.seal(self.rows,self.public,'a'*64,'b'*40,'123',parts,lambda:None);parts.finish();return r
    def test_authenticated_roundtrip_sqlite_and_cp(self):
        with patch.object(c,'PART_BYTES',4096):self.seal()
        r=c.restore(self.p/'parts',self.keydir,self.p/'restore','b'*40,'123')
        self.assertTrue(r['sqlite_quick_check']);self.assertFalse(r['cleanup_authorized'])
        self.assertEqual((self.p/'restore/checkpoint55/optimizer.pt').read_bytes(),self.cp.read_bytes())
        self.assertEqual(os.stat(self.keydir/'private.pem').st_mode&0o777,0o600)
    def test_tamper_authenticates_before_any_restore_write(self):
        self.seal();p=self.p/'parts/cp55-s03.cipher.part000';raw=bytearray(p.read_bytes());raw[-30]^=1;p.write_bytes(raw)
        with self.assertRaises(Exception):c.restore(self.p/'parts',self.keydir,self.p/'restore','b'*40,'123')
        self.assertFalse((self.p/'restore').exists())
    def test_source_mutation_no_valid_ciphertext(self):
        out=io.BytesIO();calls=[0]
        def guard():
            calls[0]+=1
            if calls[0]==5:self.cp.write_bytes(b'changed')
        with self.assertRaises(RuntimeError):c.seal(self.rows,self.public,'a'*64,'b'*40,'123',out,guard)
    def test_stop_revocation_aborts_before_auth_tag(self):
        def guard():raise RuntimeError('HOLD_STOP_CHANGED')
        with self.assertRaisesRegex(RuntimeError,'STOP_CHANGED'):c.seal(self.rows,self.public,'a'*64,'b'*40,'123',io.BytesIO(),guard)
    def test_source_or_request_replay_refused(self):
        self.seal()
        with self.assertRaisesRegex(RuntimeError,'HEADER_BINDING'):c.restore(self.p/'parts',self.keydir,self.p/'restore','c'*40,'123')
    def test_wrong_cp_pin_refused(self):
        self.rows[1]=(self.cp,'checkpoint55/optimizer.pt','0'*64)
        with self.assertRaisesRegex(RuntimeError,'PINNED_FILE_SHA'):self.seal()
    def test_no_filename_or_private_plaintext_in_wire(self):
        self.seal();raw=(self.p/'parts/cp55-s03.cipher.part000').read_bytes()
        for text in (b'optimizer.pt',b's03.sqlite',b'private optimizer state',b'PRIVATE KEY'):self.assertNotIn(text,raw)
    def test_expired_key_refused(self):
        self.public={**self.public,'created_at':0,'expires_at':1}
        with self.assertRaisesRegex(RuntimeError,'KEY_TTL'):self.seal()
    def test_paths_symlinks_and_duplicate_names_rejected(self):
        self.rows[1]=(self.cp,'../escape','0'*64)
        with self.assertRaisesRegex(RuntimeError,'FILE_NAME'):self.seal()

if __name__=='__main__':unittest.main()
