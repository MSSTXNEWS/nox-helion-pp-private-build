// E05: provider descriptors are configuration ONLY; no invented values or unapproved network calls.
using System;
using System.Collections.Generic;

namespace NoxHelion.Space.E05;
public sealed record SpaceFeedDefinition(string FeedId, string Category,
    string Provider, Uri? ApprovedEndpoint, string? LicenseRecord,
    TimeSpan Ttl, TimeSpan Timeout, bool Enabled);
public static class SpaceFeedPolicy
{
    public static IReadOnlyList<SpaceFeedDefinition> DefaultUnconfigured() =>
        new[] {
            Disabled("weather", "weather"), Disabled("nox-news", "news"),
            Disabled("msstx-news", "news"), Disabled("eur-usd", "fx"),
            Disabled("eur-rub", "fx"), Disabled("bitcoin", "crypto"),
            Disabled("brent", "commodity"), Disabled("finance-news", "news")
        };
    private static SpaceFeedDefinition Disabled(string id, string category) =>
        new(id, category, "UNCONFIGURED", null, null, TimeSpan.FromMinutes(10),
            TimeSpan.FromSeconds(8), false);
    public static bool IsReady(SpaceFeedDefinition source) =>
        source.Enabled && source.ApprovedEndpoint is { Scheme: "https" } &&
        string.IsNullOrEmpty(source.ApprovedEndpoint.UserInfo) &&
        !string.IsNullOrWhiteSpace(source.Provider) &&
        !string.IsNullOrWhiteSpace(source.LicenseRecord);
}
