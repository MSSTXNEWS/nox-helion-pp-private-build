using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;

namespace NoxHelion.E05;

// E05 component-side contract for the single E06 native owner adapter.
// Source-only: no service, process, UI shell, bridge, or event journal is created.
public static class E05HostTelemetryFacade
{
    public static E05HardwareFrame ReadVerified(string runId,
        IEnumerable<ISensorProvider> installedProviders, DateTimeOffset now,
        CancellationToken stop)
    {
        if (string.IsNullOrWhiteSpace(runId) || installedProviders is null)
            return new E05HardwareFrame(runId ?? "", now, Array.Empty<SensorPoint>(),
                "UNAVAILABLE");
        return E05HardwareEvidence.Snapshot(runId, installedProviders, now, stop);
    }

    public static async ValueTask<E05HostPublishReceipt> PublishGpuAsync(
        IE05HostEventV3Port? ownerHost, E05HardwareFrame? frame,
        DateTimeOffset now, CancellationToken stop)
    {
        stop.ThrowIfCancellationRequested();
        if (frame is null || string.IsNullOrWhiteSpace(frame.RunId) ||
            frame.PolledUtc > now || now - frame.PolledUtc > TimeSpan.FromSeconds(30))
            return new(frame?.RunId ?? "", "HOLD_FRAME_STALE", null);
        var gpu = frame.Sensors?.FirstOrDefault(x => x.Key == "gpu.percent");
        if (gpu is null || gpu.Status != "LIVE")
            return new(frame.RunId, "HOLD_SENSOR_UNVERIFIED", null);
        return await E05HostGpuPublisher.PublishAsync(ownerHost, frame.RunId,
            gpu, now, stop).ConfigureAwait(false);
    }
}
