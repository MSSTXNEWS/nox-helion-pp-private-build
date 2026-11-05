"""T06 source receipt must identify the *checked out* Git commit, never a historic SHA."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[2] / "coordination/e06/t06_compile_original_wpf_p02.py"
SPEC = importlib.util.spec_from_file_location("nox_t06_compile_source_identity", MODULE)
compile_owner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(compile_owner)

class PayloadVerifierImport(unittest.TestCase):
    def test_file_import_from_arbitrary_cwd_uses_existing_sibling_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            # A same-named module on the search path must never replace the owner.
            trap = Path(directory) / "t06_package_original_onehost.py"
            trap.write_text("raise AssertionError('SEARCH_PATH_OWNER_EXECUTED')\n", encoding="utf-8")
            script = """
import importlib.util
from pathlib import Path
import sys
before = tuple(sys.path)
source = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("arbitrary_compiler_alias", source)
compiler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compiler)
verifier = compiler.stage_reviewed_installed_payload_verifier
expected = source.resolve().with_name("t06_package_original_onehost.py")
assert Path(verifier.__code__.co_filename).resolve() == expected
assert verifier.__name__ == "stage_reviewed_installed_payload_verifier"
assert tuple(sys.path) == before
"""
            result = subprocess.run([sys.executable, "-c", script, str(MODULE)],
                                    cwd=directory, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_sibling_owner_cannot_fall_back_to_search_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            isolated = root / "isolated"
            isolated.mkdir()
            source = isolated / MODULE.name
            source.write_bytes(MODULE.read_bytes())
            (root / "t06_package_original_onehost.py").write_text(
                "def stage_reviewed_installed_payload_verifier(*args): return 'FAKE_PASS'\n",
                encoding="utf-8")
            script = """
import importlib.util
from pathlib import Path
import sys
source = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("missing_owner_compiler", source)
compiler = importlib.util.module_from_spec(spec)
try:
    spec.loader.exec_module(compiler)
except FileNotFoundError as error:
    # Windows TEMP may use its 8.3 alias; compare canonical paths, not spelling.
    assert Path(error.filename).resolve() == source.resolve().with_name("t06_package_original_onehost.py")
else:
    raise AssertionError("MISSING_SIBLING_OWNER_WAS_ACCEPTED")
