using System;
using System.Collections.Generic;
using System.Linq;

namespace NoxHelion.E05;

// Read-only secondary NOX SPACE + mobile projection. The native host supplies
// pre-approved licenses, validated provider responses and its CURRENT RunID.
// Nothing here opens an endpoint, creates UI elements, or writes events.
public static class E05ApprovedSpace
{
    public static E05ReadOnlySpace Project(string runId, DateTimeOffset now,
        IReadOnlyList<FeedResult>? feeds,
        IReadOnlyDictionary<string, ApprovedFeed>? approved,
        E05HardwareFrame? verifiedHostFrame, decimal? attestedProductProgress)
    {
        if (string.IsNullOrWhiteSpace(runId)) throw new ArgumentException("RunID required");
        var tiles = new List<E05SpaceTile>(16);
        foreach (var f in (feeds ?? Array.Empty<FeedResult>()).Take(16))
        {
            if (f is null) continue;
            ApprovedFeed? src = null;
            if (approved is not null && f.Id is not null)
                approved.TryGetValue(f.Id, out src);
            var trust = E05FeedTrust.Classify(f, src, now);
            bool licensedAndFresh = trust.Status == "SOURCE_DATED" &&
                f.FetchedAt.HasValue && f.FetchedAt <= now &&
                now - f.FetchedAt.Value <= src!.Ttl;
            var status = licensedAndFresh ? "SOURCE_DATED" :
                trust.Status == "SOURCE_DATED" ? "STALE" : trust.Status;
            tiles.Add(new E05SpaceTile(Safe(f.Id), Safe(f.Provider), status,
                f.SourceTimestamp, f.FetchedAt, null));
        }
        var points = Array.Empty<SensorPoint>();
        if (verifiedHostFrame is not null && verifiedHostFrame.RunId == runId &&
            verifiedHostFrame.PolledUtc <= now &&
            now - verifiedHostFrame.PolledUtc <= TimeSpan.FromSeconds(30) &&
            verifiedHostFrame.Sensors is not null)
        {
            points = verifiedHostFrame.Sensors.Select(p =>
            {
                bool valid = p is not null && p.Status == "LIVE" &&
                    p.Value.HasValue && double.IsFinite(p.Value.Value) &&
                    p.ObservedAtUtc.HasValue && p.ObservedAtUtc <= now &&
                    now - p.ObservedAtUtc.Value <= TimeSpan.FromSeconds(30) &&
                    (p.Key == "cpu.system.percent" || p.Key == "gpu.percent" ||
                     p.Key == "gpu.vram.used_bytes" || p.Key == "gpu.vram.total_bytes" ||
                     p.Key == "gpu.temperature.c");
                return valid ? p! :
                    (p is null ? new SensorPoint("UNVERIFIED", null, "", "NONE", null, "N_D") :
                    p with { Value = null, ObservedAtUtc = null, Status = "N_D" });
            }).ToArray();
        }
        return new E05ReadOnlySpace("NOX-E05-READONLY-v1", runId, now, "READ_ONLY",
            tiles, points, attestedProductProgress is >= 0 and <= 100
                ? attestedProductProgress : null);
    }

    private static string Safe(string? value) =>
        value is { Length: > 0 and <= 100 } &&
        value.All(c => char.IsLetterOrDigit(c) || c is '_' or '-' or '.' or ' ')
        ? value : "UNVERIFIED";
}
