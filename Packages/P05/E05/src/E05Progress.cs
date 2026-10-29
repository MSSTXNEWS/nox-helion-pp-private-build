using System;
using System.Collections.Generic;
using System.Linq;

namespace NoxHelion.E05;

public sealed record TaskCriterion(string TaskId, decimal Weight, string Status, string? ReceiptId);
public sealed record LaneProof(int LaneId, string ManifestReceipt,
    IReadOnlyList<TaskCriterion> Criteria);
public sealed record CoreProof(string CoreId, double? Percent, string Status,
    string? ReceiptId, DateTimeOffset? MeasuredAt);
public sealed record PersonaProof(string PersonaId, string Status, DateTimeOffset? ObservedAt);

public static class ProgressMath
{
    private static readonly decimal[] ProductWeights = { .20m, .25m, .20m, .25m, .10m };
    // Requires a frozen denominator and a receipt for every ACCEPTED criterion.
    // OPEN/HOLD/FAILED remain zero contribution, while invalid evidence yields N/D.
    public static decimal? LanePercent(LaneProof? lane)
    {
        if (lane is null || string.IsNullOrWhiteSpace(lane.ManifestReceipt) ||
            lane.Criteria is null || lane.Criteria.Count == 0) return null;
        decimal total = 0, done = 0;
        bool allAccepted = true;
        var unique = new HashSet<string>(StringComparer.Ordinal);
        foreach (var item in lane.Criteria)
        {
            if (!unique.Add(item.TaskId) || item.Weight <= 0 ||
                string.IsNullOrWhiteSpace(item.TaskId)) return null;
            total += item.Weight;
            if (item.Status == "ACCEPTED")
            {
                if (string.IsNullOrWhiteSpace(item.ReceiptId)) return null;
                done += item.Weight;
            }
            else
            {
                allAccepted = false;
                if (item.Status is not ("OPEN" or "HOLD" or "FAILED")) return null;
            }
        }
        // Completion is determined by TaskID states, never rounding alone.
        return allAccepted ? 100m : Math.Min(99.99m, decimal.Round(100 * done / total, 2));
    }
    // E06/E07 are gates, not numerical product weights.
    public static decimal? Overall(IReadOnlyList<LaneProof>? lanes)
    {
        if (lanes is null || lanes.Count != 5) return null;
        decimal result = 0;
        bool allAccepted = true;
        for (int i = 0; i < 5; i++)
        {
            if (lanes[i].LaneId != i + 1) return null;
            decimal? pct = LanePercent(lanes[i]);
            if (!pct.HasValue) return null;
            allAccepted &= pct.Value == 100m;
            result += pct.Value * ProductWeights[i];
        }
        return allAccepted ? 100m : Math.Min(99.99m, decimal.Round(result, 2));
    }
    // The eight orbit scores are not project readiness percentages.
    public static double? CoreAverage(IReadOnlyList<CoreProof>? cores)
    {
        if (cores is null || cores.Count != 8) return null;
        var unique = new HashSet<string>(StringComparer.Ordinal);
        double sum = 0;
        foreach (var c in cores)
        {
            if (!unique.Add(c.CoreId) || c.Status != "VERIFIED" ||
                string.IsNullOrWhiteSpace(c.ReceiptId) ||
                c.Percent is null || !double.IsFinite(c.Percent.Value) ||
                c.Percent < 0 || c.Percent > 100 || c.MeasuredAt is null) return null;
            sum += c.Percent.Value;
        }
        return Math.Round(sum / 8, 2);
    }
    public static bool PersonasValid(IReadOnlyList<PersonaProof>? personas) =>
        personas is { Count: 5 } && personas.All(x =>
            !string.IsNullOrWhiteSpace(x.PersonaId) &&
            (x.Status == "AVAILABLE" || x.Status == "OFFLINE")) &&
        personas.Select(x => x.PersonaId).Distinct(StringComparer.Ordinal).Count() == 5;
}
