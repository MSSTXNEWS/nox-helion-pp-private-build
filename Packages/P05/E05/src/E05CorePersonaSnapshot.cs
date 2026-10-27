using System;
using System.Collections.Generic;
using System.Linq;

namespace NoxHelion.E05;

public sealed record E05CorePersonaSnapshot(double? CenterPercent,
    IReadOnlyList<CoreProof> CoreIds, IReadOnlyList<PersonaProof> Personas,
    string Status, DateTimeOffset CapturedUtc);

public static class E05CorePersonaProjection
{
    // #1/#6 pass the eight original CoreIDs and five actual Persona IDs.
    // We do not invent names, scores, personalities, or learned abilities.
    public static E05CorePersonaSnapshot Project(IReadOnlyList<string> approvedCoreIds,
        IReadOnlyList<string> approvedPersonaIds, IReadOnlyList<CoreProof> sourceCores,
        IReadOnlyList<PersonaProof> sourcePersonas, DateTimeOffset now)
    {
        bool approved = Unique(approvedCoreIds, 8) && Unique(approvedPersonaIds, 5);
        bool exactCores = approved && sourceCores.Count == 8 &&
            approvedCoreIds.ToHashSet(StringComparer.Ordinal).SetEquals(
                sourceCores.Select(c => c.CoreId));
        bool exactPersonas = approved && sourcePersonas.Count == 5 &&
            approvedPersonaIds.ToHashSet(StringComparer.Ordinal).SetEquals(
                sourcePersonas.Select(p => p.PersonaId));
        var safeCores = exactCores ? sourceCores.Select(c => c.MeasuredAt is not null &&
            c.MeasuredAt <= now && now - c.MeasuredAt <= TimeSpan.FromMinutes(5)
                ? c : c with { Percent = null, Status = "N_D", ReceiptId = null }).ToArray()
            : Array.Empty<CoreProof>();
        var safePersonas = exactPersonas ? sourcePersonas.Select(p => p.ObservedAt is not null &&
            p.ObservedAt <= now && now - p.ObservedAt <= TimeSpan.FromMinutes(5)
                ? p : p with { Status = "OFFLINE" }).ToArray()
            : Array.Empty<PersonaProof>();
        var value = ProgressMath.CoreAverage(safeCores);
        var state = value.HasValue && ProgressMath.PersonasValid(safePersonas)
            ? "VERIFIED" : "N_D";
        return new(value, safeCores, safePersonas, state, now);
    }
    private static bool Unique(IReadOnlyList<string> items, int expected) =>
        items.Count == expected && items.All(x => !string.IsNullOrWhiteSpace(x)) &&
        items.Distinct(StringComparer.Ordinal).Count() == expected;
}