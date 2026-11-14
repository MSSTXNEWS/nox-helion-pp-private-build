"""T06 MB3 regression: existing NSIS 3.13 only, offline/hash-based gate, no auto-install."""
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"coordination/e06/t06_package_original_onehost.py"
spec=importlib.util.spec_from_file_location("nox_existing_t06_nsis",SOURCE)
assert spec is not None and spec.loader is not None
package=importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)

class OfflineNsisVersionGate(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.binary=Path(self.temp.name)/'makensis.exe'
        self.binary.write_bytes(b'original-offline-NSIS-compiler-test-fixture')
        self.calls=[]

    def run_version(self,args,**kwargs):
        self.calls.append((args,kwargs))
        return SimpleNamespace(returncode=0,stdout='v3.13\n',stderr='')

    def admit(self,version=None,lookup=None,candidates=None,runner=None):
        if runner is None:
            runner=(lambda args,**kwargs: SimpleNamespace(returncode=0,stdout=version,stderr='')) if version is not None else self.run_version
        return package.preflight_nsis_compiler(
            lookup=lookup or (lambda _: str(self.binary)),
            runner=runner,candidates=candidates if candidates is not None else [])

    def test_existing_313_offline_pass_records_exact_bytes(self):
        path,digest=self.admit()
        self.assertEqual(path,str(self.binary))
        self.assertEqual(digest,hashlib.sha256(self.binary.read_bytes()).hexdigest())
        self.assertEqual(self.calls[0][0],[str(self.binary),'/VERSION'])
        self.assertEqual(self.calls[0][1]['timeout'],20)

    def test_path_absent_fails_closed_no_package_manager(self):
        with self.assertRaisesRegex(RuntimeError,'PREINSTALLED_COMPILER_REQUIRED_NO_NETWORK'):
            self.admit(lookup=lambda _:None,candidates=[])
        self.assertFalse(self.calls)

    def test_rejects_older_310(self):
        with self.assertRaisesRegex(RuntimeError,'EXACT_VERSION_REQUIRED'):
            self.admit(version='v3.10\n')

    def test_rejects_newer_314_unreviewed(self):
        with self.assertRaisesRegex(RuntimeError,'EXACT_VERSION_REQUIRED'):
            self.admit(version='v3.14\n')

    def test_rejects_banner_suffix(self):
        with self.assertRaisesRegex(RuntimeError,'EXACT_VERSION_REQUIRED'):
            self.admit(version='v3.13\nUNREVIEWED COMPILER')

    def test_symlink_compiler_fails_closed(self):
        alias=Path(self.temp.name)/'alias.exe'
        try:alias.symlink_to(self.binary)
        except (OSError,NotImplementedError):self.skipTest('No symlink permission')
        with self.assertRaisesRegex(RuntimeError,'PREINSTALLED_COMPILER_REQUIRED_NO_NETWORK'):
            self.admit(lookup=lambda _:str(alias))
        self.assertFalse(self.calls)

    def test_version_process_failure(self):
        with self.assertRaisesRegex(RuntimeError,'VERSION_PROBE_FAILED'):
            self.admit(runner=lambda *a,**k:SimpleNamespace(returncode=4,stdout='',stderr=''))

    def test_version_probe_timeout(self):
        def timeout(*args,**kwargs):
            raise subprocess.TimeoutExpired(args[0],20)
        with self.assertRaisesRegex(RuntimeError,'VERSION_PROBE_FAILED'):
            self.admit(runner=timeout)

    def test_no_implicit_chocolatey_or_download_in_original_packager(self):
        content=SOURCE.read_text('utf-8')
        self.assertNotIn('chocolatey=shutil.which("choco")',content)
        self.assertNotIn('"install","nsis","--yes"',content)
        self.assertIn('nsis,nsis_compiler_sha=preflight_nsis_compiler()',content)

if __name__=='__main__':
    unittest.main()
