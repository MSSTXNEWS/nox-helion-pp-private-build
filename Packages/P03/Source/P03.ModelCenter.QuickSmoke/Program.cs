using Nox.P03;
if (!ModelQuickActions.VerifyDiscoveryIntegrity()) throw new Exception("DISCOVERY_INTEGRITY_FAILED");
var slots = ModelQuickActions.OllamaSlots;
if (slots.Length != 20 || ModelQuickActions.ExternalLeads.Count(x=>x.DownloadAllowed) != 0)
    throw new Exception("UNREVIEWED_MODEL_PROMOTION");
if (ModelQuickActions.TryResolveApprovedOllamaPull("qwen3", ModelCatalog.OfficialFamilies, true, true, out _))
    throw new Exception("FAMILY_CARD_CANNOT_INSTALL");
if (ModelQuickActions.TryResolveApprovedOllamaPull("qwen3", ModelCatalog.OfficialFamilies, false, true, out _))
    throw new Exception("LICENSE_ACK_REQUIRED");
if (ModelQuickActions.TryResolveApprovedOllamaPull("unknown", ModelCatalog.OfficialFamilies, true, true, out _))
    throw new Exception("UNKNOWN_MODEL_ALLOWED");
var fixture = ModelCatalog.Get("qwen3") with
{
    EvidenceStatus = CatalogEvidenceStatus.ArtifactVerified,
    ExactTag = "qwen3:0.6b", Version = "unit-test", License = "synthetic-test-license",
    ArtifactBytes = 8192, RequiredDiskBytes = 16384, RecommendedRamBytes = 32768,
    ExpectedSha256 = new string('a',64), ExpectedManifestDigestSha256 = new string('b',64),
    ImmutableRevision = new string('c',64), CompatibilityReviewed = true,
    LicenseEvidenceUri = new Uri("https://ollama.com/library/qwen3"),
    CompatibilityEvidenceUri = new Uri("https://ollama.com/library/qwen3")
};
if (!ModelQuickActions.TryResolveApprovedOllamaPull("qwen3", [fixture], true, true, out var selected)
    || selected?.ExactTag != "qwen3:0.6b")
    throw new Exception("HOST_VERIFIED_SELECT_FAILED");
if (ModelQuickActions.TryResolveApprovedOllamaPull("qwen3", [fixture,fixture], true, true, out _))
    throw new Exception("AMBIGUOUS_PIN_APPROVED");
if (ModelQuickActions.TryResolveApprovedOllamaPull("qwen3", [fixture], true, false, out _))
    throw new Exception("HOST_CAPABILITY_REQUIRED");
// G1-03 regression: 20 visible model families stay identical to P03 WOW.
if (!ModelQuickActions.OllamaSlots.Any(x=>x.Id=="gemma2") ||
    ModelQuickActions.OllamaSlots.Any(x=>x.Id=="nomic-embed-text"))
    throw new Exception("P03_QUICK20_UI_CSHARP_SLOT_DRIFT");
if (!ModelTagReviewLeads.VerifyReviewBoundary() ||
    ModelTagReviewLeads.ExactTags.Any(x=>x.DownloadEligible))
    throw new Exception("P03_EXACT_TAG_25_REVIEW_BOUNDARY_FAILED");
if (!ModelQuickActions.TryResolveApprovedOllamaPullExactTag("qwen3:0.6b", [fixture], true, true, out var exact)
    || exact?.ExactTag != "qwen3:0.6b")
    throw new Exception("P03_EXACT_TAG_APPROVED_FIXTURE_FAILED");
if (ModelQuickActions.TryResolveApprovedOllamaPullExactTag("qwen3:0.6b", ModelCatalog.OfficialFamilies, true, true, out _))
    throw new Exception("P03_UNVERIFIED_TAG_MUST_HOLD");
if (ModelQuickActions.TryResolveApprovedOllamaPullExactTag("qwen3:0.6b", [fixture,fixture], true, true, out _))
    throw new Exception("P03_DUPLICATED_PIN_MUST_HOLD");
if (ModelQuickActions.TryResolveApprovedOllamaPullExactTag("qwen3:0.6b", [fixture], false, true, out _) ||
    ModelQuickActions.TryResolveApprovedOllamaPullExactTag("qwen3:0.6b", [fixture], true, false, out _))
    throw new Exception("P03_HOST_OR_LICENSE_CONSENT_REQUIRED");
Console.WriteLine("P03_EXACT_TAG_LEADS_25_HOLD_AND_GUARDED_SELECTION_PASS");

Console.WriteLine("P03_QUICK_20_SOURCE_AND_ADMISSION_SMOKE_PASS (synthetic fixture, no weights downloaded)");