"""
            result = subprocess.run([sys.executable, "-c", script, str(source)],
                                    cwd=directory, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

class SourceHeadIdentity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        (self.root / "tracked.txt").write_text("original\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        self.git("-c", "user.name=NOX Test", "-c", "user.email=nox-test@example.invalid", "commit", "-qm", "first")
        root_patch = patch.object(compile_owner, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        env_patch = patch.dict(os.environ, {key: "" for key in (
            "CI_COMMIT_SHA", "CI_SERVER_HOST", "CI_PROJECT_PATH",
            "NOX_T06_AUTHENTICATED_GITHUB_FETCH", "NOX_T06_GITHUB_FROZEN_SHA",
            "NOX_T06_GITLAB_ORIGIN_SHA", "NOX_T06_GITHUB_FROZEN_REF")})
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], text=True).strip()

    def test_returns_real_checkout_head_not_stale_constant(self):
        self.assertEqual(compile_owner.verified_source_head(), self.git("rev-parse", "HEAD"))
        self.assertNotEqual(compile_owner.verified_source_head(), "74e03bc99d82467e8b9f48f367b8815fb13a0798")

    def gitlab_witnesses(self):
        head = self.git("rev-parse", "HEAD")
        return {
            "CI_COMMIT_SHA": "b" * 40,
            "CI_SERVER_HOST": "gitlab.com",
            "CI_PROJECT_PATH": "s-grouptwet/nox-helion-pp-private-build",
            "NOX_T06_AUTHENTICATED_GITHUB_FETCH": "PASS",
            "NOX_T06_GITHUB_FROZEN_SHA": head,
            "NOX_T06_GITLAB_ORIGIN_SHA": "b" * 40,
            "NOX_T06_GITHUB_FROZEN_REF": "buildpin/nox-express-20261102-" + head[:12],
        }

    def test_unverified_ci_head_fails_closed(self):
        with patch.dict(os.environ, {"CI_COMMIT_SHA": "f" * 40}):
            with self.assertRaisesRegex(RuntimeError, "T06_GITLAB_AUTHENTICATED_FROZEN_SOURCE_REQUIRED"):
                compile_owner.verified_source_head()

    def test_authenticated_frozen_ci_head_accepted(self):
        with patch.dict(os.environ, self.gitlab_witnesses()):
            self.assertEqual(compile_owner.verified_source_head(), self.git("rev-parse", "HEAD"))

    def test_mismatched_frozen_ci_head_fails_closed(self):
        witnesses = self.gitlab_witnesses()
        witnesses["NOX_T06_GITHUB_FROZEN_SHA"] = "f" * 40
        with patch.dict(os.environ, witnesses):
            with self.assertRaisesRegex(RuntimeError, "T06_GITLAB_AUTHENTICATED_FROZEN_SOURCE_REQUIRED"):
                compile_owner.verified_source_head()

    def test_missing_git_checkout_fails_closed(self):
        with patch.object(compile_owner, "ROOT", self.root / "missing_checkout"):
            with self.assertRaisesRegex(RuntimeError, "T06_SOURCE_COMMIT_UNVERIFIED"):
                compile_owner.verified_source_head()

    def test_receipt_is_measured_at_start_and_before_persist(self):
        source = MODULE.read_text(encoding="utf-8")
        self.assertIn("source_git_sha=verified_source_head()", source)
        self.assertIn("require(verified_source_head()==source_git_sha", source)
        self.assertIn('"source_git_sha":source_git_sha', source)
        self.assertNotIn('"source_git_sha":"74e03bc99d82467e8b9f48f367b8815fb13a0798"', source)

    def test_later_commit_is_detectably_different(self):
        first = compile_owner.verified_source_head()
        (self.root / "tracked.txt").write_text("changed\n", encoding="utf-8")
        self.git("add", "tracked.txt")
        self.git("-c", "user.name=NOX Test", "-c", "user.email=nox-test@example.invalid", "commit", "-qm", "second")
        self.assertNotEqual(first, compile_owner.verified_source_head())

class ApprovedRegistryBuildPin(unittest.TestCase):
    """The shipped original NSIS builder must pin the current reviewed P03 code."""
    def test_original_installer_registry_pin_matches_approved_git_blob(self):
        import json
        import re
        root = MODULE.parents[2]
        relative = "Packages/P03/Source/P03.ModelCenter/ModelArtifactReviewRegistry.cs"
        builder = (root / "coordination/e06/build_onehost_installer.ps1").read_text(encoding="utf-8-sig")
        expression = (r"@\{relative='" + re.escape(relative) +
                      r"';dest='Integration/P03/ModelArtifactReviewRegistry.cs';blob='([a-f0-9]{40})'\}")
        pins = re.findall(expression, builder)
        self.assertEqual(len(pins), 1, "Original NSIS source stage has no unique P03 registry pin")
        result = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD:" + relative],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        actual = result.stdout.strip()
        self.assertRegex(actual, r"^[a-f0-9]{40}$")
        manifest = json.loads((root / "coordination/express/P03_PINNED_GIT_BLOBS.json").read_text(encoding="utf-8"))
        reviewed = [entry for entry in manifest["approved_overrides"] if entry.get("path") == relative]
        self.assertEqual(len(reviewed), 1, "P03 current reviewed source needs one approved override")
        self.assertEqual(reviewed[0]["post_git_blob_sha1"], actual, "P03 reviewed override is stale")
        self.assertEqual(pins[0], actual, "Active NSIS OneHost builder would reject reviewed P03 source")


    def test_approved_p03_hardening_smoke_source_and_size(self):
        """Original P03 smoke source must not silently drift from reviewed Git bytes."""
        import json
        root = MODULE.parents[2]
        relative = "Packages/P03/Source/P03.ModelCenter.HardeningSmoke/Program.cs"
        registry = json.loads((root / "coordination/express/P03_PINNED_GIT_BLOBS.json").read_text(encoding="utf-8"))
        approved = [x for x in registry["approved_overrides"] if x.get("path") == relative]
        self.assertEqual(len(approved), 1, "P03 hardening source needs one reviewed override")
        proc = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD:" + relative],
                              capture_output=True, text=True, timeout=15)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertRegex(proc.stdout.strip(), r"^[a-f0-9]{40}$")
        self.assertEqual(approved[0]["post_git_blob_sha1"], proc.stdout.strip(),
                         "Approved hardening smoke source Git blob has drifted")
        self.assertEqual(approved[0]["post_bytes"], (root / relative).stat().st_size,
                         "Approved hardening smoke source length has drifted")



class OriginalNativeAddonStagePin(unittest.TestCase):
    """G2 INSTALL cannot enter real WPF owner with a stale nested stage blob."""
    def test_original_wpf_stage_pins_active_addon_and_stager(self):
        import re
        root = MODULE.parents[2]
        stage_relative = "coordination/e06/stage_native_p02.py"
        addon_relative = "coordination/e06/MainWindow.NativeP02.cs"
        def git_blob(relative):
            cmd = subprocess.run(["git", "-C", str(root), "rev-parse",
                                  "HEAD:" + relative],
                                 capture_output=True, text=True, timeout=20)
            self.assertEqual(cmd.returncode, 0, cmd.stderr)
            self.assertRegex(cmd.stdout.strip(), r"\A[0-9a-f]{40}\Z")
            return cmd.stdout.strip()
        stage_blob = git_blob(stage_relative)
        addon_blob = git_blob(addon_relative)
        stage = (root / stage_relative).read_text(encoding="utf-8")
        builder = (root / "coordination/e06/build_onehost_installer.ps1").read_text(encoding="utf-8")
        compiler = (root / "coordination/e06/t06_compile_original_wpf_p02.py").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r'(?m)^ADDON_SHA="([0-9a-f]{40})"$', stage),
                         [addon_blob], "Original R11 staging rejects the actual WPF owner")
        self.assertIn("T06_NATIVE_ADDON_GIT_BLOB_HOLD", stage)
        self.assertIn("sha='" + stage_blob + "'", builder)
        self.assertIn("sha='" + addon_blob + "'", builder)
        self.assertIn('"' + stage_relative + '":"' + stage_blob + '"', compiler)
        self.assertIn('"' + addon_relative + '":"' + addon_blob + '"', compiler)


if __name__ == "__main__":
    unittest.main()
