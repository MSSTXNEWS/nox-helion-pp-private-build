namespace Nox.P03;

public sealed class ModelDownloadQueueWorker(
    ModelDownloadQueueStore store,
    OllamaModelAdapter ollama,
    ModelLifecyclePublisher events)
{
    private readonly Dictionary<Guid, CancellationTokenSource> _running = [];
    private readonly SemaphoreSlim _singleWorker = new(1, 1);

    public async Task RunNextAsync(CancellationToken ct = default)
    {
        await _singleWorker.WaitAsync(ct);
        try
        {
            var job = (await store.ReadAsync(ct)).FirstOrDefault(x => x.State == ModelJobState.Queued);
            if (job is null) return;
            // Legacy unpinned jobs remain preserved in the queue, but cannot execute.
            if (job.Kind == ModelJobKind.OllamaPull &&
                (job.ExpectedOllamaDigest is not { Length: 64 } || string.IsNullOrWhiteSpace(job.ImmutableRevision)))
            {
                await store.UpdateAsync(job.Id, j => j with { State = ModelJobState.Failed,
                    Status = "REVIEW_REQUIRED", Error = "UNPINNED_ARTIFACT" }, ct);
                return;
            }
            using var linked = CancellationTokenSource.CreateLinkedTokenSource(ct);
            lock (_running) _running[job.Id] = linked;
            // CancelQueuedAsync may win between snapshot and this transition.
            // A cancelled job must never be resurrected as Running.
            var started = await store.TryStartQueuedAsync(job.Id, ct);
            if (started is null)
            {
                lock (_running) _running.Remove(job.Id);
                return;
            }
            await SafePublishAsync(job, "started", "Starting", null, null, null, null, ct);
            try
            {
                var current = started;
                async ValueTask OnProgress(OllamaStreamUpdate u, CancellationToken token)
                {
                    await store.UpdateAsync(job.Id, j => j.State == ModelJobState.Running
                        ? j with { Status = u.Status, CompletedBytes = u.Completed, TotalBytes = u.Total }
                        : j, token);
                    await SafePublishAsync(job, "progress", u.Status, u.Completed, u.Total, u.Digest, null, token);
                }
                string? digest;
                if (current.Kind == ModelJobKind.OllamaPull)
                    digest = await ollama.PullAsync(current, OnProgress, linked.Token);
                else
                {
                    var imported = await ollama.ImportGgufAsync(current, OnProgress, linked.Token);
                    digest = "sha256:" + imported.Sha256;
                    await store.UpdateAsync(job.Id, j => j with { ComputedSha256 = imported.Sha256 }, ct);
                }
                var done = await store.UpdateAsync(job.Id, j => j.State == ModelJobState.Running
                    ? j with { State = ModelJobState.Completed, Status = "Installed",
                        ReceiptPath = ollama.ReceiptPathFor(j.Id) } : j, CancellationToken.None);
                if (done?.State != ModelJobState.Completed)
                    throw new OperationCanceledException("Cancellation won the terminal-state race.", linked.Token);
                await SafePublishAsync(job, "completed", "Installed", done.CompletedBytes, done.TotalBytes, digest, null, CancellationToken.None);
            }
            catch (OperationCanceledException) when (linked.IsCancellationRequested)
            {
                var cancelled = await store.UpdateAsync(job.Id, j =>
                    j.State is ModelJobState.Running or ModelJobState.Cancelling
                        ? j with { State = ModelJobState.Cancelled, Status = "Cancelled; Ollama may resume this pull later" }
                        : j, CancellationToken.None);
                if (cancelled?.State == ModelJobState.Cancelled)
                    await SafePublishAsync(job, "cancelled", "Cancelled", null, null, null, null, CancellationToken.None);
            }
            catch (Exception ex)
            {
                var failed = await store.UpdateAsync(job.Id, j =>
                    j.State is ModelJobState.Running or ModelJobState.Cancelling
                        ? j with { State = ModelJobState.Failed, Status = "Failed", Error = ex.Message }
                        : j, CancellationToken.None);
                if (failed?.State == ModelJobState.Failed)
                    await SafePublishAsync(job, "failed", "Failed", null, null, null, ex.Message, CancellationToken.None);
            }
            finally { lock (_running) _running.Remove(job.Id); }
        }
        finally { _singleWorker.Release(); }
    }

    public async Task<bool> CancelAsync(Guid id, CancellationToken ct = default)
    {
        CancellationTokenSource? running;
        lock (_running) _running.TryGetValue(id, out running);
        if (running is not null)
        {
            // Persist the intent BEFORE signalling cancellation. A completed terminal
            // cancellation must not be overwritten by a delayed Cancelling write.
            var record = await store.UpdateAsync(id, j => j.State == ModelJobState.Running
                ? j with { State = ModelJobState.Cancelling, Status = "Cancelling" } : j, ct);
            if (record?.State == ModelJobState.Cancelling)
            {
                running.Cancel();
                return true;
            }
            // STOP can arrive after token registration but before the atomic
            // Queued->Running claim. Persist the cancellation at that boundary.
            if (record?.State == ModelJobState.Queued)
                return await store.CancelQueuedAsync(id, ct);
            return false;
        }
        return await store.CancelQueuedAsync(id, ct);
    }

    public Task<ModelJob?> RetryAsync(Guid id, CancellationToken ct = default) => store.RetryAsync(id, ct);

    // A UI/event sink outage must not convert a successfully persisted model
    // installation into Failed or erase the installed receipt.
    private async ValueTask SafePublishAsync(ModelJob job, string phase, string status,
        long? completed, long? total, string? digest, string? error, CancellationToken ct)
    {
        try
        {
            await events.PublishAsync(new ModelLifecycleEvent(
                Guid.NewGuid(), job.Id, job.ModelTag, phase, status, completed, total,
                digest, error, DateTimeOffset.UtcNow), ct);
        }
        catch (Exception ex) when (ex is not OutOfMemoryException)
        {
            System.Diagnostics.Trace.TraceError(
                "P03_EVENT_DELIVERY_FAILED job={0} phase={1} kind={2}", job.Id, phase,
                ex.GetType().Name);
        }
    }
}