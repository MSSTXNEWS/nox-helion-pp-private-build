using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Cryptography;
using System.Text;

namespace NoxHelion.E05;

public sealed record E05SealedCriterion(string TaskId, decimal Weight,
    string State, string? OwnerReceipt, string? EvidenceSha256);
public sealed record E05SealedLane(int LaneId, string ManifestSha256,
    IReadOnlyList<E05SealedCriterion> Criteria);
public interface IE05ReceiptVerifier
{
    // E06 supplies an independent verifier against exact, frozen bytes/owner/RunID.
    bool IsFrozenManifest(string manifestSha256, int laneId);
    bool IsVerified(string taskId, string receiptId, string evidenceSha256);
}
public static class E05SealedProgress
{
    public static decimal? Evaluate(E05SealedLane? lane, IE05ReceiptVerifier? verifier)
    {
        if (lane is null || verifier is null || lane.LaneId is < 1 or > 5 ||
            !IsSha256(lane.ManifestSha256) ||
            !verifier.IsFrozenManifest(lane.ManifestSha256, lane.LaneId) ||
            lane.Criteria.Count == 0) return null;
        decimal total = 0, done = 0;
        var unique = new HashSet<string>(StringComparer.Ordinal);
        foreach (var c in lane.Criteria)
        {
            if (string.IsNullOrWhiteSpace(c.TaskId) || !unique.Add(c.TaskId) ||
                c.Weight <= 0 || c.Weight > 1000) return null;
            checked { total += c.Weight; }
            if (c.State == "ACCEPTED")
            {
                if (string.IsNullOrWhiteSpace(c.OwnerReceipt) ||
                    !IsSha256(c.EvidenceSha256) ||
                    !verifier.IsVerified(c.TaskId, c.OwnerReceipt, c.EvidenceSha256!)) return null;
                done += c.Weight;
            }
            else if (c.State is not ("OPEN" or "FAILED" or "HOLD")) return null;
        }
        return total > 0 ? Math.Round(100 * done / total, 2) : null;
    }
    public static decimal? Overall(IReadOnlyList<E05SealedLane> lanes,
        IE05ReceiptVerifier? verifier)
    {
        if (lanes.Count != 5) return null;
        decimal[] weights = { .20m, .25m, .20m, .25m, .10m };
        decimal result = 0;
        for (int i = 0; i < 5; i++)
        {
            if (lanes[i].LaneId != i + 1) return null;
            var percent = Evaluate(lanes[i], verifier);
            if (percent is null) return null;
            result += percent.Value * weights[i];
        }
        return Math.Round(result, 2);
    }
    private static bool IsSha256(string? hash) => hash is { Length: 64 } &&
        hash.All(c => (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') ||
            (c >= 'A' && c <= 'F'));
}
