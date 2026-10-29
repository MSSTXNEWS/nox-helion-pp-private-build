using System;
using System.Collections.Generic;
using System.Linq;

namespace NoxHelion.E05;

// E05 TaskIDs are fixed, but only E06's approved frozen criterion manifest can
// provide a denominator. These rows never masquerade as accepted percentages.
public static class E05TaskIds
{
    public static readonly string[] All = {
        "E05-01", "E05-02", "E05-03", "E05-04", "E05-05", "E05-06", "E05-07"
    };
}
public sealed record ReadinessBar(int Executor, string State,
    decimal? Percent, string? TaskManifest, string? Receipt,
    string? Blocker, DateTimeOffset At);
public sealed record ReadinessSnapshot(IReadOnlyList<ReadinessBar> Bars,
    decimal? Overall, string RunId, DateTimeOffset At);

public static class ReadinessProjection
{
    // E06 and E07 are gates only. Never call an unknown denominator "0%".
    public static ReadinessSnapshot Evaluate(string runId,
        IReadOnlyList<LaneProof?> currentProductLanes,
        string integrationState, string acceptanceState,
        DateTimeOffset at)
    {
        if (string.IsNullOrWhiteSpace(runId)) throw new ArgumentException(nameof(runId));
        if (currentProductLanes.Count != 5) throw new ArgumentException("Five product lanes required");
        var bars = new List<ReadinessBar>(7);
        for (int i = 0; i < 5; i++)
        {
            LaneProof? lane = currentProductLanes[i];
            decimal? pct = lane?.LaneId == i + 1 ? ProgressMath.LanePercent(lane) : null;
            bars.Add(new ReadinessBar(i + 1, pct is null ? "N/D" : "CRITERIA_MEASURED",
                pct, lane?.ManifestReceipt, null,
                pct is null ? "NO_FROZEN_CRITERIA_OR_RECEIPTS" : null, at));
        }
        // Gates must be shown separately. They have no numerical weight.
        bars.Add(new ReadinessBar(6, integrationState, null, null, null,
            integrationState == "PASS" ? null : "INTEGRATION_NOT_ATTESTED", at));
        bars.Add(new ReadinessBar(7, acceptanceState, null, null, null,
            acceptanceState == "PASS" ? null : "INDEPENDENT_QA_NOT_ATTESTED", at));
        var known = currentProductLanes.All(x => x is not null) &&
            currentProductLanes.Select((x, i) => x!.LaneId == i + 1).All(x => x);
        var overall = known ? ProgressMath.Overall(currentProductLanes.Select(x => x!).ToList()) : null;
        return new ReadinessSnapshot(bars, overall, runId, at);
    }
}
