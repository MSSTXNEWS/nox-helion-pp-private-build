"""Regression for first real Windows E06 uninstall quiescence race, source only."""
from pathlib import Path
import importlib.util
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
PATH=ROOT/"coordination/e06/t06_samevm_installed_smoke.py"
def load_smoke():
    spec=importlib.util.spec_from_file_location("nox_t06_quiescence_r114", PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("T06_TEST_SOURCE_MISSING")
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

class UninstallQuiescenceR114(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/"NOX HELION"
        self.root.mkdir()
        self.payload=self.root/"Accessibility.dll"
        self.payload.write_bytes(b"original")
        self.module=load_smoke()
        self.metadata=tuple(self.root/n for n in ("payload.sha256.json","nox-p01-owned.txt","Uninstall.exe"))

    def verifier(self,root,files):
        if any(p.exists() or p.is_symlink() for p in tuple(files)+self.metadata):
            raise RuntimeError("T06_CONSERVATIVE_UNINSTALL_MANIFEST_FILE_REMAINS")

    def asynchronously_remove(self,paths,delay=.08):
        def delete():
            time.sleep(delay)
            for p in paths:
                p.unlink()
        thread=threading.Thread(target=delete)
        thread.start()
        self.addCleanup(thread.join)
        return thread

    def test_metadata_gone_before_late_owned_dll_must_wait(self):
        # Exact first-failure race: NSIS metadata cleanup is NOT evidence
        # its delayed child has removed the last manifest-owned DLL.
        thread=self.asynchronously_remove((self.payload,))
        with patch.object(self.module,"verify_original_uninstall",self.verifier):
            self.module.await_original_uninstall(self.root,(self.payload,),
                                                 timeout_seconds=.5,poll_seconds=.01)
        thread.join()
        self.assertFalse(self.payload.exists())

    def test_metadata_and_owned_file_both_late_must_wait(self):
        self.metadata[0].write_bytes(b"meta")
        thread=self.asynchronously_remove((self.metadata[0],self.payload))
        with patch.object(self.module,"verify_original_uninstall",self.verifier):
            self.module.await_original_uninstall(self.root,(self.payload,),
                                                 timeout_seconds=.5,poll_seconds=.01)
        thread.join()
        self.assertFalse(self.payload.exists())

    def test_persistent_owned_residue_still_holds(self):
        with patch.object(self.module,"verify_original_uninstall",self.verifier):
            with self.assertRaisesRegex(RuntimeError,
                                        "T06_CONSERVATIVE_UNINSTALL_MANIFEST_FILE_REMAINS"):
                self.module.await_original_uninstall(self.root,(self.payload,),
                                                     timeout_seconds=.06,poll_seconds=.01)
        self.assertTrue(self.payload.exists())

    def test_unknown_private_file_is_not_removed_or_waited_for(self):
        self.payload.unlink()
        private=self.root/"private-user-file.txt"
        private.write_bytes(b"preserve")
        with patch.object(self.module,"verify_original_uninstall",self.verifier):
            self.module.await_original_uninstall(self.root,(self.payload,),
                                                 timeout_seconds=.06,poll_seconds=.01)
        self.assertEqual(private.read_bytes(),b"preserve")

if __name__=="__main__":
    unittest.main(verbosity=2)
