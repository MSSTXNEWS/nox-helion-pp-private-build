using System.Collections.Immutable;
using System.Text.RegularExpressions;

namespace Nox.P03;

public enum CatalogEvidenceStatus { FamilyListed, ArtifactVerified }

/// <summary>
/// A library family is a discovery record, not a downloadable artifact. Artifact fields stay null
/// until an exact official tag and its license/size/digest are independently reviewed.
/// </summary>
public sealed record ModelCatalogEntry(
    string Id,
    string Name,
    Uri OfficialLibraryPage,
    CatalogEvidenceStatus EvidenceStatus = CatalogEvidenceStatus.FamilyListed,
    string? ExactTag = null,
    string? Version = null,
    string? License = null,
    long? ArtifactBytes = null,
    long? RequiredDiskBytes = null,
    long? RecommendedRamBytes = null,
    long? RecommendedVramBytes = null,
    string? ExpectedSha256 = null,
    Uri? LicenseEvidenceUri = null,
    Uri? CompatibilityEvidenceUri = null,
    string? ImmutableRevision = null,
    bool CompatibilityReviewed = false,
    string? ExpectedManifestDigestSha256 = null)
{
    public bool CanOfferOneClickPull => EvidenceStatus == CatalogEvidenceStatus.ArtifactVerified
        && IsPinnedTag(ExactTag)
        && !string.IsNullOrWhiteSpace(Version)
        && !string.IsNullOrWhiteSpace(License)
        && ArtifactBytes is > 0
        && RequiredDiskBytes is > 0
        && RequiredDiskBytes >= ArtifactBytes
        && IsSha256(ExpectedSha256)
        && IsSha256(ExpectedManifestDigestSha256)
        && LicenseEvidenceUri is { Scheme: "https" }
        && CompatibilityEvidenceUri is { Scheme: "https" }
        && IsImmutableRevision(ImmutableRevision)
        && (RecommendedRamBytes is > 0 || RecommendedVramBytes is > 0)
        && (RecommendedRamBytes is null or > 0)
        && (RecommendedVramBytes is null or > 0)
        && CompatibilityReviewed;

    // Keep discoverable models disabled unless a concrete tag matches the
    // exact queue grammar; family names and ':latest' are not immutable pins.
    private static bool IsPinnedTag(string? tag) =>
        tag is { Length: > 0 and <= 160 }
        && !tag.Contains("..", StringComparison.Ordinal)
        && !tag.EndsWith(":latest", StringComparison.OrdinalIgnoreCase)
        && Regex.IsMatch(tag, @"^[a-zA-Z0-9][a-zA-Z0-9._-]*(/[a-zA-Z0-9][a-zA-Z0-9._-]*)?:[a-zA-Z0-9][a-zA-Z0-9._-]*$");

    // A direct native catalog entry must meet the same immutable revision
    // proof as the reviewed artifact registry; arbitrary "latest" is HOLD.
    private static bool IsImmutableRevision(string? value) =>
        IsSha256(value) ||
        (value is { Length: 71 } &&
         value.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase) &&
         IsSha256(value[7..]));

    private static bool IsSha256(string? value) => value is { Length: 64 }
        && value.All(Uri.IsHexDigit);
}

public static class ModelCatalog
{
    private const string Library = "https://ollama.com/library/";

    // Family listing from the official Ollama library. These intentionally remain discovery-only:
    // the library index is not evidence for a concrete tag's license, version, bytes, or hash.
    public static ImmutableArray<ModelCatalogEntry> OfficialFamilies { get; } =
    [
        Family("deepseek-r1", "DeepSeek R1"), Family("llama3.1", "Llama 3.1"),
        Family("llama3.2", "Llama 3.2"), Family("qwen2.5", "Qwen 2.5"),
        Family("qwen3", "Qwen 3"), Family("gemma3", "Gemma 3"),
        Family("gemma2", "Gemma 2"), Family("mistral", "Mistral"),
        Family("llama3", "Llama 3"), Family("qwen2.5-coder", "Qwen 2.5 Coder"),
        Family("phi3", "Phi 3"), Family("mxbai-embed-large", "Mixedbread Embed Large"),
        Family("llava", "LLaVA"), Family("gpt-oss", "GPT-OSS"),
        Family("qwen3-coder", "Qwen 3 Coder"), Family("qwen3-vl", "Qwen 3 VL"),
        Family("tinyllama", "TinyLlama"), Family("qwen2", "Qwen 2"),
        Family("mistral-nemo", "Mistral Nemo"), Family("yi-coder", "Yi Coder"),
        Family("nous-hermes2", "Nous Hermes 2"), Family("aya", "Aya 23"),
        Family("stable-code", "Stable Code"), Family("wizard-math", "Wizard Math"),
        Family("llama-guard3", "Llama Guard 3"), Family("internlm2", "InternLM 2"),
        Family("devstral", "Devstral"), Family("granite3.1-dense", "Granite 3.1 Dense"),
        Family("phi4", "Phi 4"), Family("muse-glimmer", "Muse Glimmer")
    ];

    // Catalog integrity is independent of actual source-page or license review.
    public static bool IsValidFamilyIndex() => OfficialFamilies.Length >= 24
        && OfficialFamilies.Select(x => x.Id).Distinct(StringComparer.OrdinalIgnoreCase).Count() == OfficialFamilies.Length
        && OfficialFamilies.All(x => x.EvidenceStatus == CatalogEvidenceStatus.FamilyListed
            && x.OfficialLibraryPage.IsAbsoluteUri && x.OfficialLibraryPage.Scheme == Uri.UriSchemeHttps);

    public static ModelCatalogEntry Get(string id) => OfficialFamilies.FirstOrDefault(x =>
        string.Equals(x.Id, id, StringComparison.OrdinalIgnoreCase))
        ?? throw new KeyNotFoundException($"Unknown model family '{id}'.");

    private static ModelCatalogEntry Family(string id, string name) =>
        new(id, name, new Uri(Library + id));
}
