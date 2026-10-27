using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;

namespace NoxHelion.E05;

public sealed record E05HardwareFrame(string RunId, DateTimeOffset PolledUtc,
    IReadOnlyList<SensorPoint> Sensors, string State);

public static class E05HardwareEvidence
{
    private static readonly string[] Keys = {
        "cpu.system.percent", "gpu.percent", "gpu.vram.used_bytes",
        "gpu.vram.total_bytes", "gpu.temperature.c"
    };

    public static E05HardwareFrame Snapshot(string runId,
        IEnumerable<ISensorProvider> installedProviders, DateTimeOffset now,
        CancellationToken stop)
    {
        if (string.IsNullOrWhiteSpace(runId)) throw new ArgumentException("RunID required");
        var raw = new List<SensorPoint>();
        foreach (var provider in installedProviders)
        {
            stop.ThrowIfCancellationRequested();
            try { raw.AddRange(provider.Read(stop)); }
            catch (OperationCanceledException) when (stop.IsCancellationRequested) { throw; }
            catch (Exception) { /* hardware failure never becomes a fabricated sample */ }
        }
        var points = new List<SensorPoint>();
        foreach (var key in Keys)
        {
            var values = raw.Where(x => x.Key == key).ToArray();
            // Multiple conflicting providers cannot silently overwrite one another.
            var sample = values.Length == 1 ? values[0] : null;
            if (sample is null) { points.Add(new(key, null, Unit(key), "NONE", null,
                values.Length > 1 ? "PROVIDER_CONFLICT" : "UNAVAILABLE")); continue; }
            bool fresh = sample.Status == "LIVE" && sample.ObservedAtUtc.HasValue &&
                now >= sample.ObservedAtUtc && now - sample.ObservedAtUtc <= TimeSpan.FromSeconds(30);
            bool magnitude = sample.Value.HasValue && double.IsFinite(sample.Value.Value) &&
                sample.Value >= 0 && (key.EndsWith("percent") ? sample.Value <= 100 : true) &&
                (key.EndsWith("temperature.c") ? sample.Value <= 150 : true);
            if (!fresh || !magnitude)
                points.Add(sample with { Value = null, ObservedAtUtc = null,
                    Status = fresh ? "INVALID_VALUE" : "UNVERIFIED_OR_STALE" });
            else points.Add(sample);
        }
        var used = points.Single(x => x.Key == "gpu.vram.used_bytes");
        var total = points.Single(x => x.Key == "gpu.vram.total_bytes");
        if (used.Value.HasValue && total.Value.HasValue && (total.Value <= 0 || used.Value > total.Value))
        {
            for (int i = 0; i < points.Count; i++)
                if (points[i].Key.StartsWith("gpu.vram.", StringComparison.Ordinal))
                    points[i] = points[i] with { Value = null, ObservedAtUtc = null,
                        Status = "INCONSISTENT_VRAM" };
        }
        return new E05HardwareFrame(runId, now, points,
            points.Any(x => x.Status == "LIVE") ? "PARTIAL_OR_LIVE" : "UNAVAILABLE");
    }
    private static string Unit(string key) => key.EndsWith("percent") ? "%" :
        key.EndsWith("temperature.c") ? "°C" : "bytes";
}