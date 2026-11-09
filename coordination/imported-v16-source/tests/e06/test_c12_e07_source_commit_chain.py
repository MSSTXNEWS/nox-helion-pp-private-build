"""C12 source-only regression for the existing E06→E07 same-SHA chain.

Run: python -m unittest tests/e06/test_c12_e07_source_commit_chain.py
This deliberately does not award E07 or assert Windows execution.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
BUILD = ROOT / "coordination/e06/build_onehost_installer.ps1"
E07 = ROOT / "coordination/e06/Emit-E07ImmutableHandoff.ps1"


def assert_original_nsis_references(case, build):
    """Four reviewed uses of ONE owner script, including the newer path guard."""
    expected = (
        "Assert-E06PlainPathAncestors -Candidate (Join-Path $installer 'NOX-HELION-Setup.nsi') -Scope 'NSIS_OWNER'",
        "if (!(Test-Path -LiteralPath (Join-Path $installer 'NOX-HELION-Setup.nsi') -PathType Leaf)) { throw 'ORIGINAL_NSIS_OWNER_SOURCE_MISSING' }",
        "$c11NsiPath=Join-Path $installer 'NOX-HELION-Setup.nsi'",
    )
    for reference in expected:
        case.assertEqual(build.count(reference), 1, reference)
    compiler_calls = re.findall(r"(?m)^& \$makensisPath [^\r\n]*$", build)
    case.assertEqual(len(compiler_calls), 1, "one original NSIS compile invocation")
    case.assertTrue(compiler_calls[0].endswith(
        "(Join-Path $installer 'NOX-HELION-Setup.nsi')"),
        "the existing compiler must target the same original owner script")
    case.assertEqual(build.count("NOX-HELION-Setup.nsi"), len(expected) + 1)


class E07SameSourceCommit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = BUILD.read_text(encoding="utf-8")
        cls.handoff = E07.read_text(encoding="utf-8")

    def test_exact_repo_head_frozen_before_builder_work(self):
        self.assertIn("$e06RepoRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path", self.build)
        self.assertIn("$e06SourceHead=((& git -C $e06RepoRoot rev-parse HEAD)", self.build)
        self.assertLess(self.build.index("$e06SourceHead="),
                        self.build.index("$installer=Join-Path $source 'Installer'"))

    def test_commit_drift_rejected_before_e06_receipt(self):
        self.assertIn("throw 'E06_SOURCE_HEAD_CHANGED_DURING_BUILD'", self.build)
        self.assertLess(self.build.index("$e06HeadAtReceipt="), self.build.index("$receipt=[ordered]@{"))
        self.assertIn("source_commit_sha1=$e06SourceHead;", self.build)

    def test_e07_anchors_git_to_script_repo_not_caller_cwd(self):
        self.assertIn("$e07RepoRoot=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '../..')).Path", self.handoff)
        self.assertIn("git -C $e07RepoRoot rev-parse HEAD", self.handoff)
        self.assertNotIn("git rev-parse HEAD", self.handoff)

    def test_e07_requires_exact_e06_source_commit(self):
        self.assertIn("([string]$onehost.source_commit_sha1) -cne $commit -or", self.handoff)
        self.assertIn("throw 'E07_SETUP_EXE_RECEIPT_SHA_DRIFT'", self.handoff)
        gate=self.handoff.index("if ($onehost.schema")
        self.assertLess(gate,self.handoff.index("$identity="))

    def test_e07_head_checked_again_before_immutable_handoff(self):
        self.assertIn("throw 'E07_CHECKOUT_SHA_DRIFT_BEFORE_SEAL'", self.handoff)
        self.assertLess(self.handoff.index("$e07HeadAtSeal="),
                        self.handoff.index("WriteReceiptNoClobber $Output"))
        self.assertIn("release_accepted=$false", self.handoff)

    def test_existing_onehost_and_nsis_not_replaced(self):
        assert_original_nsis_references(self, self.build)
        self.assertIn("NOX-E06-ONEHOST-DIAGNOSTIC-NSIS-v1", self.build)
        self.assertIn("NOX_V16_E07_IMMUTABLE_HANDOFF_V1", self.handoff)


    def test_nsis_contract_rejects_removed_guard_even_with_same_name_count(self):
        guard = "Assert-E06PlainPathAncestors -Candidate (Join-Path $installer 'NOX-HELION-Setup.nsi') -Scope 'NSIS_OWNER'"
        changed = self.build.replace(guard, "# removed guard for NOX-HELION-Setup.nsi", 1)
        self.assertNotEqual(changed, self.build)
        with self.assertRaises(AssertionError):
            assert_original_nsis_references(self, changed)

    def test_nsis_contract_rejects_redirected_compiler_with_same_name_count(self):
        call = re.findall(r"(?m)^& \$makensisPath [^\r\n]*$", self.build)[0]
        changed = self.build.replace(call, call.replace(
            "(Join-Path $installer 'NOX-HELION-Setup.nsi')",
            "(Join-Path $otherOwner 'NOX-HELION-Setup.nsi')"), 1)
        self.assertNotEqual(changed, self.build)
        with self.assertRaises(AssertionError):
            assert_original_nsis_references(self, changed)

    def test_nsis_contract_rejects_second_compile_invocation(self):
        call = re.findall(r"(?m)^& \$makensisPath [^\r\n]*$", self.build)[0]
        with self.assertRaises(AssertionError):
            assert_original_nsis_references(self, self.build + "\n" + call + "\n")


if __name__ == "__main__":
    unittest.main()
