using System;
using System.Collections.Generic;
using System.Linq;

namespace NoxHelion.E05;

public sealed record E05WowOption(string Name, string Owner, string Source,
    bool Enabled, string Reason);
public static class E05WowCompatibility
{
    // Existing PR9/14/15 visual effects are candidates, NOT 3 replacement shells.
    // #1 owns D02 layout; #6 chooses exactly one implementation per effect.
    public static IReadOnlyList<E05WowOption> Resolve(
        IReadOnlyCollection<string> approvedEffectIds, bool hostEventBridgeVerified,
        bool eco, bool reducedMotion)
    {
        var ids = new[] { "orbit-evidence", "live-aura", "cinematic-reveal",
            "command-focus", "stream-pulse", "action-ack", "source-trust" };
        return ids.Select(x => new E05WowOption(x, "E01/E06", "PR9+PR14+PR15 REVIEW",
            hostEventBridgeVerified && !eco && !reducedMotion &&
            approvedEffectIds.Contains(x),
            !hostEventBridgeVerified ? "EVENT_BRIDGE_UNVERIFIED" :
            eco || reducedMotion ? "MOTION_DISABLED" :
            !approvedEffectIds.Contains(x) ? "NOT_DESIGN_APPROVED" : "OPTIONAL"))
            .ToArray();
    }
}