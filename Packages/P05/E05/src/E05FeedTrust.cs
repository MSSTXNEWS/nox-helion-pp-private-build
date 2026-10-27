using System;
using System.Collections.Generic;
using System.Linq;

namespace NoxHelion.E05;

public sealed record E05SourceTrust(string Id, string Status,
    string Provider, DateTimeOffset? SourceUtc, DateTimeOffset? FetchUtc,
    string Reason);
public static class E05FeedTrust
{
    // Explicitly configured provider sources only; no invented BTC/Brent/FX values.
    public static readonly IReadOnlyList<string> SupportedIds = new[] {
        "weather", "nox-news", "msstx-news", "eur-usd", "eur-rub",
        "bitcoin", "brent", "finance-news"
    };
    public static E05SourceTrust Classify(FeedResult result, ApprovedFeed? approved,
        DateTimeOffset now)
    {
        if (approved is null || !E05SafeFeedClient.Valid(approved) ||
            result.Id != approved.Id || result.Provider != approved.Provider ||
            !SupportedIds.Contains(result.Id))
            return new(result.Id, "DISABLED", result.Provider, null, null,
                "SOURCE_NOT_APPROVED");
        if (!result.SourceTimestamp.HasValue || !result.FetchedAt.HasValue ||
            result.SourceTimestamp > now || result.FetchedAt > now)
            return new(result.Id, "N_D", result.Provider, result.SourceTimestamp,
                result.FetchedAt, "MISSING_OR_FUTURE_TIME");
        if (now - result.SourceTimestamp > approved.MaxSourceAge || result.Stale)
            return new(result.Id, "STALE", result.Provider, result.SourceTimestamp,
                result.FetchedAt, "SOURCE_TOO_OLD_OR_OFFLINE");
        return new(result.Id, result.Status is "LIVE" or "CACHE" ? "SOURCE_DATED" : "N_D",
            result.Provider, result.SourceTimestamp, result.FetchedAt, result.ErrorCode ?? "OK");
    }
}
