"""E06 EXPRESS exact source verifier regressions; no downloads, writes to owners or release claims."""
import hashlib
import importlib.util
import pathlib
import tempfile
import unittest

SRC=pathlib.Path(__file__).resolve().parents[2]/"coordination"/"express"/"verify_stage.py"
spec=importlib.util.spec_from_file_location("nox_express_verified_stage", SRC)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class SourceSealTests(unittest.TestCase):
    def test_refuse_windows_traversal_and_devices(self):
        for bad in ("../secret", "A/../../secret", "CON.txt", "name ", "NUL", r"C:\temp", "foo//bar", "a/b."):
            with self.subTest(bad=bad):
                self.assertFalse(mod.safe_relpath(bad))
        self.assertTrue(mod.safe_relpath("Packages/P04/train_qlora.py"))

    def test_exact_git_blob_and_sha256(self):
        with tempfile.TemporaryDirectory() as root:
            p=pathlib.Path(root)/"safe.txt"
            data=b"NOX-V16-original-preservation"
            p.write_bytes(data)
            blob=hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()
            self.assertEqual(mod.stream_hash(p, "sha1"), (blob,len(data)))
            self.assertEqual(mod.stream_hash(p, "sha256"), (hashlib.sha256(data).hexdigest(),len(data)))

    def test_symlink_path_hard_hold(self):
        with tempfile.TemporaryDirectory() as root:
            p=pathlib.Path(root)/"source.txt"
            p.write_text("valuable")
            target=pathlib.Path(root)/"link"
            try: target.symlink_to(p)
            except (OSError,NotImplementedError): self.skipTest("symlink unsupported")
            with self.assertRaises(mod.Hold):
                mod.stream_hash(target, "sha256")
            self.assertEqual(p.read_text(),"valuable")

    def test_original_file_absence_refuses_source_acceptance(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(mod.Hold):
                mod.verify_tracked(pathlib.Path(root), {"files":[{"path":"source_00.part","git_blob_sha1":"0"*40}]})

    def test_duplicate_original_paths_hard_hold(self):
        with tempfile.TemporaryDirectory() as root:
            p=pathlib.Path(root)/"source_00.part"
            p.write_bytes(b"1")
            h=hashlib.sha1(b"blob 1\0"+b"1").hexdigest()
            with self.assertRaises(mod.Hold):
                mod.verify_tracked(pathlib.Path(root),{"files":[{"path":"source_00.part","git_blob_sha1":h},{"path":"source_00.part","git_blob_sha1":h}]})

if __name__=="__main__":
    unittest.main()
