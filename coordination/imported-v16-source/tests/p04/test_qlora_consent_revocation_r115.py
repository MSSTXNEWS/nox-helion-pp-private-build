"""W01-R116: real original QLoRA restoration and local consent revalidation."""
import hashlib,pathlib,sys,tempfile,unittest,inspect
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[2]/"Packages"/"P04"))
import train_qlora as q
GOOD=b'{"schema":"nox-dataset-consent-v1","rights_status":"APPROVED","consent_status":"GRANTED"}\n'
class ConsentSnapshot(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory();self.addCleanup(self.t.cleanup)
        self.path=pathlib.Path(self.t.name)/"consent.json";self.path.write_bytes(GOOD)
        self.sha=hashlib.sha256(GOOD).hexdigest()
    def check(self):return q.require_training_consent_unchanged(self.path,self.sha)
    def blocked(self):
        with self.assertRaisesRegex(RuntimeError,"P04_TRAINING_CONSENT_CHANGED"):self.check()
    def test_unchanged(self):self.assertIsNone(self.check())
    def test_revoked(self):self.path.write_bytes(GOOD.replace(b"GRANTED",b"REVOKED"));self.blocked()
    def test_modified(self):self.path.write_bytes(GOOD+b" ");self.blocked()
    def test_deleted(self):self.path.unlink();self.blocked()
    def test_symlink(self):
        x=pathlib.Path(self.t.name)/"actual";x.write_bytes(GOOD);self.path.unlink()
        try:self.path.symlink_to(x)
        except (OSError,NotImplementedError):self.skipTest("no symlinks")
        self.blocked()
    def test_hardlink_alias_is_not_approved_consent(self):
        import os
        alias=pathlib.Path(self.t.name)/"second-consent-name.json"
        try:os.link(self.path,alias)
        except (OSError,NotImplementedError):self.skipTest("filesystem has no hardlink support")
        self.blocked()
    def test_identical_file_replaced_during_open_is_not_consent(self):
        import os
        from unittest import mock
        replacement=pathlib.Path(self.t.name)/"identical-new-file.json"
        replacement.write_bytes(GOOD)
        open_original=os.open
        def replacement_after_open(*a,**kw):
            fd=open_original(*a,**kw)
            os.replace(replacement,self.path)
            return fd
        with mock.patch.object(os,"open",side_effect=replacement_after_open):
            self.blocked()
    def test_malformed_hash(self):
        with self.assertRaisesRegex(RuntimeError,"P04_TRAINING_CONSENT_CHANGED"):
            q.require_training_consent_unchanged(self.path,"bad")
    def test_hash_mismatch(self):self.sha="0"*64;self.blocked()
    def test_invalid_grant(self):
        self.path.write_bytes(GOOD.replace(b"APPROVED",b"REJECTED"))
        self.sha=hashlib.sha256(self.path.read_bytes()).hexdigest();self.blocked()
    def test_classification(self):
        self.assertEqual(q.classify_training_failure(RuntimeError("P04_TRAINING_CONSENT_CHANGED")),"HOLD")
    def test_full_source_and_runtime_checks(self):
        s=inspect.getsource(q);self.assertGreater(len(s),60000)
        for x in ("class Callback(TrainerCallback):","trainer.train(resume_from_checkpoint=resume)","write_training_receipt(output, receipt)"):self.assertIn(x,s)
        self.assertGreaterEqual(s.count("require_training_consent_unchanged(manifest_path, approved_manifest_sha256)"),5)
if __name__=="__main__":unittest.main()
