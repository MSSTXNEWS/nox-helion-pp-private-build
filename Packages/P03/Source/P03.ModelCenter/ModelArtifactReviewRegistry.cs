using System.Text.Json;
using System.Text.RegularExpressions;

namespace Nox.P03;

/// <summary>Unverified links never become downloadable artifacts. Host authenticates
/// the reviewer/rights receipt and SourceLock before permitting TryPromote.</summary>
public sealed record ModelArtifactReviewCandidate(
    string FamilyId, string OfficialSourceUrl, string? ExactTag,
    string? Version, string? LicenseId, string? LicenseEvidenceUrl,
    long? ArtifactBytes, long? RequiredDiskBytes, long? RecommendedRamBytes,
    long? RecommendedVramBytes, string? ArtifactSha256, string? ManifestSha256,
    string? CompatibilityEvidenceUrl, string? ImmutableRevision,
    bool CompatibilityReviewed, string? ReviewerReceiptId,
    string ReviewStatus = "REVIEW_REQUIRED");

public static class ModelArtifactReviewRegistry
{
    /// <summary>Owner-side snapshot for the existing native/Python boundary.
    /// Caller supplies authenticated owner receipt verification; page JSON must
    /// never set it. Export is metadata, not a queue permission or install receipt.
    /// </summary>
    public static bool TryExportReviewedArtifact(ModelArtifactReviewCandidate? candidate,
        bool ownerReceiptVerified, out string? json)
    {
        json = null;
        if (!TryPromote(candidate, ownerReceiptVerified, out var model) || model is null)
            return false;
        json = JsonSerializer.Serialize(new {
            schema = "NOX_P03_NATIVE_REVIEWED_ARTIFACT_V1",
            familyId = model.Id, exactTag = model.ExactTag, version = model.Version,
            licenseId = model.License, licenseEvidenceUrl = model.LicenseEvidenceUri!.AbsoluteUri,
            artifactBytes = model.ArtifactBytes, requiredDiskBytes = model.RequiredDiskBytes,
            recommendedRamBytes = model.RecommendedRamBytes,
            requiredVramBytes = model.RecommendedVramBytes,
            artifactSha256 = model.ExpectedSha256!.ToLowerInvariant(),
            manifestSha256 = model.ExpectedManifestDigestSha256!.ToLowerInvariant(),
            immutableRevision = model.ImmutableRevision,
            compatibilityEvidenceUrl = model.CompatibilityEvidenceUri!.AbsoluteUri,
            reviewerReceiptId = candidate!.ReviewerReceiptId
        });
        return true;
    }

    private static readonly Regex TagPattern = new(@"^[a-zA-Z0-9][a-zA-Z0-9._-]*(/[a-zA-Z0-9][a-zA-Z0-9._-]*)?:[a-zA-Z0-9][a-zA-Z0-9._-]*$", RegexOptions.Compiled);
    private static bool Sha(string? x) => x is { Length: 64 } && x.All(Uri.IsHexDigit) && x.Any(ch => ch != '0');
    private static bool Https(string? x, out Uri? uri) =>
        Uri.TryCreate(x, UriKind.Absolute, out uri) && uri.Scheme == Uri.UriSchemeHttps &&
        string.IsNullOrEmpty(uri.UserInfo) && string.IsNullOrEmpty(uri.Fragment);
    private static bool Official(string source, string family) => Https(source, out var uri) &&
        uri!.Host.Equals("ollama.com", StringComparison.OrdinalIgnoreCase) &&
        uri.AbsolutePath.Equals("/library/" + family, StringComparison.OrdinalIgnoreCase) &&
        string.IsNullOrWhiteSpace(uri.Query);
    public static IReadOnlyList<ModelArtifactReviewCandidate> ReadTemplate(string path)
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(path));
        if (!doc.RootElement.TryGetProperty("items", out var items) || items.ValueKind != JsonValueKind.Array ||
            items.GetArrayLength() < 15 || items.GetArrayLength() > 250)
            throw new InvalidDataException("REVIEW_TEMPLATE_INVALID");
        var result = new List<ModelArtifactReviewCandidate>();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach(var item in items.EnumerateArray())
        {
            var family = item.GetProperty("family").GetString() ?? "";
            var url = item.GetProperty("officialSourceUrl").GetString() ?? "";
            if (!seen.Add(family) || !ModelCatalog.OfficialFamilies.Any(x=> x.Id.Equals(family,StringComparison.OrdinalIgnoreCase)) || !Official(url,family))
                throw new InvalidDataException("REVIEW_TEMPLATE_UNTRUSTED_SOURCE");
            result.Add(new(family,url,null,null,null,null,null,null,null,null,null,null,null,null,false,null));
        }
        return result;
    }
    public static bool TryPromote(ModelArtifactReviewCandidate? c, bool ownerReceiptVerified, out ModelCatalogEntry? result)
    {
        result=null;
        if (c is null || !ownerReceiptVerified || c.ReviewStatus!="OWNER_VERIFIED" ||
            string.IsNullOrWhiteSpace(c.ReviewerReceiptId) || c.ReviewerReceiptId.Length>128 ||
            !ModelCatalog.OfficialFamilies.Any(x=>x.Id.Equals(c.FamilyId,StringComparison.OrdinalIgnoreCase)) ||
            !Official(c.OfficialSourceUrl,c.FamilyId) ||
            !Https(c.LicenseEvidenceUrl,out var license) || !Https(c.CompatibilityEvidenceUrl,out var compat) ||
            c.ExactTag is null || c.ExactTag.Length>160 || !TagPattern.IsMatch(c.ExactTag) ||
            !c.ExactTag.StartsWith(c.FamilyId+":",StringComparison.OrdinalIgnoreCase) ||
            c.ExactTag.EndsWith(":latest",StringComparison.OrdinalIgnoreCase) || c.ExactTag.Contains("..") ||
            string.IsNullOrWhiteSpace(c.Version) || string.IsNullOrWhiteSpace(c.LicenseId) ||
            c.ArtifactBytes is not >0 || c.RequiredDiskBytes < c.ArtifactBytes ||
            (c.RecommendedRamBytes is not >0 && c.RecommendedVramBytes is not >0) ||
            !Sha(c.ArtifactSha256) || !Sha(c.ManifestSha256) ||
            !c.CompatibilityReviewed || string.IsNullOrWhiteSpace(c.ImmutableRevision) ||
            !(Sha(c.ImmutableRevision) || c.ImmutableRevision.StartsWith("sha256:",StringComparison.OrdinalIgnoreCase) && Sha(c.ImmutableRevision[7..]))) return false;
        var promoted=ModelCatalog.Get(c.FamilyId) with {
            EvidenceStatus=CatalogEvidenceStatus.ArtifactVerified,
            ExactTag=c.ExactTag, Version=c.Version, License=c.LicenseId,
            ArtifactBytes=c.ArtifactBytes, RequiredDiskBytes=c.RequiredDiskBytes,
            RecommendedRamBytes=c.RecommendedRamBytes, RecommendedVramBytes=c.RecommendedVramBytes,
            ExpectedSha256=c.ArtifactSha256, ExpectedManifestDigestSha256=c.ManifestSha256,
            LicenseEvidenceUri=license, CompatibilityEvidenceUri=compat,
            ImmutableRevision=c.ImmutableRevision, CompatibilityReviewed=true
        };
        // A failed Try operation must never leak a partially promoted artifact.
        // Direct entries and reviewed candidates share the catalogue resource gate.
        if (!promoted.CanOfferOneClickPull) return false;
        result=promoted;
        return true;
    }
}
