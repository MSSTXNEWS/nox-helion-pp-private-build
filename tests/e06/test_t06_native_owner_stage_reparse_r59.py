"""Native owner 18-file stage must reject source or destination reparse ancestry.

Runs only original T06 stage function on scoped temporary bytes; this is not
Windows runtime, completed Setup, or independent installed E07 acceptance.
"""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[2] / "coordination/e06/t06_compile_original_wpf_p02.py"
SPEC = importlib.util.spec_from_file_location("nox_t06_owner_stage_r59", SOURCE)
compiler = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compiler)
DEST = "Integration/NativePythonPipe.cs"


class NativeOwnerSourceTrust(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="nox-stage-r59-")
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.root = base / "checkout"
        self.root.mkdir()
        self.stage = base / "disposable-R11"
        self.stage.mkdir()
        folder = self.root / "Packages/P03/real"
        folder.mkdir(parents=True)
        self.raw = b"pinned-original-native-owner-source\n"
        (folder / "native.cs").write_bytes(self.raw)
        self.owner_row = "Packages/P03/real/native.cs"
        root_patch = patch.object(compiler, "ROOT", self.root)
        dest_patch = patch.object(compiler, "REQUIRED_NATIVE_DESTINATIONS", frozenset({DEST}))
        root_patch.start()
        dest_patch.start()
        self.addCleanup(root_patch.stop)
        self.addCleanup(dest_patch.stop)

    def run_owner_stage(self, relative=None):
        rows = ((relative or self.owner_row, DEST, compiler.git_blob(self.raw)),)
        with patch.object(compiler, "canonical_owner_manifest", return_value=rows):
            return compiler.stage_current_owner_components(self.stage)

    def test_original_unredirected_native_source_stages_exact_bytes(self):
        self.assertEqual(self.run_owner_stage(), 1)
        self.assertEqual((self.stage / DEST).read_bytes(), self.raw)

    def test_source_symlink_ancestor_with_same_sha_denied(self):
        alias = self.root / "Packages/P03/redirect"
        alias.symlink_to(self.root / "Packages/P03/real", target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "T06_CANONICAL_OWNER_COMPONENT_MISSING_OR_REDIRECTED"):
            self.run_owner_stage("Packages/P03/redirect/native.cs")
        self.assertFalse((self.stage / DEST).exists())

    def test_stage_destination_junction_like_parent_denied_before_write(self):
        other = self.stage.parent / "other"
        other.mkdir()
        (self.stage / "Integration").symlink_to(other, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "T06_CANONICAL_OWNER_STAGE_DESTINATION_REDIRECTED"):
            self.run_owner_stage()
        self.assertFalse((other / "NativePythonPipe.cs").exists())

    def test_dangling_stage_parent_fails_closed(self):
        (self.stage / "Integration").symlink_to(self.stage / "missing", target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "T06_CANONICAL_OWNER_STAGE_DESTINATION_REDIRECTED"):
            self.run_owner_stage()

    def test_original_leaf_symlink_rejected(self):
        leaf = self.root / "Packages/P03/real/native-link.cs"
        leaf.symlink_to(leaf.with_name("native.cs"))
        with self.assertRaisesRegex(RuntimeError, "T06_CANONICAL_OWNER_COMPONENT_MISSING_OR_REDIRECTED"):
            self.run_owner_stage("Packages/P03/real/native-link.cs")

    def test_windows_reparse_attribute_source_ancestor_denied(self):
        guarded = self.root / "Packages/P03/real"
        original = Path.lstat
        def witnessed(path):
            metadata = original(path)
            if path == guarded:
                return SimpleNamespace(st_mode=metadata.st_mode, st_file_attributes=0x400)
            return metadata
        with patch.object(Path, "lstat", witnessed):
            with self.assertRaisesRegex(RuntimeError, "T06_CANONICAL_OWNER_COMPONENT_MISSING_OR_REDIRECTED"):
                self.run_owner_stage()


if __name__ == "__main__":
    unittest.main()
