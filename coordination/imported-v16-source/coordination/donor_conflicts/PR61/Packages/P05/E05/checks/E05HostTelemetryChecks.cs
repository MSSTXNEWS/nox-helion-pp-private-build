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
        // TURBO10: real host-owned polling, no telemetry.snapshot or second bus.
        var received = new List<E05HardwareFrame>();
        var liveHost = new FixtureHost();
        var session = new E05SamplingLoop(liveHost, providers, TimeSpan.FromSeconds(2),
            frame => received.Add(frame));
        var sessionAck = await session.PollVerifiedOnceAsync("NOX-E05-FIXTURE",
            CancellationToken.None);
        Verify(sessionAck.Status == "HOST_ACCEPTED" && liveHost.Count == 1 &&
            liveHost.EventType == "gpu.sample" && received.Count == 1 &&
            received[0].RunId == "NOX-E05-FIXTURE",
            "TURBO10 host poll emits only canonical gpu.sample, frame is read only");
        var noSensorHost = new FixtureHost();
        var unavailableFrames = new List<E05HardwareFrame>();
        var unavailableSession = new E05SamplingLoop(noSensorHost,
            Array.Empty<ISensorProvider>(), TimeSpan.FromSeconds(2),
            f => unavailableFrames.Add(f));
        var unavailableAck = await unavailableSession.PollVerifiedOnceAsync(
            "NOX-E05-FIXTURE", CancellationToken.None);
        Verify(unavailableAck.Status == "HOLD_SENSOR_UNVERIFIED" &&
            unavailableFrames.Count == 1 && noSensorHost.Count == 0,
            "TURBO10 missing sensor never makes invented GPU events");
        using var cancelled = new CancellationTokenSource();
        cancelled.Cancel();
        try {
            await session.PollVerifiedOnceAsync("NOX-E05-FIXTURE", cancelled.Token);
            throw new Exception("TURBO10 cancelled sampling was not stopped");
        }
        catch (OperationCanceledException) {
            Verify(liveHost.Count == 1 && received.Count == 1,
                "TURBO10 STOP cancels before sampling or event publication");
        }
        // TURBO10 R02: cancellation from the ONE host-owned callback exits
        // the periodic loop before any second sample or fabricated event.
        using var stopAtFirst = new CancellationTokenSource();
        var stopFrameCount = 0;
        var stopHost = new FixtureHost();
        var stopLoop = new E05SamplingLoop(stopHost,
            Array.Empty<ISensorProvider>(), TimeSpan.FromSeconds(2),
            _ => { stopFrameCount++; stopAtFirst.Cancel(); });
        try {
            await stopLoop.RunAsync("NOX-E05-FIXTURE", stopAtFirst.Token);
            throw new Exception("TURBO10 R02 cancellation did not stop loop");
        }
        catch (OperationCanceledException) {
            Verify(stopFrameCount == 1 && stopHost.Count == 0,
                "TURBO10 R02 STOP ends one canonical loop without fake GPU");
        }
        try {
            await stopLoop.RunAsync(new string('x', 161), CancellationToken.None);
            throw new Exception("TURBO10 R02 bad RunID was admitted");
        }
        catch (ArgumentException) {
            Verify(stopFrameCount == 1,
                "TURBO10 R02 oversized RunID rejected before sampling");
        }
        var legacy = new E05SamplingLoop(
            new E05SensorPublisher(Array.Empty<ISensorProvider>(),
                new FixtureLegacyTransport()), TimeSpan.FromSeconds(2));
        try {
            await legacy.RunAsync("NOX-E05-FIXTURE", CancellationToken.None);
            throw new Exception("TURBO10 R02 legacy noncanonical event was published");
        }
        catch (NotSupportedException) {
            Verify(true, "TURBO10 R02 legacy noncanonical event stays fail-closed");
        }
    }
    private sealed class FixtureSensor : ISensorProvider
    {
        private readonly SensorPoint[] values;
        public string Name => "fixture";
        public FixtureSensor(params SensorPoint[] values) { this.values = values; }
        public IReadOnlyList<SensorPoint> Read(CancellationToken stop) => values;
    }
    private sealed class FixtureLegacyTransport : IEventV3Transport
    {
        public ValueTask SendAsync(TelemetryEventV3 e, CancellationToken stop) =>
            ValueTask.CompletedTask;
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
