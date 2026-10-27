#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;

namespace NoxHelion.P03.WorkerCatalog;

/// <summary>
/// A family card is discovery metadata only. It is not a pinned artifact and
/// must never be passed to a downloader until a complete provenance record exists.
/// </summary>
public sealed record ModelFamilyCandidate(
    string CatalogId,
    Uri OfficialLibraryUri,
    DateTimeOffset ObservedAtUtc);

/// <summary>
/// Evidence required to queue one exact model artifact. Unknown values remain
/// empty and cause validation to fail closed.
/// </summary>
public sealed record ModelArtifactEvidence(
    string CatalogId,
    string ArtifactReference,
    Uri? OfficialSourceUri,
    string? ArtifactRevision,
    string? LicenseId,
    Uri? LicenseEvidenceUri,
    long? ArtifactSizeBytes,
    string? ArtifactSha256,
    Uri? CompatibilityEvidenceUri,
    decimal? RequiredVramGiB,
    string? SourceCommit,
    string? SourceTree,
    string? SourceLockFingerprintSha256,
    string? OwnerReceiptId,
    string? OwnerReceiptPath,
    string? OwnerPreimageSha256,
    string? OwnerPostimageSha256,
    string? OwnerPatchSha256)
{
    public const string ExpectedOwnerPath = "Packages/P03/worker-catalog/ModelCatalog.cs";

    /// <summary>
    /// Returns the fifteen provenance gates. The final gate verifies that the
    /// owner receipt binds all three before/after/patch hashes.
    /// </summary>
    public IReadOnlyList<string> GetProvenanceFailures()
    {
        var failures = new List<string>(15);
        Check(!string.IsNullOrWhiteSpace(CatalogId), "catalog-id", failures);
        Check(!string.IsNullOrWhiteSpace(ArtifactReference), "artifact-reference", failures);
        Check(IsHttps(OfficialSourceUri) &&
              string.Equals(OfficialSourceUri!.Host, "ollama.com", StringComparison.OrdinalIgnoreCase),
            "official-source", failures);
        Check(!string.IsNullOrWhiteSpace(ArtifactRevision) &&
              !string.Equals(ArtifactRevision, "latest", StringComparison.OrdinalIgnoreCase),
            "immutable-artifact-revision", failures);
        Check(!string.IsNullOrWhiteSpace(LicenseId), "license-id", failures);
        Check(IsHttps(LicenseEvidenceUri), "license-evidence-url", failures);
        Check(ArtifactSizeBytes is > 0, "artifact-size", failures);
        Check(IsSha256(ArtifactSha256), "artifact-sha256", failures);
        Check(IsHttps(CompatibilityEvidenceUri), "compatibility-evidence-url", failures);
        Check(RequiredVramGiB is > 0, "required-vram", failures);
        Check(IsGitObjectId(SourceCommit), "source-commit", failures);
        Check(IsGitObjectId(SourceTree), "source-tree", failures);
        Check(IsSha256(SourceLockFingerprintSha256), "sourcelock-fingerprint", failures);
        Check(!string.IsNullOrWhiteSpace(OwnerReceiptId) &&
              string.Equals(NormalizePath(OwnerReceiptPath), ExpectedOwnerPath, StringComparison.Ordinal),
            "owner-receipt-identity-and-path", failures);
        Check(IsSha256(OwnerPreimageSha256) && IsSha256(OwnerPostimageSha256) && IsSha256(OwnerPatchSha256),
            "owner-receipt-pre-post-patch-hashes", failures);

        return failures;
    }

    public string ArtifactIdentity => string.Join("|", CatalogId, ArtifactRevision, ArtifactSha256);

    private static void Check(bool passed, string gate, ICollection<string> failures)
    {
        if (!passed)
            failures.Add(gate);
    }

    private static bool IsHttps(Uri? uri) =>
        uri is { IsAbsoluteUri: true } &&
        string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase);

    private static bool IsGitObjectId(string? value) =>
        Regex.IsMatch(value ?? string.Empty, "^[0-9a-fA-F]{40}$", RegexOptions.CultureInvariant);

    private static bool IsSha256(string? value) =>
        Regex.IsMatch(value ?? string.Empty, "^[0-9a-fA-F]{64}$", RegexOptions.CultureInvariant);

    private static string NormalizePath(string? value) =>
        (value ?? string.Empty).Replace('\\', '/').TrimStart('/');
}

/// <summary>
/// Fail-closed P03 discovery catalog. The family list is taken from the
/// official Ollama library page observed on 2026-10-27; family cards do not
/// assert tag, license, bytes, hardware compatibility, or download eligibility.
/// </summary>
public sealed class ModelCatalog
{
    public const string OfficialLibrarySnapshotUri = "https://ollama.com/library?sort=popular";
    public static readonly DateTimeOffset SnapshotObservedAtUtc =
        new(2026, 10, 27, 0, 0, 0, TimeSpan.Zero);

    private static readonly string[] FamilyIds = new[]
    {
        "llama3.1", "deepseek-r1", "nomic-embed-text", "llama3.2", "qwen2.5",
        "qwen3", "gemma3", "gemma2", "mistral", "gemma4", "llama3", "qwen3.5",
        "qwen2.5-coder", "phi3", "mxbai-embed-large", "llava", "gpt-oss", "qwen3-coder",
        "glm-ocr", "gemma", "qwen", "bge-m3", "phi4", "llama2", "codellama",
        "qwen3.6", "qwen3-vl", "tinyllama", "qwen2", "mistral-nemo"
    };

    private readonly IReadOnlyList<ModelFamilyCandidate> _families = Array.AsReadOnly(
        FamilyIds.Select(id => new ModelFamilyCandidate(
            id,
            new Uri($"https://ollama.com/library/{id}", UriKind.Absolute),
            SnapshotObservedAtUtc)).ToArray());

    public IReadOnlyList<ModelFamilyCandidate> FamilyCandidates => _families;

    public bool TryGetFamily(string catalogId, out ModelFamilyCandidate? candidate)
    {
        candidate = _families.FirstOrDefault(item =>
            string.Equals(item.CatalogId, catalogId, StringComparison.OrdinalIgnoreCase));
        return candidate is not null;
    }

    public static IReadOnlyList<string> ValidateForQueue(ModelArtifactEvidence evidence) =>
        evidence.GetProvenanceFailures();
}
