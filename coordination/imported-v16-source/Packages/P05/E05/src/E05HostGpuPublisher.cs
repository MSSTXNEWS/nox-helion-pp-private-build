using System;
using System.Threading;
using System.Threading.Tasks;

namespace NoxHelion.E05;

// E06 owns the ONLY real EventV3Bridge implementation of IE05HostEventV3Port.
// This class cannot publish directly to a second bus or write a journal.
public sealed record E05HostPublishReceipt(string RunId, string Status, string? EventId);
public static class E05HostGpuPublisher
{
    public static async ValueTask<E05HostPublishReceipt> PublishAsync(
        IE05HostEventV3Port? host, string runId, SensorPoint? reading,
        DateTimeOffset now, CancellationToken stop)
    {
        stop.ThrowIfCancellationRequested();
        if (string.IsNullOrWhiteSpace(runId) || runId.Length > 160)
            return new(runId ?? string.Empty, "HOLD_INVALID_RUNID", null);
        if (host is null) return new(runId, "HOLD_HOST_UNBOUND", null);
        if (reading is null) return new(runId, "HOLD_SENSOR_UNAVAILABLE", null);
        var evt = E05CanonicalEventFactory.GpuUtilization(runId, reading, now);
        if (evt is null || !E05CanonicalEventFactory.IsCanonical(evt))
            return new(runId, "HOLD_SENSOR_UNVERIFIED", null);
        try
        {
            bool accepted = await host.PublishAsync(evt, stop).ConfigureAwait(false);
            return accepted ? new(runId, "HOST_ACCEPTED", evt.EventId)
                            : new(runId, "HOLD_HOST_REJECTED", null);
        }
        catch (OperationCanceledException) when (stop.IsCancellationRequested) { throw; }
        catch (Exception) { return new(runId, "HOLD_HOST_ERROR", null); }
    }
}
