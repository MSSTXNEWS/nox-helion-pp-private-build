using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using NoxHelion.E05;

// Isolated deterministic checks; no real GPU, Docs, URL or external credentials.
public static class E05HostTelemetryChecks
{
    public static async Task RunAsync()
    {
        static void Verify(bool result, string label)
        {
            if (!result) throw new Exception(label);
            Console.WriteLine("PASS " + label);
        }
        var now = DateTimeOffset.UtcNow;
        ISensorProvider[] providers = {
            new FixtureSensor(new SensorPoint("gpu.percent", 39, "%", "NVIDIA.NVML", now, "LIVE"),
                new SensorPoint("gpu.vram.used_bytes", 2048, "bytes", "NVIDIA.NVML", now, "LIVE"),
                new SensorPoint("gpu.vram.total_bytes", 1024, "bytes", "NVIDIA.NVML", now, "LIVE"))
        };
        var frame = E05HostTelemetryFacade.ReadVerified("NOX-E05-FIXTURE",
            providers, now, CancellationToken.None);
        Verify(frame.Sensors.Single(x => x.Key == "gpu.vram.used_bytes").Value is null,
            "FACADE C13 invalid VRAM cannot appear live");
        Verify(frame.Sensors.Single(x => x.Key == "gpu.percent").Value == 39,
            "FACADE C13 legitimate GPU sample remains available");
        var unbound = await E05HostTelemetryFacade.PublishGpuAsync(null, frame, now,
            CancellationToken.None);
        Verify(unbound.Status == "HOLD_HOST_UNBOUND", "FACADE C13 no host is HOLD");
        var owner = new FixtureHost();
        var published = await E05HostTelemetryFacade.PublishGpuAsync(owner, frame, now,
            CancellationToken.None);
        Verify(published.Status == "HOST_ACCEPTED" && owner.EventType == "gpu.sample" &&
            owner.Count == 1, "FACADE C13 only canonical gpu.sample reaches host");
        var stale = await E05HostTelemetryFacade.PublishGpuAsync(owner, frame,
            now.AddMinutes(1), CancellationToken.None);
        Verify(stale.Status == "HOLD_FRAME_STALE" && owner.Count == 1,
            "FACADE C13 expired sample cannot be replayed");
        var missing = E05HostTelemetryFacade.ReadVerified("", providers, now,
            CancellationToken.None);
        Verify(missing.State == "UNAVAILABLE" && missing.Sensors.Count == 0,
            "FACADE C13 unbound run remains unavailable");
    }
    private sealed class FixtureSensor : ISensorProvider
    {
        private readonly SensorPoint[] values;
        public string Name => "fixture";
        public FixtureSensor(params SensorPoint[] values) { this.values = values; }
        public IReadOnlyList<SensorPoint> Read(CancellationToken stop) => values;
    }
    private sealed class FixtureHost : IE05HostEventV3Port
    {
        public int Count { get; private set; }
        public string? EventType { get; private set; }
        public ValueTask<bool> PublishAsync(E05CanonicalEvent e, CancellationToken stop)
        {
            Count++; EventType = e.EventType;
            return ValueTask.FromResult(E05CanonicalEventFactory.IsCanonical(e));
        }
    }
}
