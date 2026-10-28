using System;
using System.Collections.Generic;
using System.Threading;

namespace NoxHelion.E05;

public sealed record E05HostState(E05HardwareFrame Hardware,
    ReadinessSnapshot Readiness, E05ReadOnlySpace Space);

public static class E05HostStateAdapter
{
    public static E05HostState Capture(string runId, DateTimeOffset now,
        IEnumerable<ISensorProvider> providers,
        IReadOnlyList<E05SealedLane>? lanes, IE05ReceiptVerifier? verifier,
        IReadOnlyList<FeedResult>? feeds,
        IReadOnlyDictionary<string, ApprovedFeed>? approved,
        string e06Gate, string e07Gate, CancellationToken stop)
    {
        stop.ThrowIfCancellationRequested();
        if (string.IsNullOrWhiteSpace(runId) || runId.Length > 160)
            throw new ArgumentException("RunID required", nameof(runId));
        var hardware = E05HostTelemetryFacade.ReadVerified(runId,
            providers ?? Array.Empty<ISensorProvider>(), now, stop);
        var readiness = E05VerifiedReadiness.Project(runId, now,
            lanes, verifier, e06Gate, e07Gate);
        var space = E05ApprovedSpace.ProjectVerified(runId, now, feeds,
            approved, hardware, readiness, lanes, verifier);
        return new E05HostState(hardware, readiness, space);
    }
}
