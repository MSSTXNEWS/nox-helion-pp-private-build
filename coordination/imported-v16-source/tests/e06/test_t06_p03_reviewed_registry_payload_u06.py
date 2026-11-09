"""Original E06 P03 registry in the real NSIS owner payload, not model PASS."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
SPEC=importlib.util.spec_from_file_location("u06_registry",
        ROOT/"coordination/e06/t06_package_original_onehost.py")
MOD=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)

class ReviewedRegistryPayload(unittest.TestCase):
    def setUp(self):
        self.workspace=tempfile.TemporaryDirectory()
        self.addCleanup(self.workspace.cleanup)
        self.root=Path(self.workspace.name)
        (self.root/"contracts").mkdir()
        self.registry=self.root/"contracts/p03_reviewed_artifacts.json"
        shutil.copy2(ROOT/"contracts/p03_reviewed_artifacts.json",self.registry)
        self.payload=self.root/"payload"
        self.payload.mkdir()

    def test_pinned_registry_is_manifest_ready(self):
        got=MOD.stage_reviewed_registry(self.registry,self.payload)
        self.assertEqual(got["sha256"],MOD.P03_REVIEWED_REGISTRY_SHA256)
        self.assertEqual(got["reviewed_count"],0)
        self.assertFalse(got["release_accepted"])
        self.assertEqual((self.payload/got["path"]).read_bytes(),self.registry.read_bytes())

    def test_registry_mutation_denied(self):
        self.registry.write_bytes(b'{"schema":"NOX-P03-REVIEWED-ARTIFACTS-V1","items":[{}]}')
        with self.assertRaisesRegex(RuntimeError,"T06_P03_REGISTRY_SOURCELOCK_SHA_HOLD"):
            MOD.stage_reviewed_registry(self.registry,self.payload)

    def test_owned_payload_collision_denied(self):
        MOD.stage_reviewed_registry(self.registry,self.payload)
        with self.assertRaisesRegex(RuntimeError,"T06_P03_REGISTRY_DESTINATION_COLLISION"):
            MOD.stage_reviewed_registry(self.registry,self.payload)

    def test_wrong_filename_denied(self):
        rename=self.registry.with_name("unreviewed.json")
        self.registry.rename(rename)
        with self.assertRaisesRegex(RuntimeError,"T06_P03_REGISTRY_PATH_HOLD"):
            MOD.stage_reviewed_registry(rename,self.payload)

    def test_reparse_source_denied(self):
        original=self.root/"original.json"
        self.registry.rename(original)
        try:self.registry.symlink_to(original)
        except (OSError,NotImplementedError):self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(RuntimeError,"T06_PAYLOAD_PATH_REPARSE_HOLD"):
            MOD.stage_reviewed_registry(self.registry,self.payload)

    def test_reparse_payload_parent_denied(self):
        redir=self.root/"redir"
        redir.mkdir()
        try:(self.payload/"contracts").symlink_to(redir,target_is_directory=True)
        except (OSError,NotImplementedError):self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(RuntimeError,"T06_PAYLOAD_PATH_REPARSE_HOLD"):
            MOD.stage_reviewed_registry(self.registry,self.payload)

    def test_original_native_owner_sha_matches(self):
        owner=(ROOT/"coordination/e06/MainWindow.NativeP02.cs").read_text("utf-8")
        self.assertIn(MOD.P03_REVIEWED_REGISTRY_SHA256,owner)
        self.assertIn('Path.Combine(AppContext.BaseDirectory,"contracts","p03_reviewed_artifacts.json")',owner)

if __name__=="__main__":unittest.main()
