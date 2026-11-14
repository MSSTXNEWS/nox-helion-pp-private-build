// NOX PACK01: typed owner #3 C40+TURBO10 adapter over the ORIGINAL queue and worker.
// No second downloader, no unsigned/unpinned weights and no direct browser permissions.
using Nox.P03;
using System.Net;
using System.Text.Json;

namespace Nox.Pack01;

public sealed record VerifiedP03Input(
    string RouteId,
    string? Query = null,
    string? ModelTag = null,
    Guid? JobId = null,
    string? SelectedGgufPath = null,
    string? ReviewedLicenseUrl = null,
    bool NativeLicenseConsent = false,
    bool NativeFilePickerConfirmed = false,
    ModelCatalogEntry? ApprovedArtifact = null,
    long? ExpectedLocalBytes = null,
    string? ExpectedLocalSha256 = null,
    string? RightsReceiptId = null);

public sealed record ActualLocalModel(string Tag, string? Digest, long? Bytes);

public sealed class P03OwnerPack
{
    private readonly ModelDownloadQueueStore _queue;
    private readonly ModelDownloadQueueWorker _worker;
    private readonly WindowsComponentAdapter _components;
    private readonly HttpClient _ollama;

    public P03OwnerPack(ModelDownloadQueueStore existingQueue,ModelDownloadQueueWorker existingWorker,
        WindowsComponentAdapter existingComponents,HttpClient existingLoopbackOllama)
    {
        _queue = existingQueue ?? throw new ArgumentNullException(nameof(existingQueue));
        _worker = existingWorker ?? throw new ArgumentNullException(nameof(existingWorker));
        _components = existingComponents ?? throw new ArgumentNullException(nameof(existingComponents));
        _ollama = existingLoopbackOllama ?? throw new ArgumentNullException(nameof(existingLoopbackOllama));
        EnsureLocal(_ollama.BaseAddress);
    }

    public static readonly IReadOnlySet<string> Supported = new HashSet<string>(StringComparer.Ordinal)
    {
        "models.catalog", "models.installed", "models.pull", "models.gguf.import",
        "models.queue", "models.cancel", "models.retry", "models.digest", "models.preflight", "models.licenses"
    };

    public async Task<object> ExecuteAsync(VerifiedP03Input intent,CancellationToken stop = default)
    {
        ArgumentNullException.ThrowIfNull(intent);
        if (!Supported.Contains(intent.RouteId))
            throw new NotSupportedException("Unverified model route HOLD");
        stop.ThrowIfCancellationRequested();
        switch (intent.RouteId)
        {
            case "models.catalog":
                return ModelCatalog.OfficialFamilies.Where(x=>string.IsNullOrWhiteSpace(intent.Query) ||
                    (x.Name+" "+x.Id).Contains(intent.Query,StringComparison.OrdinalIgnoreCase)).ToArray();
            case "models.licenses":
                // Reflect only original owner model-card evidence, never invent a grant.
                return ModelCatalog.OfficialFamilies.Select(x=>new {
                    FamilyId=x.Id, x.Name, x.ExactTag, x.License,
                    LicenseEvidence=x.LicenseEvidenceUri?.AbsoluteUri,
                    x.ImmutableRevision,
                    Status=x.CanOfferOneClickPull ? "ARTIFACT_VERIFIED" : "REVIEW_REQUIRED",
                    CanDownload=x.CanOfferOneClickPull
                }).ToArray();
            case "models.installed":
                return await InstalledAsync(stop).ConfigureAwait(false);
            case "models.queue":
                return await _queue.ReadAsync(stop).ConfigureAwait(false);
            case "models.cancel":
                return await _worker.CancelAsync(RequireJobId(intent),stop).ConfigureAwait(false);
            case "models.retry":
                return await _worker.RetryAsync(RequireJobId(intent),stop).ConfigureAwait(false)
                    ?? throw new KeyNotFoundException("Model job not found");
            case "models.digest":
            {
                if (string.IsNullOrWhiteSpace(intent.ModelTag))
                    throw new ArgumentException("Native installed model selection required");
                var actual = await InstalledAsync(stop).ConfigureAwait(false);
                return actual.FirstOrDefault(x=>string.Equals(x.Tag,intent.ModelTag,StringComparison.Ordinal))
                    ?? throw new KeyNotFoundException("Model not installed");
            }
            case "models.preflight":
                return await _components.DetectAsync(stop).ConfigureAwait(false);
            case "models.pull":
            {
                RequireConsent(intent);
                if (intent.ApprovedArtifact is null || !intent.ApprovedArtifact.CanOfferOneClickPull)
                    throw new InvalidDataException("Exact approved model/artifact identity, rights and SHA required");
                var job=await _queue.EnqueueVerifiedPullAsync(intent.ApprovedArtifact,
                    intent.NativeLicenseConsent,stop).ConfigureAwait(false);
                await _worker.RunNextAsync(stop).ConfigureAwait(false);
                return (await _queue.ReadAsync(stop).ConfigureAwait(false)).Single(x=>x.Id==job.Id);
                // Queued/Failed statuses remain truthful; never claim installed automatically.
            }
            case "models.gguf.import":
            {
                RequireConsent(intent);
                if (!intent.NativeFilePickerConfirmed || string.IsNullOrWhiteSpace(intent.SelectedGgufPath))
                    throw new UnauthorizedAccessException("Native GGUF file picker required");
                if (!string.Equals(Path.GetExtension(intent.SelectedGgufPath),".gguf",
                    StringComparison.OrdinalIgnoreCase))
                    throw new ArgumentException("GGUF required");
                if (string.IsNullOrWhiteSpace(intent.ModelTag) || intent.ExpectedLocalBytes is not >4 ||
                    string.IsNullOrWhiteSpace(intent.ExpectedLocalSha256) ||
                    string.IsNullOrWhiteSpace(intent.RightsReceiptId))
                    throw new InvalidDataException("Pinned local GGUF bytes/SHA/rights receipt required");
                var job=await _queue.EnqueueVerifiedGgufAsync(intent.ModelTag,intent.SelectedGgufPath,
                    intent.ExpectedLocalBytes.Value,intent.ExpectedLocalSha256,
                    intent.RightsReceiptId,intent.ReviewedLicenseUrl!,stop).ConfigureAwait(false);
                await _worker.RunNextAsync(stop).ConfigureAwait(false);
                return (await _queue.ReadAsync(stop).ConfigureAwait(false)).Single(x=>x.Id==job.Id);
            }
            default:
                throw new NotSupportedException("Unbound P03 route");
        }
    }

