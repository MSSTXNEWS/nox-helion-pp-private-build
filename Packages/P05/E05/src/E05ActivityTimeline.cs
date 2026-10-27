using System;
using System.Collections.Generic;
using System.Linq;

namespace NoxHelion.E05;

public sealed record E05ActivityItem(string TaskId, string PackageId,
    string EventType, string State, DateTimeOffset LastSeenUtc,
    long? ProgressNumerator, long? ProgressDenominator);
public sealed class E05ActivityTimeline
{
    private readonly Dictionary<string, E05ActivityItem> current = new(StringComparer.Ordinal);
    private readonly HashSet<string> processedIds = new(StringComparer.Ordinal);
    private readonly string expectedRunId;
    public E05ActivityTimeline(string expectedRunId)
    {
        if (string.IsNullOrWhiteSpace(expectedRunId)) throw new ArgumentException("RunID");
        this.expectedRunId = expectedRunId;
    }
    // Only actual host-origin event bytes. No timers, synthetic counters, or acceptance promotion.
    public bool Accept(E05CanonicalEvent e, DateTimeOffset now)
    {
        if (!E05CanonicalEventFactory.IsCanonical(e) || e.RunId != expectedRunId ||
            e.EventType == "acceptance.updated" || e.EvidenceVerified ||
            e.TimestampUtc > now || now - e.TimestampUtc > TimeSpan.FromMinutes(5) ||
            !processedIds.Add(e.EventId)) return false;
        var key = e.PackageId + "/" + e.TaskId;
        if (current.TryGetValue(key, out var old) && e.TimestampUtc < old.LastSeenUtc)
            return false;
        current[key] = new(e.TaskId, e.PackageId, e.EventType, e.State,
            e.TimestampUtc, e.Numerator, e.Denominator);
        // The host may recycle the timeline per RunID; cap memory without dropping state.
        if (processedIds.Count > 10000) processedIds.Clear();
        return true;
    }
    public IReadOnlyList<E05ActivityItem> Read(DateTimeOffset now) =>
        current.Values.Select(x => now - x.LastSeenUtc > TimeSpan.FromMinutes(2)
            ? x with { State = "OFFLINE", ProgressNumerator = null,
                ProgressDenominator = null } : x).ToArray();
}
