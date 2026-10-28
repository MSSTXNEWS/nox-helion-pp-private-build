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
            lane.Criteria is null || lane.Criteria.Count == 0) return null;
        decimal total = 0, done = 0;
        var unique = new HashSet<string>(StringComparer.Ordinal);
        foreach (var c in lane.Criteria)
        {
            if (c is null || string.IsNullOrWhiteSpace(c.TaskId) || !unique.Add(c.TaskId) ||
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
        if (lanes is null || lanes.Count != 5 || HasCrossLaneTaskCollision(lanes)) return null;
        decimal[] weights = { .20m, .25m, .20m, .25m, .10m };
        decimal result = 0;
        for (int i = 0; i < 5; i++)
        {
            if (lanes[i] is null || lanes[i].LaneId != i + 1) return null;
            var percent = Evaluate(lanes[i], verifier);
            if (percent is null) return null;
            result += percent.Value * weights[i];
        }
        return Math.Round(result, 2);
    }
    // A frozen TaskID identifies one project criterion, not one criterion per
    // owner. Local Evaluate guards duplicates within a lane; aggregate and UI
    // admission must also reject the same identity appearing in two lanes.
    // Missing rows remain unknown evidence, not invented duplicate identities.
    internal static bool HasCrossLaneTaskCollision(IReadOnlyList<E05SealedLane>? lanes)
    {
        if (lanes is null) return false;
        var owners = new Dictionary<string, int>(StringComparer.Ordinal);
        for (int i = 0; i < lanes.Count; i++)
        {
            var criteria = lanes[i]?.Criteria;
            if (criteria is null) continue;
            foreach (var criterion in criteria)
            {
                if (criterion is null || string.IsNullOrWhiteSpace(criterion.TaskId)) continue;
                if (owners.TryGetValue(criterion.TaskId, out int previous) && previous != i)
                    return true;
                owners[criterion.TaskId] = i;
            }
        }
        return false;
    }
    private static bool IsSha256(string? hash) => hash is { Length: 64 } &&
        hash.All(c => (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') ||
            (c >= 'A' && c <= 'F'));
}
