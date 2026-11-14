using System.Collections.Immutable;

namespace Nox.P03;

/// <summary>
/// Exact variant tags observed in official Ollama tag indexes on 2026-10-28.
/// A tag is mutable: it is NOT an immutable model pin or a license receipt.
/// All 25 records are HOLD until a full manifest digest, artifact hash,
/// exact bytes, license and hardware evidence are independently accepted.
/// This list is discovery metadata: it NEVER downloads any model or starts a host.
/// </summary>
public sealed record ModelTagReviewLead(
    string FamilyId,
    string ExactTag,
    string Role,
    Uri OfficialTagIndex,
    string Status = "HOLD_ARTIFACT_EVIDENCE",
    string? ImmutableManifestSha256 = null,
    string? LicenseEvidenceUrl = null,
    long? ExactArtifactBytes = null,
    long? ReviewedVramBytes = null,
    string? ImmutableRevision = null)
{
    public bool DownloadEligible => false;
}

public static class ModelTagReviewLeads
{
    public static ImmutableArray<ModelTagReviewLead> ExactTags { get; } =
    [
        Lead("qwen3", "0.6b", "CHAT/REASON"),
        Lead("qwen3", "1.7b", "CHAT/REASON"),
        Lead("qwen3", "4b", "CHAT/REASON"),
        Lead("qwen3", "8b", "CHAT/REASON"),
        Lead("qwen3", "14b", "CHAT/REASON"),
        Lead("qwen3", "30b", "CHAT/REASON"),
        Lead("qwen3", "32b", "CHAT/REASON"),
        Lead("qwen2.5", "0.5b", "CHAT"),
        Lead("qwen2.5", "1.5b", "CHAT"),
        Lead("qwen2.5", "3b", "CHAT"),
        Lead("qwen2.5", "7b", "CHAT"),
        Lead("qwen2.5", "14b", "CHAT"),
        Lead("qwen2.5", "32b", "CHAT"),
        Lead("qwen2.5", "72b", "CHAT"),
        Lead("gemma3", "270m", "CHAT/VISION"),
        Lead("gemma3", "1b", "CHAT/VISION"),
        Lead("gemma3", "4b", "CHAT/VISION"),
        Lead("gemma3", "12b", "CHAT/VISION"),
        Lead("gemma3", "27b", "CHAT/VISION"),
        Lead("llama3.2", "1b", "CHAT"),
        Lead("llama3.2", "3b", "CHAT"),
        Lead("deepseek-r1", "1.5b", "REASON"),
        Lead("deepseek-r1", "7b", "REASON"),
        Lead("deepseek-r1", "8b", "REASON"),
        Lead("deepseek-r1", "14b", "REASON"),
    ];

    private static ModelTagReviewLead Lead(string family, string tag, string role) =>
        new(family, family + ":" + tag, role,
            new Uri("https://ollama.com/library/" + family + "/tags"));

    public static bool VerifyReviewBoundary() =>
        ExactTags.Length == 25 &&
        ExactTags.Select(x => x.ExactTag)
            .Distinct(StringComparer.OrdinalIgnoreCase).Count() == ExactTags.Length &&
        ExactTags.All(x =>
            ModelCatalog.OfficialFamilies.Any(f => f.Id == x.FamilyId) &&
            x.ExactTag.StartsWith(x.FamilyId + ":", StringComparison.Ordinal) &&
            !x.ExactTag.EndsWith(":latest", StringComparison.OrdinalIgnoreCase) &&
            x.OfficialTagIndex.Scheme == Uri.UriSchemeHttps &&
            x.OfficialTagIndex.Host == "ollama.com" &&
            x.OfficialTagIndex.AbsolutePath == "/library/" + x.FamilyId + "/tags" &&
            x.Status == "HOLD_ARTIFACT_EVIDENCE" &&
            !x.DownloadEligible &&
            x.ImmutableManifestSha256 is null && x.LicenseEvidenceUrl is null &&
            x.ExactArtifactBytes is null && x.ReviewedVramBytes is null &&
            x.ImmutableRevision is null);
}
