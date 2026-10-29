"""G3-A R30 R11: source-contract guard for direct ModelCatalogEntry records.

These checks read real C# source from this checkout; they are not .NET
behavioral tests, native session attestation, or permission to download.
Run: python -m unittest discover -s Packages/P03/Admission -p 'test_g3a_r30_r11_*.py'
"""
from pathlib import Path
import re
import unittest


P03 = Path(__file__).resolve().parent.parent
CATALOG = P03 / "Source" / "P03.ModelCenter" / "ModelCatalog.cs"
REGISTRY = P03 / "Source" / "P03.ModelCenter" / "ModelArtifactReviewRegistry.cs"


class G3AR11OfficialOriginSourceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CATALOG.read_text(encoding="utf-8")
        cls.registry = REGISTRY.read_text(encoding="utf-8")
        match = re.search(r"public bool CanOfferOneClickPull\s*=>\s*(.*?);", cls.source, re.S)
        assert match is not None, "Catalog eligibility property missing"
        cls.eligibility = match.group(1)
        match = re.search(r"private static bool IsCanonicalOfficialFamilyPage\s*\(.*?\)\s*=>\s*(.*?);", cls.source, re.S)
        assert match is not None, "Canonical source guard missing"
        cls.origin = match.group(1)

    def test_direct_public_record_uses_origin_gate(self):
        self.assertIn("IsCanonicalOfficialFamilyPage(Id, OfficialLibraryPage)", self.eligibility)

    def test_unknown_family_not_allowed(self):
        self.assertIn("ModelCatalog.OfficialFamilies.Any", self.origin)
        self.assertIn("string.Equals(entry.Id, family, StringComparison.OrdinalIgnoreCase)", self.origin)

    def test_requires_absolute_https_default_port(self):
        for token in ("page.IsAbsoluteUri", "Uri.UriSchemeHttps", "page.IsDefaultPort"):
            self.assertIn(token, self.origin)

    def test_canonical_ollama_host_only(self):
        self.assertIn('page.Host.Equals("ollama.com", StringComparison.OrdinalIgnoreCase)', self.origin)

    def test_exact_family_page_path(self):
        self.assertIn('page.AbsolutePath.Equals("/library/" + family, StringComparison.OrdinalIgnoreCase)', self.origin)

    def test_reject_uri_userinfo_query_fragment(self):
        for token in ("string.IsNullOrEmpty(page.UserInfo)", "string.IsNullOrEmpty(page.Query)",
                      "string.IsNullOrEmpty(page.Fragment)"):
            self.assertIn(token, self.origin)

    def test_digest_rights_resource_gates_not_removed(self):
        for token in ("IsSha256(ExpectedSha256)", "IsSha256(ExpectedManifestDigestSha256)",
                      "IsNativeReviewedRevision(ImmutableRevision)",
                      "IsReviewedHttpsEvidence(LicenseEvidenceUri)",
                      "IsReviewedHttpsEvidence(CompatibilityEvidenceUri)",
                      "RequiredDiskBytes >= ArtifactBytes", "CompatibilityReviewed"):
            self.assertIn(token, self.eligibility)

    def test_preserve_family_catalog_minimum_and_owner_factory(self):
        families = re.findall(r'Family\("[a-z0-9._-]+",', self.source)
        self.assertGreaterEqual(len(families), 24)
        self.assertIn("ModelCatalog.Get(c.FamilyId) with", self.registry)
        self.assertIn("if (!promoted.CanOfferOneClickPull) return false;", self.registry)


if __name__ == "__main__":
    unittest.main()
