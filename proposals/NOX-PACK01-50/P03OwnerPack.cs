// NOX V16 PACK01 — typed owner #3 adapter over the REAL P03 ModelCenterFacade.
// Build this together with the pinned original P03 project, not as a second downloader.
// Only native Windows host may construct VerifiedP03Input after real user consent.
using Nox.P03;

namespace Nox.Pack01;

public sealed record VerifiedP03Input(
    string RouteId,
    string? ChoiceId = null,
    string? Query = null,
    string? ModelTag = null,
    Guid? JobId = null,
    string? SelectedGgufPath = null,
    string? ReviewedLicenseUrl = null,
    bool NativeLicenseConsent = false,
    bool NativeFilePickerConfirmed = false);

public sealed class P03OwnerPack
{
    private readonly ModelCenterFacade _center;
    private readonly ModelDownloadQueueStore _queue;
    private readonly WindowsComponentAdapter _components;

    public P03OwnerPack(ModelCenterFacade existingCenter,
        ModelDownloadQueueStore existingQueue, WindowsComponentAdapter existingComponents)
    {
        _center = existingCenter ?? throw new ArgumentNullException(nameof(existingCenter));
        _queue = existingQueue ?? throw new ArgumentNullException(nameof(existingQueue));
        _components = existingComponents ?? throw new ArgumentNullException(nameof(existingComponents));
    }

    // 9 actually implemented P03 owner methods; 10th (models.licenses)
    // remains HOLD because a tag/library page is NOT a verified license grant.
    public static readonly IReadOnlySet<string> Supported = new HashSet<string>(StringComparer.Ordinal)
    {
        "models.catalog", "models.installed", "models.pull", "models.gguf.import",
        "models.queue", "models.cancel", "models.retry", "models.digest", "models.preflight"
    };

    public async Task<object> ExecuteAsync(VerifiedP03Input intent, CancellationToken stop = default)
    {
        ArgumentNullException.ThrowIfNull(intent);
        if (!Supported.Contains(intent.RouteId))
            throw new NotSupportedException("Unbound or unverified model action");
        stop.ThrowIfCancellationRequested();
        switch (intent.RouteId)
        {
            case "models.catalog":
                return _center.SearchChoices(intent.Query);
            case "models.installed":
                return await _center.InstalledAsync(stop).ConfigureAwait(false);
            case "models.queue":
                return await _center.JobsAsync(stop).ConfigureAwait(false);
            case "models.cancel":
                return await _center.StopAsync(RequireJobId(intent), stop).ConfigureAwait(false);
            case "models.retry":
                return await _center.RetryAsync(RequireJobId(intent), stop).ConfigureAwait(false)
                    ?? throw new KeyNotFoundException("Model job not found");
            case "models.digest":
            {
                if (string.IsNullOrWhiteSpace(intent.ModelTag))
                    throw new ArgumentException("Native model selection required");
                var models = await _center.InstalledAsync(stop).ConfigureAwait(false);
                return models.FirstOrDefault(x => string.Equals(x.Tag, intent.ModelTag, StringComparison.Ordinal))
                    ?? throw new KeyNotFoundException("Model not installed");
            }
            case "models.preflight":
                return await _components.DetectAsync(stop).ConfigureAwait(false);
            case "models.pull":
            {
                RequireConsent(intent);
                if (string.IsNullOrWhiteSpace(intent.ChoiceId))
                    throw new ArgumentException("Choose one existing quick-install model");
                // Queue selection uses original P03 20-model list and confirmed license.
                var queued = await _center.QueueInstallAsync(intent.ChoiceId,
                    intent.ReviewedLicenseUrl!, intent.NativeLicenseConsent, stop).ConfigureAwait(false);
                // Reuse original durable queue worker rather than launching another client.
                await _center.RunNextAsync(stop).ConfigureAwait(false);
                return (await _center.JobsAsync(stop).ConfigureAwait(false))
                    .Single(x => x.Id == queued.Id); // Could remain queued: never fake Installed.
            }
            case "models.gguf.import":
            {
                RequireConsent(intent);
                if (!intent.NativeFilePickerConfirmed || string.IsNullOrWhiteSpace(intent.SelectedGgufPath))
                    throw new UnauthorizedAccessException("Select GGUF via native file picker");
                if (!string.Equals(Path.GetExtension(intent.SelectedGgufPath), ".gguf",
                    StringComparison.OrdinalIgnoreCase))
                    throw new ArgumentException("Only GGUF source files supported");
                if (string.IsNullOrWhiteSpace(intent.ModelTag))
                    throw new ArgumentException("Native GGUF model name required");
                var queued = await _queue.EnqueueAsync(ModelJobKind.GgufImport,
                    intent.ModelTag, intent.SelectedGgufPath,
                    intent.NativeLicenseConsent, intent.ReviewedLicenseUrl!, stop).ConfigureAwait(false);
                await _center.RunNextAsync(stop).ConfigureAwait(false);
                return (await _center.JobsAsync(stop).ConfigureAwait(false))
                    .Single(x => x.Id == queued.Id);
            }
            default:
                throw new NotSupportedException("Unknown P03 capability");
        }
    }

    private static Guid RequireJobId(VerifiedP03Input input)
    {
        if (input.JobId is not Guid value || value == Guid.Empty)
            throw new ArgumentException("Existing native job ID required");
        return value;
    }

    private static void RequireConsent(VerifiedP03Input input)
    {
        if (!input.NativeLicenseConsent || !Uri.TryCreate(input.ReviewedLicenseUrl,
            UriKind.Absolute, out var url) || url.Scheme != Uri.UriSchemeHttps)
            throw new UnauthorizedAccessException("Reviewed license HTTPS URL and native consent required");
        // Host MUST independently validate that approval and the origin of the file-picker handle.
    }
}
