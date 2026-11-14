using System;
using System.Collections.Generic;
using System.Linq;

namespace NoxHelion.E05;

// The ONLY projection intended for product percentage UI. The legacy LaneProof
// convenience calculator is retained for old fixtures, not production claims.
// E06 owns the frozen current-source verifier and actual authorization.
public static class E05VerifiedReadiness
{
    public static ReadinessSnapshot Project(string runId, DateTimeOffset now,
        IReadOnlyList<E05SealedLane>? lanes, IE05ReceiptVerifier? verifier,
        string integrationGate, string qaGate)
    {
        if (string.IsNullOrWhiteSpace(runId)) throw new ArgumentException("RunID required");
        var bars = new List<ReadinessBar>(7);
        bool complete = lanes is { Count: 5 } && verifier is not null;
        decimal? overall = null;
        for (int i = 0; i < 5; i++)
        {
            var lane = complete ? lanes![i] : null;
            decimal? percent = null;
            if (lane is not null && lane.LaneId == i + 1)
                try { percent = E05SealedProgress.Evaluate(lane, verifier); }
                catch (Exception) { percent = null; }
            bars.Add(new ReadinessBar(i + 1,
                percent.HasValue ? "CRITERIA_VERIFIED" : "N/D",
                percent, percent.HasValue ? lane!.ManifestSha256 : null,
                null, percent.HasValue ? null : "FROZEN_LEDGER_OR_RECEIPT_MISSING", now));
        }
        if (complete && bars.Take(5).All(x => x.Percent.HasValue))
            try { overall = E05SealedProgress.Overall(lanes!, verifier); }
            catch (Exception) { overall = null; }
        // Integration and E07 are independent gates, never weighted progress.
        bars.Add(new ReadinessBar(6, integrationGate == "PASS" ? "PASS" : "HOLD",
            null, null, null, integrationGate == "PASS" ? null : "E06_NOT_ACCEPTED", now));
        bars.Add(new ReadinessBar(7, qaGate == "PASS" ? "PASS" : "NOT_RUN",
            null, null, null, qaGate == "PASS" ? null : "E07_NOT_ACCEPTED", now));
        return new ReadinessSnapshot(bars, overall, runId, now);
    }
}
