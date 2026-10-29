"""G3-A R30/R10 source-only regression: public catalog entry bypass of native review.

Run from an existing repository checkout:
    python -m unittest discover -s Packages/P03/Admission -p 'test_g3a_r30_r10_*.py'
No Windows build, download, Ollama or network is required.
These are Python source-contract tests, NOT an execution of the C# property.
"""
import re
import unittest
from pathlib import Path
import sys

_HERE = Path(__file__).resolve().parent
_P03 = _HERE.parent
_CATALOG = _P03 / "Source" / "P03.ModelCenter" / "ModelCatalog.cs"
_REGISTRY = _P03 / "Source" / "P03.ModelCenter" / "ModelArtifactReviewRegistry.cs"
sys.path.insert(0, str(_HERE))
import p03_modelcenter_gate as gate  # noqa: E402


class G3AR10CatalogDirectEntryGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = _CATALOG.read_text(encoding="utf-8")
        cls.registry = _REGISTRY.read_text(encoding="utf-8")
        cls.offer = cls.catalog.split("public bool CanOfferOneClickPull =>", 1)[1].split(";", 1)[0]

    def test_still_thirty_discovery_families(self):
        self.assertEqual(len(re.findall(r'\\bFamily\\("', self.catalog)), 30)
        self.assertIn("CatalogEvidenceStatus.FamilyListed", self.catalog)

    def test_public_record_cannot_use_nonblank_revision_only(self):
        self.assertIn("IsNativeReviewedRevision(ImmutableRevision)", self.offer)
        self.assertNotIn("!string.IsNullOrWhiteSpace(ImmutableRevision)", self.offer)

    def test_reviewed_revision_is_actual_sha_format(self):
        self.assertIn("IsSha256(revision)", self.catalog)
        self.assertIn('revision.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase)', self.catalog)
        self.assertIn("IsSha256(revision[7..])", self.catalog)

    def test_public_record_must_match_owner_tag(self):
        self.assertIn("IsCanonicalOwnerTag(ExactTag, Id)", self.offer)
        self.assertIn('tag.StartsWith(family + ":", StringComparison.OrdinalIgnoreCase)', self.catalog)

    def test_latest_tag_and_dotted_spoof_rejected(self):
        self.assertIn('!tag.EndsWith(":latest", StringComparison.OrdinalIgnoreCase)', self.catalog)
        self.assertIn('!tag.Contains("..", StringComparison.Ordinal)', self.catalog)

    def test_catalog_tag_has_bounded_allowlist_pattern(self):
        self.assertIn('tag is { Length: <= 160 }', self.catalog)
        self.assertIn('tag, @"^[A-Za-z0-9][A-Za-z0-9._-]*:[A-Za-z0-9][A-Za-z0-9._-]*$"', self.catalog)

    def test_both_evidence_uris_share_structural_gate(self):
        self.assertIn("IsReviewedHttpsEvidence(LicenseEvidenceUri)", self.offer)
        self.assertIn("IsReviewedHttpsEvidence(CompatibilityEvidenceUri)", self.offer)

    def test_evidence_gate_rejects_alt_port_loopback_and_userinfo(self):
        for phrase in ("uri.IsAbsoluteUri", "uri.IsDefaultPort", "!uri.IsLoopback",
                       "string.IsNullOrEmpty(uri.UserInfo)", "string.IsNullOrEmpty(uri.Fragment)",
                       'uri.Host.EndsWith(".local", StringComparison.OrdinalIgnoreCase)'):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.catalog)

    def test_existing_owner_registry_digest_policy_retained(self):
        self.assertIn("Sha(c.ImmutableRevision)", self.registry)
        self.assertIn('c.ImmutableRevision.StartsWith("sha256:",StringComparison.OrdinalIgnoreCase)', self.registry)

    def test_previous_zero_forty_hex_regression_full_python_import(self):
        self.assertFalse(gate._immutable_revision("0" * 40, "ollama"))
        self.assertFalse(gate._immutable_revision("0" * 40, "gguf"))
        self.assertTrue(gate._immutable_revision("a" * 40, "ollama"))

    def test_previous_zero_sixtyfour_hex_regression_full_python_import(self):
        self.assertFalse(gate._immutable_revision("0" * 64, "ollama"))
        self.assertFalse(gate._immutable_revision("sha256:" + "0" * 64, "ollama"))
        self.assertTrue(gate._immutable_revision("sha256:" + "a" * 64, "ollama"))


if __name__ == "__main__":
    unittest.main()
