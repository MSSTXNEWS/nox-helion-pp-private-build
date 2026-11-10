"""Original E06 builder PS5.1 hash compatibility regression (not installed E07)."""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "coordination/e06/build_onehost_installer.ps1"
COMPILER = ROOT / "coordination/e06/t06_compile_original_wpf_p02.py"
WEBVIEW2_PIN = "e9d91ac3ed0bf5437ff38f07d2179a9e7a130835c4d0d1be49fa2c563f0e8bd1"


class E06WindowsPS51BuilderHashCompat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = BUILDER.read_text(encoding="utf-8")

    def test_no_net5_only_static_digest_api_and_no_source_gates_lost(self):
        for forbidden in ("::HashData(", "[Convert]::ToHexString"):
            self.assertNotIn(forbidden, self.source)
        for retained in (
            "D02_PINNED_STAGE_SCRIPT_SHA_HOLD",
            "P03_REVIEW_REGISTRY_SOURCE_SHA_HOLD",
            "P03_REVIEW_REGISTRY_PAYLOAD_SHA_HOLD",
            "E06_WEBVIEW2_PREFLIGHT_REPLACEMENT_GUARD_HOLD",
            "NSIS_PREINSTALLED_BINARY_REQUIRED_NO_AUTO_INSTALL",
            "NOX.P01.Shell.exe",
        ):
            self.assertIn(retained, self.source)

    def test_original_git_blob_sha1_preimage_and_disposal_preserved(self):
        self.assertEqual(self.source.count("function Get-E06CanonicalGitBlobSha("), 1)
        fn = self.source.split("  function Get-E06CanonicalGitBlobSha(", 1)[1].split(
            "\n  $creativeScriptBlob=", 1
        )[0]
        for part in (
            "D02_STAGE_SCRIPT_BARE_CR_HOLD",
            '[Text.Encoding]::ASCII.GetBytes("blob $($normalized.Length)',
            '$gitBlobHasher=[Security.Cryptography.SHA1]::Create()',
            '$sha=$gitBlobHasher.ComputeHash($all)',
            '$gitBlobHasher.Dispose()',
            "[BitConverter]::ToString($sha).Replace('-','')",
        ):
            self.assertIn(part, fn)

    def test_p03_rights_registry_sha256_fail_closed_on_original_digest(self):
        self.assertEqual(self.source.count(
            "$registryHasher=[Security.Cryptography.SHA256]::Create()"
        ), 1)
        digest = self.source.split(
            "$registryCanonicalBytes=$registryUtf8.GetBytes($registryCanonicalText)", 1
        )[1].split("\nif ($registryCanonicalSha -cne $p03RegistrySha)", 1)[0]
        self.assertIn("$registryHasher.ComputeHash($registryCanonicalBytes)", digest)
        self.assertIn("$registryHasher.Dispose()", digest)
        self.assertIn("[BitConverter]::ToString(", digest)
        self.assertIn("throw 'P03_REVIEW_REGISTRY_UNSAFE_ENCODING'", self.source)

    def test_signed_webview2_donor_exact_block_sha_unmodified(self):
        anchor = "$webviewReplacement=@'\n"
        self.assertEqual(self.source.count(anchor), 1)
        replacement = self.source.split(anchor, 1)[1].split("\n'@", 1)[0] + "\n"
        self.assertEqual(hashlib.sha256(replacement.encode("utf-8")).hexdigest(), WEBVIEW2_PIN)
        self.assertIn(
            'WEBVIEW2_E06_REGISTRY_BLOCK_SHA256="' + WEBVIEW2_PIN + '"',
            COMPILER.read_text(encoding="utf-8"),
        )

    def test_real_powershell_digest_if_host_has_powershell(self):
        ps = next((p for p in (
            shutil.which("powershell.exe"), shutil.which("powershell"),
            shutil.which("pwsh"),
        ) if p), None)
        if not ps:
            self.skipTest("No native PowerShell here; source checks still mandatory")
        fn = "  function Get-E06CanonicalGitBlobSha(" + self.source.split(
            "  function Get-E06CanonicalGitBlobSha(", 1
        )[1].split("\n  $creativeScriptBlob=", 1)[0]
        digest = self.source.split(
            "$registryCanonicalBytes=$registryUtf8.GetBytes($registryCanonicalText)", 1
        )[1].split("\nif ($registryCanonicalSha -cne $p03RegistrySha)", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / "fixture.txt"
            p.write_bytes(b"abc\r\n")
            escaped_path = str(p).replace("'", "''")
            script = (
                "$ErrorActionPreference='Stop'\nSet-StrictMode -Version Latest\n"
                + fn + "\n"
                + "$blob=Get-E06CanonicalGitBlobSha '" + escaped_path + "'\n"
                + "$registryCanonicalBytes=[Text.Encoding]::UTF8.GetBytes('abc')\n"
                + digest + "\n"
                + "Write-Output ('BLOB='+$blob)\n"
                + "Write-Output ('REGISTRY='+$registryCanonicalSha)\n"
            )
            result = subprocess.run(
                [ps, "-NoProfile", "-NonInteractive", "-Command", script],
                text=True, capture_output=True, check=False, timeout=30,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(
            "BLOB=" + hashlib.sha1(b"blob 4\x00abc\n").hexdigest(), result.stdout
        )
        self.assertIn(
            "REGISTRY=" + hashlib.sha256(b"abc").hexdigest(), result.stdout
        )


if __name__ == "__main__":
    unittest.main()
