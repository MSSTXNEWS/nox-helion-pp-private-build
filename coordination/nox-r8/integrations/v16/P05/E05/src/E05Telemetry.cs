using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;

namespace NoxHelion.E05;

public sealed record SensorPoint(string Key, double? Value, string Unit,
    string Source, DateTimeOffset? ObservedAtUtc, string Status);

public interface ISensorProvider
{
    string Name { get; }
    IReadOnlyList<SensorPoint> Read(CancellationToken cancellationToken);
}

// Windows system-wide CPU, sampled from two successive GetSystemTimes reads.
// Returns WARMUP on the first read. Never returns a fabricated initial percentage.
public sealed class WindowsCpuSensor : ISensorProvider
{
    private ulong? lastIdle, lastTotal;
    public string Name => "Windows.GetSystemTimes";

    [StructLayout(LayoutKind.Sequential)]
    private struct FileTime { public uint Low; public uint High;
        public ulong AsUInt64() => ((ulong)High << 32) | Low; }
    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetSystemTimes(out FileTime idle,
        out FileTime kernel, out FileTime user);

    public IReadOnlyList<SensorPoint> Read(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (!RuntimeInformation.IsOSPlatform(OSPlatform.Windows))
            return new[] { new SensorPoint("cpu.system.percent", null, "%", Name,
                null, "UNSUPPORTED_OS") };
        if (!GetSystemTimes(out var idle, out var kernel, out var user))
            return new[] { new SensorPoint("cpu.system.percent", null, "%", Name,
                null, "SENSOR_ERROR") };
        ulong idleValue = idle.AsUInt64();
        ulong total = kernel.AsUInt64() + user.AsUInt64();
        double? pct = null;
        if (lastTotal.HasValue && lastIdle.HasValue && total > lastTotal.Value &&
            idleValue >= lastIdle.Value)
        {
            var deltaTotal = total - lastTotal.Value;
            var deltaIdle = idleValue - lastIdle.Value;
            if (deltaIdle <= deltaTotal)
                pct = 100.0 * (1.0 - deltaIdle / (double)deltaTotal);
        }
        lastTotal = total;
        lastIdle = idleValue;
        return new[] { new SensorPoint("cpu.system.percent", pct, "%", Name,
            pct.HasValue ? DateTimeOffset.UtcNow : null,
            pct.HasValue ? "LIVE" : "WARMUP") };
    }
}

// Uses only the locally installed NVIDIA display driver's NVML library.
// No bundled SDK, no GPU requirement, no simulated fallback for other vendors.
public sealed class NvidiaNvmlSensor : ISensorProvider
{
    public string Name => "NVIDIA.NVML";
    [StructLayout(LayoutKind.Sequential)]
    private struct Utilization { public uint Gpu; public uint Memory; }
    [StructLayout(LayoutKind.Sequential)]
    private struct MemoryInfo { public ulong Total; public ulong Free; public ulong Used; }
    [DllImport("nvml.dll", EntryPoint = "nvmlInit_v2", CallingConvention = CallingConvention.Cdecl)]
    private static extern int Init();
    [DllImport("nvml.dll", EntryPoint = "nvmlShutdown", CallingConvention = CallingConvention.Cdecl)]
    private static extern int Shutdown();
    [DllImport("nvml.dll", EntryPoint = "nvmlDeviceGetHandleByIndex_v2", CallingConvention = CallingConvention.Cdecl)]
    private static extern int Device(uint index, out IntPtr handle);
    [DllImport("nvml.dll", EntryPoint = "nvmlDeviceGetUtilizationRates", CallingConvention = CallingConvention.Cdecl)]
    private static extern int Util(IntPtr handle, out Utilization rates);
    [DllImport("nvml.dll", EntryPoint = "nvmlDeviceGetMemoryInfo", CallingConvention = CallingConvention.Cdecl)]
    private static extern int Memory(IntPtr handle, out MemoryInfo info);
    [DllImport("nvml.dll", EntryPoint = "nvmlDeviceGetTemperature", CallingConvention = CallingConvention.Cdecl)]
    private static extern int Temperature(IntPtr handle, uint sensor, out uint degreesC);

    private IReadOnlyList<SensorPoint> Missing(string status) => new[] {
        new SensorPoint("gpu.percent", null, "%", Name, null, status),
        new SensorPoint("gpu.vram.used_bytes", null, "bytes", Name, null, status),
        new SensorPoint("gpu.vram.total_bytes", null, "bytes", Name, null, status),
        new SensorPoint("gpu.temperature.c", null, "°C", Name, null, status)
    };

    public IReadOnlyList<SensorPoint> Read(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (!RuntimeInformation.IsOSPlatform(OSPlatform.Windows)) return Missing("UNSUPPORTED_OS");
        try
        {
            if (Init() != 0) return Missing("PROVIDER_UNAVAILABLE");
            try
            {
                if (Device(0, out var h) != 0) return Missing("GPU_UNAVAILABLE");
                DateTimeOffset time = DateTimeOffset.UtcNow;
                var okUtil = Util(h, out var u) == 0;
                var okMemory = Memory(h, out var m) == 0;
                var okTemperature = Temperature(h, 0, out var t) == 0;
                return new[] {
                    Point("gpu.percent", okUtil ? u.Gpu : null, "%", time),
                    Point("gpu.vram.used_bytes", okMemory ? (double)m.Used : null, "bytes", time),
                    Point("gpu.vram.total_bytes", okMemory ? (double)m.Total : null, "bytes", time),
                    Point("gpu.temperature.c", okTemperature ? t : null, "°C", time)
                };
            }
            finally { Shutdown(); }
        }
        catch (DllNotFoundException) { return Missing("DRIVER_NOT_INSTALLED"); }
        catch (EntryPointNotFoundException) { return Missing("NVML_INCOMPATIBLE"); }
        catch (BadImageFormatException) { return Missing("ARCHITECTURE_MISMATCH"); }
    }

    private SensorPoint Point(string key, double? value, string unit, DateTimeOffset time) =>
        new(key, value, unit, Name, value.HasValue ? time : null,
            value.HasValue ? "LIVE" : "NOT_SUPPORTED");
}

// The shared host owns events.v3. This is an adapter interface, not a second event bus.
public sealed record TelemetryEventV3(string Version, string Kind, string RunId,
    DateTimeOffset UtcTimestamp, IReadOnlyList<SensorPoint> Points);
public interface IEventV3Transport
{
    ValueTask SendAsync(TelemetryEventV3 message, CancellationToken stop);
}
public sealed class E05SensorPublisher
{
    private readonly IReadOnlyList<ISensorProvider> providers;
    private readonly IEventV3Transport hostTransport;
    public E05SensorPublisher(IReadOnlyList<ISensorProvider> providers, IEventV3Transport hostTransport)
    { this.providers = providers; this.hostTransport = hostTransport; }
    // R11 events.v3 does not define telemetry.snapshot. Host #6 must bind
    // E05CanonicalEventFactory.GpuUtilization to its existing EventV3Bridge.
    // Until that binding exists this legacy method fails closed, rather than
    // emitting a noncanonical event into the shared journal.
    public Task PollOnceAsync(string runId, CancellationToken stop)
    {
        stop.ThrowIfCancellationRequested();
        if (string.IsNullOrWhiteSpace(runId)) throw new ArgumentException("Missing RunID", nameof(runId));
        throw new NotSupportedException("HOLD: telemetry.snapshot is not an approved events.v3 event type. Use E05CanonicalEventFactory and E06-owned host bridge.");
    }
}