    private async Task<IReadOnlyList<ActualLocalModel>> InstalledAsync(CancellationToken stop)
    {
        EnsureLocal(_ollama.BaseAddress);
        using var response=await _ollama.GetAsync("api/tags",stop).ConfigureAwait(false);
        response.EnsureSuccessStatusCode();
        using var doc=await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(stop),
            cancellationToken:stop).ConfigureAwait(false);
        if (!doc.RootElement.TryGetProperty("models",out var models) ||
            models.ValueKind != JsonValueKind.Array)
            throw new InvalidDataException("Invalid local Ollama response");
        var result=new List<ActualLocalModel>();
        foreach (var m in models.EnumerateArray())
        {
            if (!m.TryGetProperty("name",out var n) || n.ValueKind!=JsonValueKind.String)continue;
            var name=n.GetString();
            if (string.IsNullOrEmpty(name))continue;
            string? digest=m.TryGetProperty("digest",out var d) && d.ValueKind==JsonValueKind.String?d.GetString():null;
            long? size=m.TryGetProperty("size",out var s) && s.TryGetInt64(out var value)?value:null;
            result.Add(new(name,digest,size));
        }
        return result;
    }

    private static Guid RequireJobId(VerifiedP03Input input)
    {
        if (input.JobId is not Guid id || id==Guid.Empty)
            throw new ArgumentException("Native existing job ID required");
        return id;
    }

    private static void RequireConsent(VerifiedP03Input input)
    {
        if (!input.NativeLicenseConsent || !Uri.TryCreate(input.ReviewedLicenseUrl,
            UriKind.Absolute,out var url) || url.Scheme!=Uri.UriSchemeHttps)
            throw new UnauthorizedAccessException("Native license review/consent required");
        // E06 host independently enforces ACL, approved registry and picker provenance.
    }

    private static void EnsureLocal(Uri? origin)
    {
        if (origin is null || origin.Scheme!=Uri.UriSchemeHttp ||
            origin.AbsolutePath!="/" || !string.IsNullOrEmpty(origin.UserInfo) ||
            !string.IsNullOrEmpty(origin.Query) || !string.IsNullOrEmpty(origin.Fragment) ||
            !(origin.Host.Equals("localhost",StringComparison.OrdinalIgnoreCase) ||
              (IPAddress.TryParse(origin.Host,out var ip) && IPAddress.IsLoopback(ip))))
            throw new InvalidOperationException("Only existing loopback Ollama permitted");
    }
}
