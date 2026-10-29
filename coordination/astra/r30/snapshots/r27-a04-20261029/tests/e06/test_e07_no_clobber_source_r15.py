"""Source safety tests for E07 immutable handoff; not native Windows acceptance."""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HANDOFF = ROOT / "coordination/e06/Emit-E07ImmutableHandoff.ps1"
WINDOWS = ROOT / "tests/e06/Test-E07NoClobberConcurrent.ps1"

def safe(text: str) -> bool:
    return (
        text.count("function WriteReceiptNoClobber(") == 1
        and text.count("WriteReceiptNoClobber $Output ((") == 1
        and text.count("[IO.FileMode]::CreateNew") >= 1
        and text.count("[IO.FileShare]::None") >= 1
        and text.count("$stream.Flush($true)") >= 1
        and text.count("$stream.Dispose()") >= 1
        and "[IO.File]::WriteAllText($Output" not in text
        and text.count('Write-Host "E07_BUILDID_SEALED') == 1
        and "release_accepted=$false" in text
    )

class ExclusiveReceiptSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = HANDOFF.read_text(encoding="utf-8")
        cls.native = WINDOWS.read_text(encoding="utf-8")
    def test_actual_owner_source_guarantees_exclusive_create(self):
        self.assertTrue(safe(self.source))
    def test_new_create_cannot_be_swapped_to_truncating_create(self):
        self.assertFalse(safe(self.source.replace("[IO.FileMode]::CreateNew","[IO.FileMode]::Create",1)))
    def test_no_shared_write_access(self):
        self.assertFalse(safe(self.source.replace("[IO.FileShare]::None","[IO.FileShare]::ReadWrite",1)))
    def test_failed_flush_cannot_count_as_durable_write(self):
        self.assertFalse(safe(self.source.replace("$stream.Flush($true)","",1)))
    def test_dispose_remains_mandatory(self):
        self.assertFalse(safe(self.source.replace("$stream.Dispose()","",1)))
    def test_legacy_overwrite_rejected(self):
        self.assertFalse(safe(self.source + "\n[IO.File]::WriteAllText($Output,'bad')"))
    def test_native_harness_uses_actual_function_ast(self):
        self.assertIn("FunctionDefinitionAst", self.native)
        self.assertIn("Invoke-Expression $writerText",self.native)
        self.assertIn("E07_NO_CLOBBER_EXISTING_FILE_OVERWRITTEN",self.native)
        self.assertIn("E07_NO_CLOBBER_CONCURRENT_WRITERS_FAILED",self.native)
        self.assertIn("ThreadJob",self.native)
    def test_original_source_lock_and_unaccepted_status_remain(self):
        self.assertIn("E07_OWNER_729_FILE_SHA_DIFFERS",self.source)
        self.assertIn("E07_OWNER_SOURCE_PART_IDENTITY_MISMATCH",self.source)
        self.assertIn("independent_e07_cases_accepted=0",self.source)
        self.assertIn("release_accepted=$false",self.source)
if __name__ == '__main__':
    unittest.main()
