"""Source-shape regression for the existing P03 native model-retry boundary.

This is NOT a .NET compilation or native ACK proof. The tests pin security
requirements in the existing C# source and run without new dependencies.
"""
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'Packages/P03/Source/P03.ModelCenter/ModelCenterNativeRoutes.cs'

class ReviewedRetrySourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding='utf-8')
        cls.route = cls.source.split('case "models.retry":', 1)[1].split('case "models.gguf.import":', 1)[0]
        cls.guard = cls.source.split('private static bool MatchesRetryProvenance(', 1)[1].split('private static void RequireHardware', 1)[0]

    def test_native_consent_unchanged(self):
        self.assertIn('if (!nativeConsent)', self.route)

    def test_unique_reviewed_model_required(self):
        self.assertIn('retryModels.Length!=1', self.route)
        self.assertIn('!MatchesRetryProvenance(previous,retryModels[0])', self.route)

    def test_stale_registry_fails_closed(self):
        self.assertIn('currentReview.Length!=1', self.route)
        self.assertIn('P03_REVIEW_CHANGED', self.route)

    def test_gguf_picker_rechecks_unique_registry_and_pinned_evidence(self):
        gguf = self.source.split('case "models.gguf.import":', 1)[1].split('case "models.pull":', 1)[0]
        self.assertIn('currentImportReview.Length!=1', gguf)
        self.assertIn('currentImportReview[0]!=importModel', gguf)
        self.assertIn('currentImportReview[0].ExpectedSha256,pinnedImportSha', gguf)
        self.assertIn('currentImportReview[0].ArtifactBytes!=pinnedImportBytes', gguf)
        self.assertIn('currentImportReview[0].ReviewedRightsReceiptId,pinnedImportRights', gguf)
        self.assertIn('currentImportReview[0].LicenseEvidenceUri?.AbsoluteUri,pinnedImportLicense', gguf)
        self.assertLess(gguf.index('currentImportReview.Length!=1'), gguf.index('EnqueueVerifiedGgufAsync'))
        self.assertIn('ct.ThrowIfCancellationRequested();', gguf)

    def test_stop_before_native_retry(self):
        self.assertLess(self.route.index('ct.ThrowIfCancellationRequested();'), self.route.index('_worker.RetryAsync('))

    def test_no_implicit_installs(self):
        self.assertNotIn('Process.Start(', self.route)
        self.assertNotIn('DownloadFile(', self.route)

    def test_same_license(self):
        self.assertIn('review.LicenseEvidenceUri is not Uri evidence', self.guard)
        self.assertIn('!evidence.IsAbsoluteUri', self.guard)
        self.assertIn('evidence.Scheme != Uri.UriSchemeHttps', self.guard)
        self.assertIn('string.IsNullOrWhiteSpace(prior.LicenseSource)', self.guard)
        self.assertIn('!string.Equals(prior.LicenseSource, evidence.AbsoluteUri, StringComparison.Ordinal)', self.guard)

    def test_ollama_manifest_and_immutable_revision(self):
        self.assertIn('prior.ExpectedOllamaDigest', self.guard)
        self.assertIn('review.ExpectedManifestDigestSha256', self.guard)
        self.assertIn('prior.ImmutableRevision', self.guard)
        self.assertIn('review.ImmutableRevision', self.guard)

    def test_gguf_sha_bytes_and_rights_receipt(self):
        for name in ('prior.ExpectedLocalSha256', 'review.ExpectedSha256',
                     'prior.ExpectedLocalBytes', 'review.ArtifactBytes',
                     'prior.RightsReceiptId', 'review.ReviewedRightsReceiptId'):
            self.assertIn(name, self.guard)

    def test_other_kind_denied(self):
        self.assertIn('_ => false', self.guard)

    def test_retry_unique_current_registry_and_rights(self):
        self.assertIn('currentReview.Length!=1', self.route)
        self.assertIn('!MatchesRetryProvenance(previous,currentReview[0])', self.route)
        self.assertIn('evidence.Scheme != Uri.UriSchemeHttps', self.guard)
        self.assertIn('string.IsNullOrWhiteSpace(prior.LicenseSource)', self.guard)
        self.assertIn('string.IsNullOrWhiteSpace(prior.ImmutableRevision)', self.guard)
        self.assertIn('string.IsNullOrWhiteSpace(prior.RightsReceiptId)', self.guard)

if __name__ == '__main__':
    unittest.main()
