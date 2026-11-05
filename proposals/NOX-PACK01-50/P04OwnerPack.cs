// NOX PACK01 -> original #4 RAG/GpuGuardian methods. No second RAG index or trainer.
// Requires an authorized native Windows SID + conversation selected by original host.
using NoxP04.Rag;
using NoxP04.GpuGuardian;

namespace Nox.Pack01;

public sealed class P04OwnerPack
{
    readonly RagIngestionService _ingestion;
    readonly GpuGuardian _guardian;
    readonly Func<string,bool> _freshNativeConsent;
    readonly IGpuWorkerControl? _worker;
    readonly Func<bool>? _isOriginalWorkerRunning;

    public static readonly IReadOnlySet<string> Supported = new HashSet<string>(StringComparer.Ordinal)
    {
        "rag.import","rag.search","memory.manage","gpu.preflight",
        "training.pause","training.resume"
    };

    // Existing registered owner RAG and GPU worker only. Callbacks originate in trusted
    // Windows host; no permission or worker state is trusted from JavaScript payload.
    public P04OwnerPack(RagIngestionService existingRag, GpuGuardian existingGuardian,
        Func<string,bool> freshNativeConsent,
        IGpuWorkerControl? existingTrainingWorker = null,
        Func<bool>? isOriginalWorkerRunning = null)
    {
        _ingestion = existingRag ?? throw new ArgumentNullException(nameof(existingRag));
        _guardian = existingGuardian ?? throw new ArgumentNullException(nameof(existingGuardian));
        _freshNativeConsent = freshNativeConsent ?? throw new ArgumentNullException(nameof(freshNativeConsent));
        _worker = existingTrainingWorker;
        _isOriginalWorkerRunning = isOriginalWorkerRunning;
    }

    public async Task<object> ExecuteAsync(string route, string ownerSid,
        string conversationId, string? input = null, string? sourceId = null,
        string? fileName = null, int topK = 5, CancellationToken cancel = default)
    {
        if (!Supported.Contains(route))throw new NotSupportedException("Unknown P04 handler");
        if (string.IsNullOrWhiteSpace(ownerSid) || string.IsNullOrWhiteSpace(conversationId))
            throw new UnauthorizedAccessException("Native user/conversation scope required");
        cancel.ThrowIfCancellationRequested();
        switch (route)
        {
            case "rag.import":
                RequireFreshNativeConsent(route);
                if (string.IsNullOrWhiteSpace(sourceId) || string.IsNullOrWhiteSpace(fileName) ||
                    string.IsNullOrWhiteSpace(input))throw new ArgumentException("Native-staged source required");
                // Original RAG computes input SHA, preserves source and host ACL.
                return await _ingestion.IngestTextAsync(ownerSid,conversationId,
                    sourceId,fileName,input,cancel).ConfigureAwait(false);

            case "rag.search":
                if (string.IsNullOrWhiteSpace(input) || topK is <1 or >20)
                    throw new ArgumentException("Valid scoped query and topK required");
                return await _ingestion.BuildContextAsync(ownerSid,conversationId,input,topK,cancel)
                    .ConfigureAwait(false);

            case "memory.manage":
                RequireFreshNativeConsent(route);
                if (string.IsNullOrWhiteSpace(sourceId))
                    throw new ArgumentException("Delete only one exact source ID; no bulk delete");
                return await _ingestion.DeleteSourceAsync(ownerSid,conversationId,sourceId,cancel)
                    .ConfigureAwait(false);

            case "gpu.preflight":
                // Truthful vendor nvidia-smi sample. If absent: N/D, not a fake ready GPU.
                return await _guardian.ReadNvidiaAsync("NIP01-25",cancel).ConfigureAwait(false);

            case "training.pause":
            case "training.resume":
                RequireFreshNativeConsent(route);
                if (_worker is null || _isOriginalWorkerRunning?.Invoke() != true)
                    throw new InvalidOperationException("Real training worker not active");
                var acknowledged = route=="training.pause"
                    ? await _worker.PauseAsync(cancel).ConfigureAwait(false)
                    : await _worker.ResumeAsync(cancel).ConfigureAwait(false);
                if (!acknowledged)
                    throw new InvalidOperationException("Training worker did not acknowledge");
                return new { Route=route, WorkerAcknowledged=true };

            default:throw new NotSupportedException("Unavailable P04 method");
        }
    }

    private void RequireFreshNativeConsent(string route)
    {
        // Approval MUST run in native trusted host for this invocation, not from page JSON.
        if (_freshNativeConsent(route) != true)
            throw new UnauthorizedAccessException("Fresh native consent required");
    }
}
