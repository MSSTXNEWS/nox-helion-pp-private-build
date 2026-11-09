"""R130: genuine bridge SHA identity vs optional BuildID; never a release gate."""
from pathlib import Path
import importlib.util
import unittest

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('r130', ROOT/'coordination/e06/t06_nsis_failure_diagnostics.py')
owner=importlib.util.module_from_spec(spec)
spec.loader.exec_module(owner)
SHA='a'*64

class Admission:
    ON_LOCAL_BRIDGE=True
    @staticmethod
    def require(predicate,error):
        if not predicate: raise RuntimeError(error)

class R130(unittest.TestCase):
    def test_real_bridge_exact_setup_sha_no_invented_build_id(self):
        self.assertIsNone(owner.verify_failed_setup_identity(Admission,{'setup_sha256':SHA},{'setup_sha256':SHA}))
    def test_changed_or_bad_sha_denied(self):
        for src,dst in ((SHA,'b'*64),('A'*64,'A'*64),('invalid','invalid'),('', ''),(None,None)):
            with self.subTest(src=src):
                with self.assertRaisesRegex(RuntimeError,'T06_NSIS_DIAGNOSTICS_SETUP_IDENTITY_HOLD'):
                    owner.verify_failed_setup_identity(Admission,{'setup_sha256':src},{'setup_sha256':dst})
    def test_unexpected_build_id_on_bridge_denied(self):
        for fail,proof in (({'build_id':'X'},{}),({}, {'build_id':'X'}),({'build_id':'X'},{'build_id':'X'})):
            with self.subTest(a=fail,b=proof):
                with self.assertRaisesRegex(RuntimeError,'T06_NSIS_DIAGNOSTICS_SETUP_IDENTITY_HOLD'):
                    owner.verify_failed_setup_identity(Admission,{'setup_sha256':SHA,**fail},{'setup_sha256':SHA,**proof})
    def test_nonbridge_requires_exact_real_build_id(self):
        class Native(Admission): ON_LOCAL_BRIDGE=False
        valid={'setup_sha256':SHA,'build_id':'NOX-V16-TEST'}
        owner.verify_failed_setup_identity(Native,valid,valid)
        for fail,proof in (({'setup_sha256':SHA},{'setup_sha256':SHA}),
                           (valid,{'setup_sha256':SHA,'build_id':'OTHER'}),
                           ({'setup_sha256':SHA,'build_id':''},valid)):
            with self.assertRaisesRegex(RuntimeError,'T06_NSIS_DIAGNOSTICS_SETUP_IDENTITY_HOLD'):
                owner.verify_failed_setup_identity(Native,fail,proof)

if __name__=='__main__': unittest.main()
