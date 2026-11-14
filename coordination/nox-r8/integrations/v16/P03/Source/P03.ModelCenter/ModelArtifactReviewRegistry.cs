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
    private static readonly Regex TagPattern = new(@"^[a-zA-Z0-9][a-zA-Z0-9._-]*(/[a-zA-Z0-9][a-zA-Z0-9._-]*)?:[a-zA-Z0-9][a-zA-Z0-9._-]*$", RegexOptions.Compiled);
    private static bool Sha(string? x) => x is { Length: 64 } && x.All(Uri.IsHexDigit);
    // Evidence links are not a native rights receipt. Do not promote loopback,
    // local-only or nonstandard-origin URLs into the approved model catalog.
    // Match the existing HasReviewedGgufAuthority external-evidence boundary.
    private static bool Https(string? x, out Uri? uri) =>
        Uri.TryCreate(x, UriKind.Absolute, out uri) && uri.Scheme == Uri.UriSchemeHttps &&
        uri.IsDefaultPort && !uri.IsLoopback && !string.IsNullOrWhiteSpace(uri.Host) &&
        !uri.Host.Equals("localhost", StringComparison.OrdinalIgnoreCase) &&
        !uri.Host.EndsWith(".localhost", StringComparison.OrdinalIgnoreCase) &&
        !uri.Host.EndsWith(".local", StringComparison.OrdinalIgnoreCase) &&
        !uri.Host.EndsWith(".internal", StringComparison.OrdinalIgnoreCase) &&
        string.IsNullOrEmpty(uri.UserInfo) && string.IsNullOrEmpty(uri.Fragment);
    private static bool Official(string source, string family) => Https(source, out var uri) &&
        uri!.Host.Equals("ollama.com", StringComparison.OrdinalIgnoreCase) &&
        uri.IsDefaultPort &&
        uri.AbsolutePath.Equals("/library/" + family, StringComparison.OrdinalIgnoreCase) &&
        string.IsNullOrWhiteSpace(uri.Query);
    public static IReadOnlyList<ModelArtifactReviewCandidate> ReadTemplate(string path)
    {
        // A review lead is still external input: read a bounded, owner-owned
        // handle, never File.ReadAllText on an unbounded/reparse/hardlink path.
        ModelLocalAttestation.RequireRegularUnlinkedFile(path);
        using var input = new FileStream(path, FileMode.Open, FileAccess.Read,
            FileShare.Read, 8192, FileOptions.SequentialScan);
        ModelLocalAttestation.RequireSingleLinkFileHandle(input.SafeFileHandle);
        if (input.Length < 2 || input.Length > 2 * 1024 * 1024)
            throw new InvalidDataException("P03_REVIEW_TEMPLATE_SIZE_HOLD");
        using var doc = JsonDocument.Parse(input);
        if (doc.RootElement.ValueKind != JsonValueKind.Object ||
            !doc.RootElement.TryGetProperty("items", out var items) || items.ValueKind != JsonValueKind.Array ||
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
    /// <summary>Load the owner-reviewed, SourceLock-pinned artifact registry.
    /// expectedSha256 MUST come from authenticated native/build policy; never
    /// compute it from the supplied file or accept it from JavaScript.</summary>
    public static IReadOnlyCollection<ModelCatalogEntry> LoadReviewedArtifacts(
        string path, string expectedSha256)
    {
        if (!Sha(expectedSha256) || expectedSha256.All(c=>c=='0'))
            throw new InvalidDataException("P03_NATIVE_REGISTRY_PIN_REQUIRED");
        ModelLocalAttestation.RequireRegularUnlinkedFile(path);
        using var input=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read);
        // Preflight cannot attest a later open: reject a swapped NTFS hardlink
        // on the actual registry handle before hashing or parsing any bytes.
        ModelLocalAttestation.RequireSingleLinkFileHandle(input.SafeFileHandle);
        if (input.Length<2 || input.Length>2*1024*1024)
            throw new InvalidDataException("P03_REGISTRY_SIZE_INVALID");
        using var memory=new MemoryStream(); input.CopyTo(memory);
        var bytes=memory.ToArray();
        var actual=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(bytes));
        if (!actual.Equals(expectedSha256,StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("P03_REGISTRY_SOURCELOCK_MISMATCH");
        using var doc=JsonDocument.Parse(bytes);
        var root=doc.RootElement;
        if (root.ValueKind!=JsonValueKind.Object ||
            root.EnumerateObject().Count()!=2 ||
            !root.TryGetProperty("schema",out var schema) ||
            schema.GetString()!="NOX-P03-REVIEWED-ARTIFACTS-V1" ||
            !root.TryGetProperty("items",out var items) ||
            items.ValueKind!=JsonValueKind.Array || items.GetArrayLength()>250)
            throw new InvalidDataException("P03_REGISTRY_SCHEMA_INVALID");
        var result=new List<ModelCatalogEntry>();
        // The native queue and Ollama tag admission treat case variants as one identity.
        // A SourceLock-pinned registry must not authorize conflicting case aliases.
        var tags=new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var options=new JsonSerializerOptions(JsonSerializerDefaults.Web) {
            UnmappedMemberHandling=System.Text.Json.Serialization.JsonUnmappedMemberHandling.Disallow };
        foreach (var item in items.EnumerateArray())
        {
            if (item.ValueKind!=JsonValueKind.Object ||
                item.EnumerateObject().Select(x=>x.Name).Distinct(StringComparer.OrdinalIgnoreCase).Count()
                    !=item.EnumerateObject().Count())
                throw new InvalidDataException("P03_REGISTRY_AMBIGUOUS_ENTRY");
            var candidate=item.Deserialize<ModelArtifactReviewCandidate>(options);
            // The exact registry bytes were admitted by the native SourceLock.
            if (!TryPromote(candidate,true,out var model) || model is null ||
                !tags.Add(model.ExactTag!))
                throw new InvalidDataException("P03_REGISTRY_UNREVIEWED_ARTIFACT");
            result.Add(model);
        }
        return result.AsReadOnly();
    }

    public static bool TryPromote(ModelArtifactReviewCandidate? c, bool ownerReceiptVerified, out ModelCatalogEntry? result)
    {
        result=null;
        if (c is null || !ownerReceiptVerified || c.ReviewStatus!="OWNER_VERIFIED" ||
            string.IsNullOrWhiteSpace(c.ReviewerReceiptId) || c.ReviewerReceiptId.Length>128 || c.ReviewerReceiptId.Any(char.IsControl) ||
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
        result=ModelCatalog.Get(c.FamilyId) with {
            EvidenceStatus=CatalogEvidenceStatus.ArtifactVerified,
            ExactTag=c.ExactTag, Version=c.Version, License=c.LicenseId,
            ArtifactBytes=c.ArtifactBytes, RequiredDiskBytes=c.RequiredDiskBytes,
            RecommendedRamBytes=c.RecommendedRamBytes, RecommendedVramBytes=c.RecommendedVramBytes,
            ExpectedSha256=c.ArtifactSha256, ExpectedManifestDigestSha256=c.ManifestSha256,
            LicenseEvidenceUri=license, CompatibilityEvidenceUri=compat,
            ImmutableRevision=c.ImmutableRevision, CompatibilityReviewed=true,
            ReviewedRightsReceiptId=c.ReviewerReceiptId
        };
        return result.CanOfferOneClickPull;
    }
}