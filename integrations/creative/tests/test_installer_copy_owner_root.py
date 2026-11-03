"""Disposable installer relocation regressions; no installer or model is run."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
BUILDER = ROOT / "coordination/e06/build_onehost_installer.ps1"
VERIFIER = ROOT / "coordination/e06/verify_native_receipt_json.py"
PATCHER = ROOT / "integrations/creative/patch_installer.py"


def canonical_verifier_bytes():
    # Fixture bytes must be the committed source, not Windows CRLF checkout.
    return subprocess.check_output(["git", "-C", str(ROOT), "show",
        "HEAD:coordination/e06/verify_native_receipt_json.py"], timeout=20)


def stage_text(text, *, expected_exit=0):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        builder = root / "disposable.ps1"
        worker = root / "worker with spaces"
        worker.mkdir()
        (worker / "NOX_CreativeWorker.exe").write_bytes(b"fixture-not-executed")
        builder.write_text(text, encoding="utf-8")
        before = builder.read_bytes()
        result = subprocess.run([sys.executable, str(PATCHER), str(builder), str(worker)],
                                capture_output=True, text=True, timeout=20)
        if (result.returncode == 0) != (expected_exit == 0):
            raise AssertionError(f"patcher exit={result.returncode}: {result.stdout} {result.stderr}")
        if expected_exit and builder.read_bytes() != before:
            raise AssertionError("rejected patch changed disposable source")
        return builder.read_text(encoding="utf-8")


class RelocationContract(unittest.TestCase):
    def setUp(self):
        self.original = BUILDER.read_text(encoding="utf-8-sig")
        self.original_bytes = BUILDER.read_bytes()

    def test_copy_root_and_helpers_are_canonical_without_editing_original(self):
        text = stage_text(self.original)
        self.assertIn("git -C $PSScriptRoot rev-parse --show-toplevel", text)
        self.assertIn("E06_SOURCE_ROOT_UNAVAILABLE", text)
        self.assertNotIn("(Join-Path $PSScriptRoot '../..')", text)
        self.assertIn("$nativeVerifier=Join-Path $e06OwnerRoot 'verify_native_receipt_json.py'", text)
        self.assertIn("$bridge=Join-Path $e06OwnerRoot 'l01_manifest_bridge.py'", text)
        self.assertEqual(self.original_bytes, BUILDER.read_bytes())

    def test_pinned_strict_json_and_all_receipt_guards_remain(self):
        text = stage_text(self.original)
        for marker in ("E06_NATIVE_RECEIPT_VERIFIER_PIN_HOLD", "E06_NATIVE_RECEIPT_STRICT_JSON_HOLD",
                       "$strictEntry.Substring(65) | ConvertFrom-Json",
                       "E06_TRACKED_CHECKOUT_DIRTY_BEFORE_BUILD", "E06_SOURCE_HEAD_CHANGED_DURING_BUILD",
                       "CREATIVE_PAYLOAD_MISSING_HOLD", "CREATIVE_PAYLOAD_OVERWRITE_HOLD"):
            self.assertIn(marker, text)
        self.assertEqual(text.count("git -C $e06RepoRoot diff --quiet --exit-code HEAD --"), 2)
        self.assertLess(text.index("-Scope 'BUILDER'"), text.index("git -C $PSScriptRoot rev-parse"))
        self.assertLess(text.index("-Scope 'REPOSITORY'"), text.index("git -C $e06RepoRoot diff --quiet"))
        pin = re.search(r"expectedNativeVerifierBlob='([0-9a-f]{40})'", text).group(1)
        raw = canonical_verifier_bytes()
        self.assertEqual(pin, hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest())

    def test_missing_root_anchor_rejected_before_any_write(self):
        text = self.original.replace("$e06RepoRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path", "# root drift")
        stage_text(text, expected_exit=1)

    def test_duplicate_root_anchor_rejected_before_any_write(self):
        line = "$e06RepoRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path"
        stage_text(self.original.replace(line, line + "\n" + line), expected_exit=1)

    def test_missing_helper_anchor_rejected_before_any_write(self):
        text = self.original.replace("Join-Path $PSScriptRoot 'verify_native_receipt_json.py'", "Join-Path $other 'verify_native_receipt_json.py'")
        stage_text(text, expected_exit=1)

    def test_missing_manifest_anchor_rejected_before_any_write(self):
        stage_text(self.original.replace("# Include the existing program files in the conservative NSIS manifest.", "# drift"), expected_exit=1)

    def test_repeated_stage_rejected_without_duplicate_worker_insertion(self):
        stage_text(stage_text(self.original), expected_exit=1)

@unittest.skipUnless(shutil.which("pwsh"), "PowerShell not installed; Windows CI must execute these cases")
class ActualPowerShellPreflight(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name).resolve()
        self.repo = self.parent / "repo with spaces"
        self.owner = self.repo / "coordination/e06"
        self.copy_dir = self.repo / "work/e06/github-creative-worker"
        self.source = self.repo / "work/e06/staged/R11"
        for path in (self.owner, self.copy_dir, self.source):
            path.mkdir(parents=True, exist_ok=True)
        self.exe = self.repo / "work/candidate/original.exe"
        self.exe.parent.mkdir(parents=True)
        self.exe.write_bytes(b"fixture-not-executed")
        self.marker = self.repo / "tracked-outside-work.txt"
        self.marker.write_text("baseline", encoding="utf-8")
        (self.owner / VERIFIER.name).write_bytes(canonical_verifier_bytes())
        (self.owner / "l01_manifest_bridge.py").write_text("# fixture, not executed", encoding="utf-8")
        self.git("init", "-q")
        self.git("config", "core.autocrlf", "false")
        self.git("add", "coordination", self.marker.name)
        self.git("-c", "user.name=Source Test", "-c", "user.email=source-test@example.invalid", "commit", "-qm", "fixture")
        original = stage_text(BUILDER.read_text(encoding="utf-8-sig"))
        self.prefix = original.split("$exeDigest=", 1)[0]
        first = original.index("  $nativeVerifier=")
        last = original.index("  $nativeStrictPython=", first)
        self.admission = original[first:last]
        self.bridge_line = next(line.strip() for line in original.splitlines() if line.strip().startswith("$bridge=Join-Path"))

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              text=True, capture_output=True, timeout=20)

    def run_preflight(self, location, *, helper=True):
        location.mkdir(parents=True, exist_ok=True)
        script = location / "build_onehost_creative_disposable.ps1"
        body = self.prefix
        if helper:
            body += self.admission + "\n" + self.bridge_line + "\n"
            body += "[ordered]@{root=$e06RepoRoot;verifier=$nativeVerifier;bridge=$bridge} | ConvertTo-Json -Compress\n"
        else:
            body += "Write-Output 'PREFLIGHT_COMPLETED'\n"
        script.write_text(body, encoding="utf-8")
        return subprocess.run([shutil.which("pwsh"), "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(script),
            "-SourceRoot", str(self.source), "-PythonExe", str(self.exe),
            "-OutputRoot", str(self.repo / "work/output"), "-RunId", "NX01-PREFLIGHT"],
            cwd=self.parent, capture_output=True, text=True, timeout=30)

    def check_success(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        value = json.loads(result.stdout.strip())
        self.assertEqual(Path(value["root"]).resolve(), self.repo)
        self.assertEqual(Path(value["verifier"]).resolve(), self.owner / VERIFIER.name)
        self.assertEqual(Path(value["bridge"]).resolve(), self.owner / "l01_manifest_bridge.py")

    def test_original_location_works(self):
        self.check_success(self.run_preflight(self.owner))

    def test_relocated_builder_uses_same_pinned_owner_from_unrelated_cwd(self):
        # A decoy beside the disposable builder must never be imported.
        (self.copy_dir / VERIFIER.name).write_text("raise RuntimeError('DECOY')", encoding="utf-8")
        self.check_success(self.run_preflight(self.copy_dir))

    def test_dirty_tracked_file_outside_work_is_rejected(self):
        self.marker.write_text("unreviewed mutation", encoding="utf-8")
        result = self.run_preflight(self.copy_dir, helper=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("E06_TRACKED_CHECKOUT_DIRTY_BEFORE_BUILD", result.stderr)

    def test_missing_canonical_helper_cannot_fall_back_to_decoy(self):
        (self.owner / VERIFIER.name).unlink()
        self.git("add", "-u")
        self.git("-c", "user.name=Source Test", "-c", "user.email=source-test@example.invalid", "commit", "-qm", "missing fixture")
        (self.copy_dir / VERIFIER.name).write_bytes(canonical_verifier_bytes())
        result = self.run_preflight(self.copy_dir)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("E06_NATIVE_RECEIPT_STRICT_JSON_HOLD", result.stderr)

    def test_changed_committed_helper_still_fails_exact_pin(self):
        (self.owner / VERIFIER.name).write_text("# changed fixture", encoding="utf-8")
        self.git("add", "-u")
        self.git("-c", "user.name=Source Test", "-c", "user.email=source-test@example.invalid", "commit", "-qm", "changed fixture")
        result = self.run_preflight(self.copy_dir)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("E06_NATIVE_RECEIPT_VERIFIER_PIN_HOLD", result.stderr)

    def test_copy_outside_git_is_rejected(self):
        result = self.run_preflight(self.parent / "outside", helper=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("PREFLIGHT_COMPLETED", result.stdout)


if __name__ == "__main__":
    unittest.main()
