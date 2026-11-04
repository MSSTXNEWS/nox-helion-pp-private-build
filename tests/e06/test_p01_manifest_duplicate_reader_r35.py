"""P01 source-only contract for the built-in .NET PS5.1 JSON reader.

Native PowerShell 5.1 fixtures remain a separate T08 criterion: this test
does not attest installer execution or installed-file deletion.
"""
from pathlib import Path
import os
import unittest

ROOT=Path(__file__).resolve().parents[2]
INSTALLER=Path(os.environ.get("NOX_PINNED_P01_INSTALLER_PATH",
                               ROOT/"stage/proposals/P01/C09/Installer"))
FILES=("Verify-Payload.ps1","Remove-InstalledPayload.ps1")


class ManifestDuplicateReaderContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources={name:(INSTALLER/name).read_text(encoding="utf-8") for name in FILES}

    def test_both_paths_use_windows_builtin_reader(self):
        for name,source in self.sources.items():
            with self.subTest(name=name):
                self.assertIn("Add-Type -AssemblyName System.Runtime.Serialization",source)
                self.assertIn("JsonReaderWriterFactory]::CreateJsonReader($bytes,$quotas)",source)

    def test_case_insensitive_per_object_member_rejection(self):
        for name,source in self.sources.items():
            with self.subTest(name=name):
                self.assertIn("[StringComparer]::OrdinalIgnoreCase",source)
                self.assertIn("if (-not $parent.Names.Add($reader.LocalName))",source)
                self.assertIn("throw 'duplicate JSON member'",source)

    def test_preflight_bounds_untrusted_manifest(self):
        for name,source in self.sources.items():
            with self.subTest(name=name):
                self.assertIn("$bytes.Length -gt 16777216",source)
                self.assertIn("$quotas.MaxDepth = 32",source)
                self.assertIn("$quotas.MaxArrayLength = 16777216",source)

    def test_size_checked_before_readallbytes(self):
        for name,source in self.sources.items():
            with self.subTest(name=name):
                self.assertIn("P01_MANIFEST_PRE_READ_SIZE_HOLD",source)
                self.assertLess(source.index("$boundedInfo.Length -gt 16777216"),
                                source.index("[IO.File]::ReadAllBytes($Path)"))

    def test_verify_precedes_any_json_object_parsing(self):
        src=self.sources["Verify-Payload.ps1"]
        self.assertLess(src.index("Assert-P01UniqueManifestMembers $manifestFull"),
                        src.index("| ConvertFrom-Json"))

    def test_uninstall_precedes_json_parse_and_file_deletion(self):
        src=self.sources["Remove-InstalledPayload.ps1"]
        self.assertLess(src.index("Assert-P01UniqueManifestMembers $manifestPath"),
                        src.index("| ConvertFrom-Json"))
        self.assertLess(src.index("Assert-P01UniqueManifestMembers $manifestPath"),
                        src.index("Remove-Item -LiteralPath $entry.Full"))

    def test_original_owner_and_no_loss_contract_remains(self):
        self.assertIn("P01_PAYLOAD_SHA256_PASS",self.sources["Verify-Payload.ps1"])
        self.assertIn("P01_UNINSTALL_PAYLOAD_PASS",self.sources["Remove-InstalledPayload.ps1"])
        self.assertIn("P01_UNINSTALL_MODIFIED_FILE",self.sources["Remove-InstalledPayload.ps1"])

    def test_reader_rejects_nonobject_root_and_closes(self):
        for name,source in self.sources.items():
            with self.subTest(name=name):
                self.assertIn("$kind -cne 'object'",source)
                self.assertIn("$reader.Close()",source)


if __name__=="__main__":
    unittest.main()
