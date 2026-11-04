"""B05: prevent stale native R11 stage pins from blocking real Windows Setup.

SOURCE_ONLY contract; an installed x64 Setup and independent E07 still require Windows.
"""
import hashlib
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
E06 = ROOT / "coordination" / "e06"
STAGE = E06 / "stage_native_p02.py"
ADDON = E06 / "MainWindow.NativeP02.cs"
BUILDER = E06 / "build_onehost_installer.ps1"
COMPILER = E06 / "t06_compile_original_wpf_p02.py"


def canonical_git_blob(path: Path) -> str:
    raw = path.read_bytes()
    # Only allow the canonical LF form of a pure Windows CRLF checkout.
    if b"\r\n" in raw and b"\r" not in raw.replace(b"\r\n", b""):
        raw = raw.replace(b"\r\n", b"\n")
    return hashlib.sha1(
        b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw
    ).hexdigest()


class NativeP02StagePinB05(unittest.TestCase):
    def test_exact_checked_in_stage_blob_is_pinned_in_both_build_paths(self):
        sha = canonical_git_blob(STAGE)
        builder = BUILDER.read_text(encoding="utf-8")
        compiler = COMPILER.read_text(encoding="utf-8")
        self.assertIn("foreach ($part in @(", builder)
        self.assertEqual(builder.count("sha='" + sha + "'"), 1)
        self.assertIn(
            '"coordination/e06/stage_native_p02.py":"' + sha + '"',
            compiler,
        )
        # Both stages remain fail-closed and the previous stale hash cannot pass.
        self.assertIn("T06_ORIGINAL_MAINWINDOW_ADDON_SHA_HOLD", builder)
        self.assertIn("GITHUB_OWNER_OVERLAY_SHA_HOLD:", compiler)

    def test_real_addon_identity_and_original_mainwindow_guards_survive(self):
        addon_sha = canonical_git_blob(ADDON)
        stage = STAGE.read_text(encoding="utf-8")
        builder = BUILDER.read_text(encoding="utf-8")
        compiler = COMPILER.read_text(encoding="utf-8")
        self.assertIn('ADDON_SHA="' + addon_sha + '"', stage)
        self.assertIn("sha='" + addon_sha + "'", builder)
        self.assertIn(
            '"coordination/e06/MainWindow.NativeP02.cs":"' + addon_sha + '"',
            compiler,
        )
        self.assertIn("MAIN_SHA=", stage)
        self.assertIn("T06_NATIVE_ADDON_GIT_BLOB_HOLD", stage)
        self.assertIn("T06_ORIGINAL_MAINWINDOW_SHA_HOLD", stage)


if __name__ == "__main__":
    unittest.main()
