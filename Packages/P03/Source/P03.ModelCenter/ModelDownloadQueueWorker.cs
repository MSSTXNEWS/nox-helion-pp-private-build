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
                // The queued snapshot can be cancelled by another NOX window before
                // this review gate is persisted. Never rewrite terminal Cancelled.
                await store.UpdateAsync(job.Id, j => j.State == ModelJobState.Queued
                    ? j with { State = ModelJobState.Failed,
                        Status = "REVIEW_REQUIRED", Error = "UNPINNED_ARTIFACT" }
                    : j, ct);
                return;
            }
            // Hold one OS-backed lease through the transfer so a second window
            // cannot misclassify this Running job as crashed during recovery.
            using var executionLease = store.TryAcquireExecutionLease(job.Id);
            if (executionLease is null) return;
            using var linked = CancellationTokenSource.CreateLinkedTokenSource(ct);
            lock (_running) _running[job.Id] = linked;
            // CancelQueuedAsync may win between snapshot and this transition.
            // A cancelled job must never be resurrected as Running.
            // A failed queue claim must not leave a disposed CTS registered:
            // otherwise a later CancelAsync can target a dead worker token.
            ModelJob? started;
            try { started = await store.TryStartQueuedAsync(job.Id, ct); }
            catch
            {
                lock (_running) _running.Remove(job.Id);
                throw;
            }
            if (started is null)
            {
                lock (_running) _running.Remove(job.Id);
                return;
            }
            using var monitorStop = new CancellationTokenSource();
            var monitorTask = WatchSharedCancelAsync(job.Id, linked, monitorStop.Token);
            await SafePublishAsync(job, "started", "Starting", null, null, null, null, ct);
            try
            {
                var current = started;
                async ValueTask OnProgress(OllamaStreamUpdate u, CancellationToken token)
                {
                    var persisted = await store.UpdateAsync(job.Id, j => j.State == ModelJobState.Running
                        ? j with { Status = u.Status, CompletedBytes = u.Completed, TotalBytes = u.Total }
                        : j, token);
                    // STOP may win the queue race while an HTTP progress callback
                    // is inflight. Do not publish a fake RUNNING event after STOP.
                    if (persisted?.State != ModelJobState.Running || linked.IsCancellationRequested)
                    {
                        linked.Cancel();
                        return;
                    }
                    await SafePublishAsync(job, "progress", u.Status, persisted.CompletedBytes, persisted.TotalBytes, u.Digest, null, token);
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
                // Ollama may finish while a native STOP is in flight; do not
                // convert an already-cancelled transfer into Installed.
                linked.Token.ThrowIfCancellationRequested();
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
            catch (Exception ex) when (linked.IsCancellationRequested)
            {
                // Native cancel can surface as an HTTP/IO exception rather than
                // OperationCanceledException. Preserve durable CANCELLED.
                var cancelled = await store.UpdateAsync(job.Id, j =>
                    j.State is ModelJobState.Running or ModelJobState.Cancelling
                        ? j with { State = ModelJobState.Cancelled,
                            Status = "Cancelled; Ollama may resume this pull later" }
                        : j, CancellationToken.None);
                if (cancelled?.State == ModelJobState.Cancelled)
                    await SafePublishAsync(job, "cancelled", "Cancelled", null, null,
                        null, null, CancellationToken.None);
                System.Diagnostics.Trace.TraceInformation(
                    "P03_CANCEL_NETWORK_TERMINATED job={0} error={1}", job.Id, ex.GetType().Name);
            }
            catch (Exception ex)
            {
                // Adapter exceptions may embed paths, URLs or credentials. Never
                // store their raw messages in durable queue JSON or UI events.
                const string publicError = "P03_TRANSFER_FAILED";
                System.Diagnostics.Trace.TraceError(
                    "P03_TRANSFER_FAILED job={0} kind={1}", job.Id, ex.GetType().Name);
                // A second NOX window may persist STOP before our local 250 ms
                // monitor cancels the token. Durable Cancelling beats local token
                // state: an already-requested STOP must never become Failed.
                var stoppedBeforeFailure = false;
                var outcome = await store.UpdateAsync(job.Id, j =>
                {
                    if (j.State == ModelJobState.Cancelling)
                    {
                        stoppedBeforeFailure = true;
                        return j with { State = ModelJobState.Cancelled,
                            Status = "Cancelled; Ollama may resume this pull later" };
                    }
                    return j.State == ModelJobState.Running
                        ? j with { State = ModelJobState.Failed,
                            Status = "Failed", Error = publicError }
                        : j;
                }, CancellationToken.None);
                if (stoppedBeforeFailure && outcome?.State == ModelJobState.Cancelled)
                    await SafePublishAsync(job, "cancelled", "Cancelled", null, null,
                        null, null, CancellationToken.None);
                else if (outcome?.State == ModelJobState.Failed)
                    await SafePublishAsync(job, "failed", "Failed", null, null,
                        null, publicError, CancellationToken.None);
            }
            finally
            {
                monitorStop.Cancel();
                try { await monitorTask; }
                catch (OperationCanceledException) when (monitorStop.IsCancellationRequested) { }
                lock (_running) _running.Remove(job.Id);
            }
        }
        finally { _singleWorker.Release(); }
    }

    /// <summary>
    /// Observe STOP persisted by a second NOX window in the existing queue.
    /// This cooperatively cancels our local HTTP token, not the entire Ollama server.
    /// </summary>
    private async Task WatchSharedCancelAsync(Guid jobId, CancellationTokenSource local,
        CancellationToken stop)
    {
        try
        {
            while (!stop.IsCancellationRequested && !local.IsCancellationRequested)
            {
                var jobs = await store.ReadAsync(stop);
                var state = jobs.FirstOrDefault(x => x.Id == jobId)?.State;
                if (state != ModelJobState.Running)
                {
                    local.Cancel();
                    return;
                }
                await Task.Delay(250, stop);
            }
        }
        catch (OperationCanceledException) when (stop.IsCancellationRequested) { }
        catch (Exception ex)
        {
            // If persisted STOP cannot be observed, do not silently continue an
            // unowned model transfer. Leave the existing receipt and queue intact.
            try { local.Cancel(); }
            catch (ObjectDisposedException) { }
            System.Diagnostics.Trace.TraceError(
                "P03_CANCEL_WATCH_ERROR job={0} type={1}", jobId, ex.GetType().Name);
        }
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
                // The worker owns this CTS and may retire/dispose it while the
                // durable intent write above is awaited. The STOP request was
                // persisted; losing that completion race is not an error.
                // Never hold _running while invoking cancellation callbacks:
                // callbacks can reenter owner cleanup or another STOP request.
                try { running.Cancel(); }
                catch (ObjectDisposedException) { }
                catch (AggregateException ex)
                {
                    // The intent was already persisted in the queue. A native
                    // callback failure must not lose that cancellation request.
                    System.Diagnostics.Trace.TraceError(
                        "P03_CANCEL_CALLBACK_FAILED job={0} type={1}",
                        id, ex.GetType().Name);
                }
                return true;
            }
            // STOP can arrive after token registration but before the atomic
            // Queued->Running claim. Persist the cancellation at that boundary.
            if (record?.State == ModelJobState.Queued)
                return await store.RequestCancelAsync(id, ct);
            return false;
        }
        return await store.RequestCancelAsync(id, ct);
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
