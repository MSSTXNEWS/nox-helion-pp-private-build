"""R52: original offline NSIS 3.13 toolchain must not change across build. NOT E07."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'coordination/e06/t06_package_original_onehost.py'
spec=importlib.util.spec_from_file_location('nox_existing_nsis_r52',SOURCE)
assert spec and spec.loader
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class NsisCompilerImmutability(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'makensis.exe'
        self.path.write_bytes(b'fixture-nsis-313')
        self.runner=lambda *a,**k:SimpleNamespace(returncode=0,stdout='v3.13\n',stderr='')

    def preflight(self,path=None):
        return module.preflight_nsis_compiler(
            lookup=lambda _:str(path or self.path),runner=self.runner,candidates=[])

    def test_accept_same_bytes_twice(self):
        path,pin=self.preflight()
        self.assertEqual(pin,hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertIsNone(module.attest_nsis_compiler_unchanged(path,pin))
        self.assertIsNone(module.attest_nsis_compiler_unchanged(path,pin))

    def test_reject_modified_compiler_after_probe(self):
        path,pin=self.preflight()
        self.path.write_bytes(b'REPLACED-nsis')
        with self.assertRaisesRegex(RuntimeError,'CHANGED_SINCE_PREFLIGHT'):
            module.attest_nsis_compiler_unchanged(path,pin)

    def test_reject_removed_compiler_after_probe(self):
        path,pin=self.preflight()
        self.path.unlink()
        with self.assertRaisesRegex(RuntimeError,'COMPILER_REPARSE_HOLD'):
            module.attest_nsis_compiler_unchanged(path,pin)

    def test_reject_symlink_file_after_probe(self):
        path,pin=self.preflight()
        other=Path(self.temp.name)/'original.exe'
        self.path.rename(other)
        try:self.path.symlink_to(other)
        except (OSError,NotImplementedError):self.skipTest('symlink unavailable')
        with self.assertRaisesRegex(RuntimeError,'COMPILER_REPARSE_HOLD'):
            module.attest_nsis_compiler_unchanged(path,pin)

    def test_reject_symlink_ancestor(self):
        path,pin=self.preflight()
        alias=Path(self.temp.name)/'alias'
        try:alias.symlink_to(Path(self.temp.name),target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest('symlink unavailable')
        with self.assertRaisesRegex(RuntimeError,'COMPILER_REPARSE_HOLD'):
            module.attest_nsis_compiler_unchanged(alias/'makensis.exe',pin)

    def test_reject_missing_owner_hash(self):
        with self.assertRaisesRegex(RuntimeError,'SHA_PIN_INVALID'):
            module.attest_nsis_compiler_unchanged(self.path,'not-hashed')

    def test_reject_version_drift(self):
        self.runner=lambda *a,**k:SimpleNamespace(returncode=0,stdout='v3.14\n',stderr='')
        with self.assertRaisesRegex(RuntimeError,'EXACT_VERSION_REQUIRED'):
            self.preflight()

    def test_preflight_reparse_parent_before_running_binary(self):
        alias=Path(self.temp.name)/'alias'
        try:alias.symlink_to(Path(self.temp.name),target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest('symlink unavailable')
        executed=[]
        self.runner=lambda *a,**k:executed.append(True)
        with self.assertRaisesRegex(RuntimeError,'COMPILER_REPARSE_HOLD'):
            self.preflight(alias/'makensis.exe')
        self.assertFalse(executed)

    def test_packager_checks_compiler_around_invocation(self):
        data=SOURCE.read_text('utf-8')
        section=data.split('nsis,nsis_compiler_sha=preflight_nsis_compiler()',1)[1].split(
            'setup_proof=verify_nsis_setup(setup)',1)[0]
        self.assertEqual(section.count(
            'attest_nsis_compiler_unchanged(nsis,nsis_compiler_sha)'),2)
        before,run,after=section.split(
            'attest_nsis_compiler_unchanged(nsis,nsis_compiler_sha)')
        self.assertIn('compiled=subprocess.run(args',run)
        self.assertIn('need(compiled.returncode==0',after)

if __name__=='__main__':unittest.main()
