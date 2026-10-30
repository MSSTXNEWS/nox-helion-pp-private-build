"""NOX E06 regression: the existing P01 verifier and builder must agree."""
from pathlib import Path
import hashlib
import re
import unittest


BUILDER = Path(__file__).resolve().parents[2] / "coordination" / "e06" / "build_onehost_installer.ps1"


class OneHostManifestContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = BUILDER.read_text(encoding="utf-8")

    def test_t06_run_id_gate_before_any_side_effect(self):
        """A malformed receipt/build ID must not reach output staging."""
        guard = self.source.find("E06_BUILD_INVALID_RUN_ID")
        self.assertGreater(guard, 0)
        self.assertIn(r"\A[A-Za-z0-9][A-Za-z0-9._:-]{1,127}\z", self.source)
        for token in (
            "Assert-E06PlainPathAncestors -Candidate $SourceRoot",
            "New-Item -ItemType Directory -Path $OutputRoot",
            "& dotnet publish $project",
        ):
            self.assertGreater(self.source.find(token), guard)

    def test_t06_missing_nsis_does_not_leave_disposable_stage(self):
        """Discover tools before any D02 stage, WPF publish or output write."""
        nsis = self.source.find("NSIS_BINARY_PATH_HOLD")
        self.assertGreater(nsis, 0)
        self.assertEqual(self.source.count("$makensis=Get-Command 'makensis.exe'"), 1)
        for token in (
            "if ($wantsCreative) {",
            "New-Item -ItemType Directory -Path $OutputRoot",
            "& dotnet publish $project",
        ):
            self.assertGreater(self.source.find(token), nsis)

    def test_hidden_and_system_payload_files_are_hashed(self):
        self.assertRegex(
            self.source,
            r"Get-ChildItem\s+-LiteralPath\s+\$payload\s+-File\s+-Recurse\s+-Force\s+\|",
        )

    def test_owner_compatible_numeric_version_in_both_places(self):
        manifest = re.search(r"\$manifest=\[ordered\]@\{[^\n]+version='([^']+)'", self.source)
        cli = re.search(r"'/DAPP_VERSION=([^']+)'", self.source)
        self.assertIsNotNone(manifest)
        self.assertIsNotNone(cli)
        self.assertEqual(manifest.group(1), cli.group(1))
        self.assertRegex(manifest.group(1), r"^\d+\.\d+\.\d+$")
        self.assertNotIn("16.0.0-rc", self.source)

    def test_original_owner_verifier_and_release_hold_are_preserved(self):
        self.assertIn("Verify-Payload.ps1", self.source)
        self.assertIn("ORIGINAL_NSIS_PAYLOAD_SHA_GATE_HOLD", self.source)
        self.assertIn("release_accepted=$false", self.source)
        self.assertIn("installer_lifecycle_tested=$false", self.source)


    def test_live_d02_two_level_owner_hash_graph(self):
        root = Path(__file__).resolve().parents[2]
        stage_path = root / "integrations/wow200/stage_wow200.py"
        stage = stage_path.read_text(encoding="utf-8")

        def git_blob(path):
            data = path.read_bytes()
            return hashlib.sha1(
                ("blob " + str(len(data))).encode("ascii") + bytes([0]) + data
            ).hexdigest()

        for name in ("nox-cinema.mjs", "nox-cinema.css"):
            active = git_blob(root / "proposals/NOX-CINEMA-FX" / name)
            legacy = git_blob(root / "integrations/wow200/proposals/NOX-CINEMA-FX" / name)
            self.assertIn(f'"active_blob": "{active}"', stage)
            self.assertIn(f'"legacy_blob": "{legacy}"', stage)
            self.assertNotEqual(active, legacy)
        self.assertIn(
            "$wowScriptBlob -cne '" + git_blob(stage_path) + "'",
            self.source,
        )
        self.assertIn("OWNER1_D02_ENGINE_SHA_HOLD", stage)
        self.assertIn("D02_PINNED_STAGE_SCRIPT_SHA_HOLD", self.source)

    def test_original_wow_manifest_and_creative_stage_pin(self):
        root = Path(__file__).resolve().parents[2]
        stage = (root / "integrations/wow200/stage_wow200.py").read_text("utf-8")

        def blob(path):
            data = path.read_bytes()
            return hashlib.sha1(
                ("blob " + str(len(data)) + "\0").encode("ascii") + data
            ).hexdigest()

        expected = (
            ('DONOR_MANIFEST_BLOB = "', root / "integrations/wow200/DONOR_BLOBS.json"),
            ('PACK01_CATALOG_BLOB = "', root / "proposals/NOX-PACK01-50/catalog.json"),
        )
        for prefix, path in expected:
            self.assertIn(prefix + blob(path) + '"', stage)
        self.assertIn(
            "$creativeScriptBlob -cne '" +
            blob(root / "integrations/creative/stage_creative.py") + "'",
            self.source,
        )

    def test_azure_e07_owner_receipt_contract(self):
        root = Path(__file__).resolve().parents[2]
        azure = (root / "azure-pipelines-nox-v16.yml").read_text(encoding="utf-8")
        handoff = (root / "coordination/e06/Emit-E07ImmutableHandoff.ps1").read_text(encoding="utf-8")
        required = set(re.findall(
            r"\[Parameter\(Mandatory=\$true\)\]\[string\]\$(\w+)",
            handoff, re.IGNORECASE))
        args = re.search(r"^\s*\$args\s*=\s*@\{([^\n]+)\}", azure, re.MULTILINE)
        self.assertIsNotNone(args)
        supplied = set(re.findall(r"(\w+)\s*=", args.group(1)))
        self.assertTrue(required)
        self.assertEqual(required - supplied, set())
        self.assertIn("Owner729Receipt=(Join-Path", azure)
        self.assertIn("nox-original-729-owner-pinned.json", azure)
        self.assertNotIn("Owner729Receipt=$pinnedManifest", azure)
        self.assertIn("--out $pinnedManifest", azure)
        self.assertIn("BUILD_ONLY_NOT_E07_ACCEPTED", azure)


if __name__ == "__main__":
    unittest.main()
