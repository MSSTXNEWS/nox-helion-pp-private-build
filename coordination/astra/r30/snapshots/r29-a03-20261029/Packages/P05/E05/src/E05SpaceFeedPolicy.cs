// Adapter catalog ported from existing E05 PR #9 policy. No network is enabled by default.
using System;
using System.Collections.Generic;

namespace NoxHelion.E05;

public static class E05SpaceFeedPolicy
{
    public static IReadOnlyList<(string Id, string Category, bool Enabled)> Catalog() =>
        new (string Id, string Category, bool Enabled)[] {
            ("weather", "weather", false),
            ("nox-news", "news", false),
            ("msstx-news", "news", false),
            ("eur-usd", "fx", false),
            ("eur-rub", "fx", false),
            ("bitcoin", "crypto", false),
            ("brent", "commodity", false),
            ("finance-news", "news", false)
        };
}
