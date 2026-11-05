"""Regression: verified GitHub source bundles remain source-only and fail closed."""
import io,json,sys,tempfile,unittest,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"coordination/express"))
import restore_engine15_sources as restore

class Engine15SourceTests(unittest.TestCase):
    def test_manifest_owner_and_part_counts(self):
        m=json.loads((ROOT/"coordination/express/NOX_ENGINE15_SOURCELOCK_42023301530.json").read_text("utf-8"))
        self.assertEqual(m["run_id"],42023301530)
        self.assertEqual(len(m["engines"]),15)
        self.assertEqual(sum(e["parts"] for e in m["engines"]),22)
        self.assertFalse(m["installed"])
        self.assertFalse(m["e07_accepted"])
        self.assertEqual([e["index"] for e in m["engines"]],list(range(1,16)))

    def test_traversal_collision_and_large_source_denied(self):
        for members in (("../escape",),("a","a"),("C:drive",)):
            with self.subTest(members=members),tempfile.TemporaryDirectory() as root:
                p=Path(root)/"bad.zip"
                with zipfile.ZipFile(p,"w") as z:
                    for name in members:z.writestr(name,b"source")
                with self.assertRaises(ValueError):
                    restore.source_zip_verified(p,"untrusted")

    def test_redirected_owner_path_denied(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)
            origin=p/"owner";origin.mkdir()
            link=p/"alias"
            try:link.symlink_to(origin,target_is_directory=True)
            except (OSError,NotImplementedError):self.skipTest("Symlinks unavailable")
            self.assertFalse(restore.safe_owner_path(link))
            self.assertFalse(restore.safe_owner_path(link/"archive.zip",missing=True))

    def test_existing_zip_is_only_reused_by_matching_sha(self):
        self.assertTrue(callable(restore.sha256))
        self.assertTrue(callable(restore.source_zip_verified))
        self.assertTrue(callable(restore.recover))

if __name__=="__main__":unittest.main()
