"""B03 G4 NO-LOSS: reject same-inode, same-size concurrent writes.

SOURCE_ONLY real filesystem plus controlled stat races; no NSIS execution,
no simulated release PASS. Original Windows E06/E07 are separate gates.
"""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"coordination"/"e06"))
import t06_samevm_installed_smoke as smoke

class B03OriginalNoLossReadRace(TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.file=self.root/"user.bin"
        self.payload=b"original persistent bytes"
        self.file.write_bytes(self.payload)

    def proof(self):
        return smoke.original_no_loss_file_preserved(
            self.file,self.payload,self.root)

    def test_unchanged_original_file_is_preserved(self):
        self.assertTrue(self.proof())

    def test_inplace_write_during_handle_read_is_hold(self):
        # Same inode/size/bytes at read time, but handle metadata changes.
        original=os.fstat
        count=[0]
        def witness(fd):
            value=original(fd)
            count[0]+=1
            if count[0]!=2:
                return value
            fields=("st_mode","st_dev","st_ino","st_size","st_nlink",
                    "st_mtime_ns","st_ctime_ns")
            output={name:getattr(value,name) for name in fields}
            output["st_mtime_ns"]+=1_000_000
            return SimpleNamespace(**output)
        with patch.object(smoke.os,"fstat",side_effect=witness):
            self.assertFalse(self.proof())
        self.assertEqual(count[0],2)

    def test_same_api_path_timestamp_drift_is_hold(self):
        original=Path.lstat
        count=[0]
        def witness(path,*args,**kwargs):
            value=original(path,*args,**kwargs)
            if path!=self.file:
                return value
            count[0]+=1
            if count[0]!=2:
                return value
            fields=("st_mode","st_dev","st_ino","st_size","st_nlink",
                    "st_mtime_ns","st_ctime_ns")
            output={name:getattr(value,name) for name in fields}
            output["st_mtime_ns"]+=1_000_000
            return SimpleNamespace(**output)
        with patch.object(Path,"lstat",witness):
            self.assertFalse(self.proof())
        self.assertEqual(count[0],2)

    def test_hardlink_to_foreign_user_data_is_hold(self):
        os.link(self.file,self.root/"foreign.dat")
        self.assertFalse(self.proof())

    def test_reparse_symlink_is_hold(self):
        original=self.root/"original.dat"
        self.file.rename(original)
        try:
            self.file.symlink_to(original)
        except (OSError,NotImplementedError):
            self.skipTest("symlinks unavailable")
        self.assertFalse(self.proof())

if __name__=="__main__":
    main()
