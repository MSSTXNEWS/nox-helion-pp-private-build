using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace NoxHelion.E05;

// Started/stopped by the EXISTING host. No additional process or event bus.
public sealed class E05SamplingLoop
{
    private readonly E05SensorPublisher publisher;
    private readonly TimeSpan interval;

    public E05SamplingLoop(E05SensorPublisher publisher, TimeSpan interval)
    {
        this.publisher = publisher ?? throw new ArgumentNullException(nameof(publisher));
        if (interval < TimeSpan.FromSeconds(2))
            throw new ArgumentOutOfRangeException(nameof(interval), "Minimum two-second polling");
        this.interval = interval;
    }
    public async Task RunAsync(string runId, CancellationToken stop)
    {
        if (string.IsNullOrWhiteSpace(runId)) throw new ArgumentException(nameof(runId));
        // First sample may legitimately be WARMUP. Do not fake a LIVE reading.
        await publisher.PollOnceAsync(runId, stop).ConfigureAwait(false);
        using var timer = new PeriodicTimer(interval);
        while (await timer.WaitForNextTickAsync(stop).ConfigureAwait(false))
            await publisher.PollOnceAsync(runId, stop).ConfigureAwait(false);
    }
}