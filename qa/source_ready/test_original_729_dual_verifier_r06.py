"""NOX V16 independent QA R06: REAL dual-verifier SourceLock 729.

Requires the physical original source_00/01/02.part bytes in a private checkout.
Never extracts ZIP into the original tree; no product writes or E07 claims.

Run from an exact pinned checkout:
  NOX_QA_PINNED_SOURCE_SHA=<git-rev-parse-HEAD> \
  python -m unittest discover -s qa/source_ready \
      -p 'test_original_729_dual_verifier_r06.py' -v

On Windows PowerShell, set $env:NOX_QA_PINNED_SOURCE_SHA first.
The outputs of the two *existing owner validators* must agree on all
729 member paths, lengths and raw SHA-256s, plus full ZIP SHA-256.
"""
from __future__ import annotations
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_ZIP = "ff8e2848c7c7ab776b90cbd8ac28e41e3815e96373c3c5f635d7587284629e9a"
PARTS = (
    ("source_00.part", 20971520, "e484e10d7b4ec9badeaae4c9d3a7e3aee5faa16b"),
    ("source_01.part", 20971520, "7853cb43ff4ba0ed3023e8d794d8222eedea56a6"),
    ("source_02.part", 18421306, "cbd9deb30860737f15e2adbaef2eaaf5d607a0de"),
)

def _load(path: Path, name: str):
    if not path.is_file() or path.is_symlink():
        raise AssertionError("ORIGINAL_VALIDATOR_NOT_REGULAR")
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise AssertionError("SOURCE_VALIDATOR_IMPORT_FAILED")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

class OriginalArchiveDualSourceLock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected_head = os.environ.get("NOX_QA_PINNED_SOURCE_SHA", "").lower()
        if not re.fullmatch("[0-9a-f]{40}", cls.expected_head):
            raise AssertionError("PINNED_SOURCE_HEAD_REQUIRED")
        cls.head = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True
        ).stdout.strip().lower()
        if cls.head != cls.expected_head:
            raise AssertionError("SOURCE_HEAD_DRIFT")
        if subprocess.run(
            ["git", "-C", str(ROOT), "diff", "--quiet", "HEAD", "--"],
            check=False,
        ).returncode != 0:
            raise AssertionError("SOURCE_WORKTREE_TRACKED_BYTES_CHANGED")

    def test_original_git_blob_identity_and_part_sizes(self):
        for name, expected_size, expected_blob in PARTS:
            with self.subTest(name=name):
                path = ROOT / name
                self.assertTrue(path.is_file() and not path.is_symlink())
                self.assertEqual(path.stat().st_size, expected_size)
                digest = hashlib.sha1(f"blob {expected_size}\0".encode("ascii"))
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024*1024), b""):
                        digest.update(chunk)
                self.assertEqual(digest.hexdigest(), expected_blob)

    def test_two_existing_validators_agree_on_all_729_raw_members(self):
        first = _load(ROOT / "coordination/e06/verify_original_729_source.py", "qa_r06_e06")
        second = _load(ROOT / "coordination/source-lock/verify_original_archive.py", "qa_r06_source_lock")
        a = first.verify_original(ROOT, run_id="QA-SOURCE-R06-ORIGINAL")
        b = second.audit(ROOT, 729)
        self.assertEqual(a["fileCount"], 729)
        self.assertEqual(b["file_count"], 729)
        self.assertEqual(a["combinedZip"]["bytes"], 60364346)
        self.assertEqual(b["zip_bytes"], 60364346)
        self.assertEqual(a["combinedZip"]["sha256"], EXPECTED_ZIP)
        self.assertEqual(b["zip_sha256"], EXPECTED_ZIP)
        am = {x["path"]: (x["bytes"], x["sha256"]) for x in a["files"]}
        bm = {x["path"]: (x["bytes"], x["sha256"]) for x in b["files"]}
        self.assertEqual(len(am), 729)
        self.assertEqual(am, bm)
        self.assertFalse(a["releaseAccepted"])
        self.assertFalse(a["nativeWindowsAccepted"])
        self.assertNotEqual(a["status"], "RELEASE_ACCEPTED")

if __name__ == "__main__":
    unittest.main()
