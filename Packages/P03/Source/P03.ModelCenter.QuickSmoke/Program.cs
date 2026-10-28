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
Console.WriteLine("P03_QUICK_20_SOURCE_AND_ADMISSION_SMOKE_PASS (synthetic fixture, no weights downloaded)");
