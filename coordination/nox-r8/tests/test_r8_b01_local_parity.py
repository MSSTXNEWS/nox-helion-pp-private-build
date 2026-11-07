"""Offline disposable fixtures. Does not touch the owner's C:\\NOX_HELION."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "attest_local_parity.py"
SHA40 = "a" * 40
SHA64 = "b" * 64


class Parity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.src = self.base / "src"
        self.src.mkdir()
        self.exe = self.base / "NOX.HELION.exe"
        self.exe.write_bytes(b"demo exe bytes")
        self.man = self.base / "SOURCE_PROVENANCE.json"
        self.receipt = self.base / "BUILD_RECEIPT.json"
        rows = []
        for name in ("MainWindow.xaml.cs", "index.html", "NOX.HELION.csproj"):
            path = self.src / name
            path.write_bytes(name.encode())
            rows.append({"path": name, "bytes": path.stat().st_size,
                         "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        m = {"schema": "NOX_R8_BUILD_SRC_PROVENANCE_V1", "source_git_sha": SHA40,
             "source_zip_sha256": SHA64, "files": rows}
        self.man.write_text(json.dumps(m), encoding="utf-8")
        r = {"schema": "NOX_R8_NATIVE_SINGLE_EXE_V1", "source_git_sha": SHA40,
             "source_sha256": SHA64,
             "staged_source_manifest_sha256": hashlib.sha256(self.man.read_bytes()).hexdigest(),
             "staged_source_file_count": 3, "exe_sha256": hashlib.sha256(self.exe.read_bytes()).hexdigest(),
             "owner_source_parity": "NOT_VERIFIED", "accepted_full_release": False}
        self.receipt.write_text(json.dumps(r), encoding="utf-8")
        self.trusted_manifest_sha = hashlib.sha256(self.man.read_bytes()).hexdigest()
        self.trusted_receipt_sha = hashlib.sha256(self.receipt.read_bytes()).hexdigest()
        self.trusted_git_sha = SHA40

    def call(self):
        p = subprocess.run([sys.executable, "-B", str(SCRIPT), "--manifest", str(self.man),
                            "--receipt", str(self.receipt), "--local-src", str(self.src),
                            "--local-exe", str(self.exe),
                            "--trusted-manifest-sha256", self.trusted_manifest_sha,
                            "--trusted-receipt-sha256", self.trusted_receipt_sha,
                            "--trusted-git-sha", self.trusted_git_sha],
                           text=True, capture_output=True)
        return p.returncode, json.loads(p.stdout)

    def test_identical_bytes_not_release(self):
        code, r = self.call()
        self.assertEqual((code, r["result"], r["release"]), (0, "BYTE_PARITY_ONLY_NOT_E2E", "HOLD"))

    def test_modified_source_fails_closed(self):
        (self.src / "index.html").write_bytes(b"changed")
        code, r = self.call()
        self.assertEqual((code, r["changed_files"], r["release"]), (2, 1, "HOLD"))

    def test_extra_source_fails_closed(self):
        (self.src / "foreign.cs").write_text("injected")
        code, r = self.call()
        self.assertEqual((code, r["unexpected_files"]), (2, 1))

    def test_changed_exe_fails_closed(self):
        self.exe.write_bytes(b"other binary")
        code, r = self.call()
        self.assertEqual((code, r["exe_match"]), (2, False))

    def test_manifest_tamper_fails_receipt_binding(self):
        m = json.loads(self.man.read_text())
        m["files"][0]["sha256"] = "0" * 64
        self.man.write_text(json.dumps(m))
        code, r = self.call()
        self.assertEqual((code, r["result"]), (3, "PROVENANCE_UNVERIFIED_HOLD"))

    def test_path_traversal_rejected_after_receipt_resign(self):
        m = json.loads(self.man.read_text())
        m["files"][0]["path"] = "../secret"
        self.man.write_text(json.dumps(m))
        r = json.loads(self.receipt.read_text())
        r["staged_source_manifest_sha256"] = hashlib.sha256(self.man.read_bytes()).hexdigest()
        self.receipt.write_text(json.dumps(r))
        # Test path validation with newly fixed independent anchors as well.
        self.trusted_manifest_sha = hashlib.sha256(self.man.read_bytes()).hexdigest()
        self.trusted_receipt_sha = hashlib.sha256(self.receipt.read_bytes()).hexdigest()
        code, result = self.call()
        self.assertEqual((code, result["result"]), (3, "PROVENANCE_UNVERIFIED_HOLD"))

    def test_missing_owner_exe_fails_closed(self):
        self.exe.unlink()
        code, r = self.call()
        self.assertEqual((code, r["result"]), (3, "PROVENANCE_UNVERIFIED_HOLD"))

    def test_source_symlink_denied(self):
        target = self.src / "index.html"
        target.unlink()
        try:
            target.symlink_to(self.base / "outside")
        except OSError:
            self.skipTest("Windows test process lacks symlink privilege")
        code, r = self.call()
        self.assertEqual((code, r["result"]), (3, "PROVENANCE_UNVERIFIED_HOLD"))

    def test_jointly_forged_manifest_receipt_fail_external_anchors(self):
        self.exe.write_bytes(b"forged exe")
        file = self.src / "MainWindow.xaml.cs"
        file.write_bytes(b"forged source")
        m = json.loads(self.man.read_text())
        m["files"][0]["bytes"] = file.stat().st_size
        m["files"][0]["sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
        self.man.write_text(json.dumps(m))
        r = json.loads(self.receipt.read_text())
        r["staged_source_manifest_sha256"] = hashlib.sha256(self.man.read_bytes()).hexdigest()
        r["exe_sha256"] = hashlib.sha256(self.exe.read_bytes()).hexdigest()
        self.receipt.write_text(json.dumps(r))
        code, result = self.call()
        self.assertEqual((code, result["result"]), (3, "PROVENANCE_UNVERIFIED_HOLD"))

    def test_wrong_trusted_git_sha_fail(self):
        self.trusted_git_sha = "c" * 40
        code, result = self.call()
        self.assertEqual((code, result["result"]), (3, "PROVENANCE_UNVERIFIED_HOLD"))


if __name__ == "__main__":
    unittest.main()
