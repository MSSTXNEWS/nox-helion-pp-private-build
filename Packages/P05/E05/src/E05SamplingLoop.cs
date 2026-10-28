using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace NoxHelion.E05;

// The single E06 host starts and stops this existing sampling loop. It does not
// own a second bus, log, sensor cache, downloader or background service.
public sealed class E05SamplingLoop
{
    private readonly E05SensorPublisher? legacyPublisher;
    private readonly IE05HostEventV3Port? canonicalHost;
    private readonly IReadOnlyList<ISensorProvider> providers;
    private readonly Action<E05HardwareFrame>? onVerifiedFrame;
    private readonly TimeSpan interval;

    // ABI/source compatibility: legacy callers still fail closed because the
    // legacy telemetry.snapshot event is NOT part of canonical events.v3.
    public E05SamplingLoop(E05SensorPublisher publisher, TimeSpan interval)
    {
        legacyPublisher = publisher ?? throw new ArgumentNullException(nameof(publisher));
        providers = Array.Empty<ISensorProvider>();
        this.interval = ValidInterval(interval);
    }

    // E06 owns canonical EventV3Bridge and the real installed sensor providers.
    // CPU, temperature, VRAM stay in the read-only host frame. Only gpu.sample
    // may be sent to the existing approved events.v3 writer.
    public E05SamplingLoop(IE05HostEventV3Port canonicalHost,
        IReadOnlyList<ISensorProvider> installedProviders, TimeSpan interval,
        Action<E05HardwareFrame>? onVerifiedFrame = null)
    {
        this.canonicalHost = canonicalHost ??
            throw new ArgumentNullException(nameof(canonicalHost));
        providers = installedProviders ??
            throw new ArgumentNullException(nameof(installedProviders));
        this.onVerifiedFrame = onVerifiedFrame;
        this.interval = ValidInterval(interval);
    }

    private static TimeSpan ValidInterval(TimeSpan value) =>
        value >= TimeSpan.FromSeconds(2) && value <= TimeSpan.FromHours(1)
            ? value : throw new ArgumentOutOfRangeException(nameof(value));

    // Host can request ONE deterministic sample, without starting a timer.
    // HOST_ACCEPTED is a host ACK only; it is not acceptance/QA or Drive readback.
    public async ValueTask<E05HostPublishReceipt> PollVerifiedOnceAsync(
        string runId, CancellationToken stop)
    {
        stop.ThrowIfCancellationRequested();
        if (string.IsNullOrWhiteSpace(runId) || runId.Length > 160)
            return new(runId ?? "", "HOLD_INVALID_RUNID", null);
        if (canonicalHost is null)
            return new(runId, "HOLD_CANONICAL_HOST_UNBOUND", null);

        var at = DateTimeOffset.UtcNow;
        var frame = E05HostTelemetryFacade.ReadVerified(runId, providers, at, stop);
        stop.ThrowIfCancellationRequested();
        onVerifiedFrame?.Invoke(frame); // Existing owner host/UI subscription, never a new bus.
        stop.ThrowIfCancellationRequested();
        return await E05HostTelemetryFacade.PublishGpuAsync(
            canonicalHost, frame, DateTimeOffset.UtcNow, stop).ConfigureAwait(false);
    }

    public async Task RunAsync(string runId, CancellationToken stop)
    {
        if (string.IsNullOrWhiteSpace(runId)) throw new ArgumentException("RunID", nameof(runId));
        if (legacyPublisher is not null)
        {
            // Preserves the pre-existing intentional fail-closed behavior.
            await legacyPublisher.PollOnceAsync(runId, stop).ConfigureAwait(false);
            return;
        }
        await PollVerifiedOnceAsync(runId, stop).ConfigureAwait(false);
        using var timer = new PeriodicTimer(interval);
        while (await timer.WaitForNextTickAsync(stop).ConfigureAwait(false))
            await PollVerifiedOnceAsync(runId, stop).ConfigureAwait(false);
    }
}
