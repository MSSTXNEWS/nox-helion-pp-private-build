namespace Nox.P03;

public sealed record ModelLifecycleEvent(
    Guid EventId,
    Guid JobId,
    string ModelTag,
    string Phase,
    string Status,
    long? CompletedBytes,
    long? TotalBytes,
    string? Digest,
    string? Error,
    DateTimeOffset AtUtc);

/// <summary>Adapters publish the same immutable event to P01 UI and P05 install/run receipts.</summary>
public interface IModelLifecycleEventSink
{
    ValueTask PublishToP01Async(ModelLifecycleEvent modelEvent, CancellationToken ct);
    ValueTask PublishToP05Async(ModelLifecycleEvent modelEvent, CancellationToken ct);
}

public sealed class ModelLifecyclePublisher(IModelLifecycleEventSink sink)
{
    public async ValueTask PublishAsync(ModelLifecycleEvent e, CancellationToken ct)
    {
        // A UI rendering failure must not suppress durable P05 event delivery.
        // Report failures to the existing worker SafePublishAsync after both
        // independent owner sinks have been attempted.
        Exception? firstFailure = null;
        try { await sink.PublishToP01Async(e, ct); }
        catch (Exception ex) when (ex is not OutOfMemoryException) { firstFailure = ex; }
        try { await sink.PublishToP05Async(e, ct); }
        catch (Exception ex) when (ex is not OutOfMemoryException)
        {
            if (firstFailure is null) firstFailure = ex;
        }
        if (firstFailure is not null) throw firstFailure;
    }
}