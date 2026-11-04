"""Original Express NSIS candidate output admission; source regression, not E07."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/"coordination/e06/t06_package_original_onehost.py"
SPEC=importlib.util.spec_from_file_location("t06_nsis_candidate",SOURCE)
MODULE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

class SetupOutputTest(unittest.TestCase):
    def test_old_staged_setup_rejected_before_build(self):
        code=SOURCE.read_text("utf-8")
        self.assertIn('need(not setup.exists() and not setup.is_symlink(),',code)
        self.assertIn('"T06_NSIS_OUTPUT_COLLISION"',code)

    def test_missing_setup_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError,"T06_NSIS_SETUP_MISSING_OR_REDIRECTED"):
                MODULE.verify_nsis_setup(Path(tmp)/"missing.exe")

    def test_tiny_168_byte_copy_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"old-copy.exe";p.write_bytes(b"MZ"+b"0"*166)
            with self.assertRaisesRegex(RuntimeError,"T06_NSIS_SETUP_TOO_SMALL_OR_TRUNCATED"):
                MODULE.verify_nsis_setup(p)

    def test_large_non_pe_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"not-exe.bin";p.write_bytes(b"PK"+b"0"*1048576)
            with self.assertRaisesRegex(RuntimeError,"T06_NSIS_SETUP_NOT_WINDOWS_PE"):
                MODULE.verify_nsis_setup(p)

    def test_binary_returns_real_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            data=bytearray(b"0"*1048578)
            data[:2]=b"MZ"
            data[60:64]=(128).to_bytes(4,"little")
            data[128:132]=b"PE\x00\x00"
            data=bytes(data)
            p=Path(tmp)/"candidate.exe";p.write_bytes(data)
            self.assertEqual(MODULE.verify_nsis_setup(p),
                {"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()})

    def test_mz_only_non_pe_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"mz-only.exe";p.write_bytes(b"MZ"+b"0"*1048576)
            with self.assertRaisesRegex(RuntimeError,"T06_NSIS_SETUP_PE_OFFSET_INVALID"):
                MODULE.verify_nsis_setup(p)

    def test_symlink_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"target.exe";target.write_bytes(b"MZ"+b"0"*1048576)
            link=Path(tmp)/"link.exe"
            try:link.symlink_to(target)
            except (OSError,NotImplementedError):self.skipTest("symlink privilege unavailable")
            with self.assertRaisesRegex(RuntimeError,"T06_NSIS_SETUP_MISSING_OR_REDIRECTED"):
                MODULE.verify_nsis_setup(link)

    def test_candidate_hash_uses_one_open_not_second_path_lookup(self):
        # Old code parsed PE from one open, then SHA-hashed a second path open.
        # A replacement between them could receive an incorrect source receipt.
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"candidate.exe"
            data=bytearray(b"0"*1048578)
            data[:2]=b"MZ"
            data[60:64]=(128).to_bytes(4,"little")
            data[128:132]=b"PE\x00\x00"
            data=bytes(data)
            p.write_bytes(data)
            original=Path.open
            reads=[0]
            def detect_second_open(candidate,mode="r",*args,**kwargs):
                if candidate==p and mode=="rb":
                    reads[0]+=1
                    if reads[0]==2:
                        p.write_bytes(b"X"*len(data))
                return original(candidate,mode,*args,**kwargs)
            with mock.patch.object(Path,"open",detect_second_open):
                result=MODULE.verify_nsis_setup(p)
            self.assertEqual(reads[0],1)
            self.assertEqual(result["sha256"],hashlib.sha256(data).hexdigest())

    def test_candidate_replaced_between_stat_and_open_hold(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"candidate.exe"
            data=bytearray(b"0"*1048578)
            data[:2]=b"MZ"
            data[60:64]=(128).to_bytes(4,"little")
            data[128:132]=b"PE\x00\x00"
            p.write_bytes(data)
            other=Path(tmp)/"replacement.exe"
            data[-1]=ord("1")
            other.write_bytes(data)
            original=Path.open
            def swap_before_open(candidate,mode="r",*args,**kwargs):
                if candidate==p and mode=="rb":
                    p.unlink()
                    other.replace(p)
                return original(candidate,mode,*args,**kwargs)
            with mock.patch.object(Path,"open",swap_before_open):
                with self.assertRaisesRegex(RuntimeError,"T06_NSIS_SETUP_REPLACED_BEFORE_OPEN"):
                    MODULE.verify_nsis_setup(p)

if __name__=="__main__":
    unittest.main()
