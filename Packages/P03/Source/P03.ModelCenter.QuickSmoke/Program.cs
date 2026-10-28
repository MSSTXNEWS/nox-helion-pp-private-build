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


/* E03 Quick20: bridge parser must follow the SAME persisted queue state transitions. */
var permissions = new Nox.P03.Wow.ModelWowBridgeContract.Capabilities(Stop:true,Retry:true,Pull:true);
var queued = new ModelJob(Guid.NewGuid(), ModelJobKind.OllamaPull, "qwen3:0.6b", null,
    true, "https://ollama.com/library/qwen3", DateTimeOffset.UtcNow, DateTimeOffset.UtcNow);
string stopQueued = System.Text.Json.JsonSerializer.Serialize(new {
    type="p03.command.v1", commandId="stop-queued-1", action="stop", jobId=queued.Id.ToString("D") });
if (!Nox.P03.Wow.ModelWowBridgeContract.TryParseCommand(stopQueued, [queued], [fixture], permissions, out var parsedStop) ||
    parsedStop?.Action != "stop") throw new Exception("P03_QUEUED_STOP_BRIDGE_MISSING");
if (!Nox.P03.Wow.ModelWowBridgeContract.TryParseCommand(stopQueued, [queued with { State = ModelJobState.Running }],
        [fixture], permissions, out _)) throw new Exception("P03_RUNNING_STOP_BRIDGE_MISSING");
if (Nox.P03.Wow.ModelWowBridgeContract.TryParseCommand(stopQueued, [queued with { State = ModelJobState.Completed }],
        [fixture], permissions, out _)) throw new Exception("P03_COMPLETED_STOP_MUST_DENY");
string retryFailed = System.Text.Json.JsonSerializer.Serialize(new {
    type="p03.command.v1", commandId="retry-failed-1", action="retry", jobId=queued.Id.ToString("D") });
if (!Nox.P03.Wow.ModelWowBridgeContract.TryParseCommand(retryFailed, [queued with { State = ModelJobState.Failed }],
        [fixture], permissions, out _)) throw new Exception("P03_FAILED_RETRY_BRIDGE_MISSING");
if (Nox.P03.Wow.ModelWowBridgeContract.TryParseCommand(retryFailed, [queued], [fixture], permissions, out _))
    throw new Exception("P03_QUEUED_RETRY_MUST_DENY");
string pullVerified = System.Text.Json.JsonSerializer.Serialize(new {
    type="p03.command.v1", commandId="pull-verified-1", action="pull", modelId="qwen3", licenseAcknowledged=true });
if (!Nox.P03.Wow.ModelWowBridgeContract.TryParseCommand(pullVerified, [queued], [fixture], permissions, out _))
    throw new Exception("P03_VERIFIED_PULL_BRIDGE_MISSING");
if (Nox.P03.Wow.ModelWowBridgeContract.TryParseCommand(pullVerified, [queued], [fixture,fixture], permissions, out _))
    throw new Exception("P03_DUPLICATE_APPROVED_ID_MUST_DENY");
if (Nox.P03.Wow.ModelWowBridgeContract.TryParseCommand(pullVerified, [queued], ModelCatalog.OfficialFamilies, permissions, out _))
    throw new Exception("P03_FAMILY_ONLY_BRIDGE_MUST_DENY");
Console.WriteLine("P03_BRIDGE_CANCEL_RETRY_DEDUP_7_TESTS_PASS");

Console.WriteLine("P03_QUICK_20_SOURCE_AND_ADMISSION_SMOKE_PASS (synthetic fixture, no weights downloaded)");
