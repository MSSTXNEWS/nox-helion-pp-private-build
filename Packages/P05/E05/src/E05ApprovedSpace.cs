using System;
using System.Collections.Generic;
using System.Linq;

namespace NoxHelion.E05;

// Read-only secondary NOX SPACE + mobile projection. The native host supplies
// pre-approved licenses, validated provider responses and its CURRENT RunID.
// Nothing here opens an endpoint, creates UI elements, or writes events.
public static class E05ApprovedSpace
{
    // Compatibility entry point: an unverified raw number is NOT an owner
    // receipt. Preserve the old signature, but never echo it as product progress.
    public static E05ReadOnlySpace Project(string runId, DateTimeOffset now,
        IReadOnlyList<FeedResult>? feeds,
        IReadOnlyDictionary<string, ApprovedFeed>? approved,
        E05HardwareFrame? verifiedHostFrame, decimal? unverifiedProductProgress)
        => ProjectCore(runId, now, feeds, approved, verifiedHostFrame, null);

    // Only the E06 frozen-ledger verifier can authorize a numerical SPACE bar.
    // Re-check the five owner seals; a caller-created ReadinessSnapshot alone
    // or a stale/foreign RunID must not become an authoritative percentage.
    public static E05ReadOnlySpace ProjectVerified(string runId, DateTimeOffset now,
        IReadOnlyList<FeedResult>? feeds,
        IReadOnlyDictionary<string, ApprovedFeed>? approved,
        E05HardwareFrame? verifiedHostFrame, ReadinessSnapshot? readiness,
        IReadOnlyList<E05SealedLane>? frozenLanes, IE05ReceiptVerifier? verifier)
    {
        decimal? progress = null;
        if (readiness is not null && frozenLanes is { Count: 5 } &&
            verifier is not null && readiness.RunId == runId &&
            readiness.At.Offset == TimeSpan.Zero && readiness.At <= now &&
            now - readiness.At <= TimeSpan.FromSeconds(30) &&
            readiness.Bars is { Count: 7 })
        {
            try
            {
                bool consistent = true;
                for (int i = 0; i < 5; i++)
                {
                    var bar = readiness.Bars[i];
                    var lane = frozenLanes[i];
                    var independentlyVerified = E05SealedProgress.Evaluate(lane, verifier);
                    if (bar is null || lane is null || lane.LaneId != i + 1 ||
                        bar.Executor != i + 1 || bar.State != "CRITERIA_VERIFIED" ||
                        bar.TaskManifest != lane.ManifestSha256 ||
                        !independentlyVerified.HasValue ||
                        bar.Percent != independentlyVerified) consistent = false;
                }
                var weighted = E05SealedProgress.Overall(frozenLanes, verifier);
                if (consistent && weighted.HasValue && weighted == readiness.Overall &&
                    weighted >= 0 && weighted <= 100 &&
                    readiness.Bars[5] is { Executor: 6, Percent: null } &&
                    readiness.Bars[6] is { Executor: 7, Percent: null })
                    progress = weighted;
            }
            catch (Exception) { /* Corrupt or unsealed ledger remains N/D. */ }
        }
        return ProjectCore(runId, now, feeds, approved, verifiedHostFrame, progress);
    }

    private static E05ReadOnlySpace ProjectCore(string runId, DateTimeOffset now,
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
