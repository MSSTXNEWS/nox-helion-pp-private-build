using System;
using System.Collections.Generic;
using System.Linq;

namespace NoxHelion.E05;

public sealed record E05SpaceTile(string FeedId, string Source, string Status,
    DateTimeOffset? SourceUtc, DateTimeOffset? FetchedUtc, string? Preview);
public sealed record E05ReadOnlySpace(string Schema, string RunId,
    DateTimeOffset SnapshotUtc, string Access, IReadOnlyList<E05SpaceTile> Tiles,
    IReadOnlyList<SensorPoint> Hardware, decimal? ProductProgress);
public static class E05SpaceReadOnlyProjection
{
    // A view-model only; no new HTTP server, token bridge, or PC-control endpoint.
    // #1 uses this on secondary NOX SPACE screens; HOME remains central + 8 CoreIDs.
    public static E05ReadOnlySpace Build(string runId, DateTimeOffset now,
        IReadOnlyList<FeedResult> feeds, E05HardwareFrame? frame,
        decimal? provenProductPercent)
    {
        if (string.IsNullOrWhiteSpace(runId)) throw new ArgumentException("RunID");
        var tiles = feeds.Take(16).Select(f =>
        {
            bool valid = f.SourceTimestamp.HasValue && f.FetchedAt.HasValue &&
                f.SourceTimestamp <= now && now - f.SourceTimestamp <= TimeSpan.FromHours(24) &&
                f.Status is ("LIVE" or "CACHE") && !f.Stale;
            return new E05SpaceTile(Safe(f.Id), Safe(f.Provider),
                valid ? "SOURCE_DATED" : f.Stale ? "STALE" : "N_D",
                f.SourceTimestamp, f.FetchedAt, null);
        }).ToArray();
        var sensors = frame is not null && frame.RunId == runId &&
            now >= frame.PolledUtc && now - frame.PolledUtc <= TimeSpan.FromSeconds(30)
            ? frame.Sensors : Array.Empty<SensorPoint>();
        var percent = provenProductPercent is >= 0 and <= 100 ? provenProductPercent : null;
        return new("NOX-E05-READONLY-v1", runId, now, "READ_ONLY", tiles, sensors,
            percent);
    }
    private static string Safe(string value) => value is { Length: <= 100 } &&
        value.All(c => char.IsLetterOrDigit(c) || c is '_' or '-' or '.' or ' ')
        ? value : "UNVERIFIED";
}