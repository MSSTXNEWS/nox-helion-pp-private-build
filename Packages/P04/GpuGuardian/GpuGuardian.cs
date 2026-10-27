using System.Diagnostics;
using System.Globalization;
using System.Text.Json.Serialization;

namespace NoxP04.GpuGuardian;

/// <summary>A truthful NVIDIA telemetry sample. Unavailable sensors remain null.</summary>
public sealed record GpuTelemetrySample(
    DateTimeOffset TimestampUtc,
    string State,
    int? Index,
    string? Name,
    string? Uuid,
    double? UtilizationPercent,
    long? MemoryUsedMiB,
    long? MemoryTotalMiB,
    double? TemperatureC,
    string Source,
    string? ErrorCode);

/// <summary>V3 event shape consumed by the P05 report projection.</summary>
public sealed record GpuGuardianEvent(
    [property: JsonPropertyName("schema")] string Schema,
    [property: JsonPropertyName("run_id")] string RunId,
    [property: JsonPropertyName("event_id")] string EventId,
    [property: JsonPropertyName("event_type")] string EventType,
    [property: JsonPropertyName("task_id")] string TaskId,
    [property: JsonPropertyName("package_id")] string PackageId,
    [property: JsonPropertyName("action_id")] string ActionId,
    [property: JsonPropertyName("timestamp_utc")] DateTimeOffset TimestampUtc,
    [property: JsonPropertyName("state")] string State,
    [property: JsonPropertyName("source")] string Source,
    [property: JsonPropertyName("message")] string Message,
    [property: JsonPropertyName("numerator")] long? Numerator,
    [property: JsonPropertyName("denominator")] long? Denominator,
    [property: JsonPropertyName("evidence_verified")] bool EvidenceVerified,
    [property: JsonPropertyName("event_sequence")] long? EventSequence = null,
    [property: JsonPropertyName("metric_name")] string? MetricName = null,
    [property: JsonPropertyName("metric_value")] double? MetricValue = null,
    [property: JsonPropertyName("temperature_c")] double? TemperatureC = null,
    [property: JsonPropertyName("gpu_utilization_percent")] double? GpuUtilizationPercent = null,
    [property: JsonPropertyName("memory_used_mib")] long? MemoryUsedMiB = null,
    [property: JsonPropertyName("memory_total_mib")] long? MemoryTotalMiB = null,
    [property: JsonPropertyName("gpu_index")] long? GpuIndex = null,
    [property: JsonPropertyName("gpu_name")] string? GpuName = null,
    [property: JsonPropertyName("error_code")] string? ErrorCode = null);

public enum GpuMode { ECO, BALANCED, INTENSIVE }

/// <summary>
/// Scheduling policy only. It adjusts cooperative queue pacing and thermal
/// polling; it does not claim to cap GPU power, clocks, fans, or utilization.
/// </summary>
public sealed record GpuModePolicy(
    TimeSpan QueueStartDelay,
    TimeSpan TelemetryInterval,
    double ThermalStopC,
    int MaximumConcurrentJobs)
{
    public static GpuModePolicy For(GpuMode mode) => mode switch
    {
        GpuMode.ECO => new(TimeSpan.FromMilliseconds(350), TimeSpan.FromSeconds(3), 80.0, 1),
        GpuMode.BALANCED => new(TimeSpan.FromMilliseconds(80), TimeSpan.FromSeconds(5), 83.0, 1),
        GpuMode.INTENSIVE => new(TimeSpan.Zero, TimeSpan.FromSeconds(3), 85.0, 1),
        _ => throw new ArgumentOutOfRangeException(nameof(mode))
    };
}

/// <summary>
/// Windows-first NVIDIA telemetry reader. It queries the vendor's local
/// nvidia-smi utility and never synthesizes missing sensor values.
/// </summary>
public sealed class GpuGuardian
{
    private const string EventSchema = "NOX-INSTALLER-EVENT-v3";
    private const int MaximumOutputCharacters = 64 * 1024;
    private readonly string? _nvidiaSmiPath;
    private readonly string _runId;
    private long _eventSequence;

    public GpuGuardian(string? runId = null, string? nvidiaSmiPath = null)
    {
        _runId = string.IsNullOrWhiteSpace(runId) ? Guid.NewGuid().ToString("N") : runId;
        _nvidiaSmiPath = ResolveNvidiaSmi(nvidiaSmiPath);
    }

    public event Action<GpuGuardianEvent>? EventRaised;

    public async Task<IReadOnlyList<GpuTelemetrySample>> ReadNvidiaAsync(
        string taskId,
        CancellationToken cancellationToken = default)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(taskId);
        if (!OperatingSystem.IsWindows() || _nvidiaSmiPath is null)
        {
            var unavailable = Unavailable("NVIDIA_TELEMETRY_UNAVAILABLE");
            EmitSample(taskId, unavailable);
            return [unavailable];
        }

        using var process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = _nvidiaSmiPath,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                ArgumentList =
                {
                    "--query-gpu=index,name,uuid,utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits"
                }
            }
        };

        try
        {
            if (!process.Start())
            {
                var failed = Unavailable("NVIDIA_QUERY_START_FAILED");
                EmitSample(taskId, failed);
                return [failed];
            }

            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            timeout.CancelAfter(TimeSpan.FromSeconds(5));
            var stdout = ReadBoundedAsync(process.StandardOutput, MaximumOutputCharacters, timeout.Token);
            var stderr = ReadBoundedAsync(process.StandardError, 8 * 1024, timeout.Token);
            await process.WaitForExitAsync(timeout.Token).ConfigureAwait(false);
            var output = await stdout.ConfigureAwait(false);
            _ = await stderr.ConfigureAwait(false); // Vendor stderr is deliberately not exposed.
            if (process.ExitCode != 0 || output.Length == 0)
            {
                var failed = Unavailable("NVIDIA_QUERY_FAILED");
                EmitSample(taskId, failed);
                return [failed];
            }

            var samples = new List<GpuTelemetrySample>();
            foreach (var line in output.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
            {
                var fields = ParseCsv(line);
                if (fields.Count != 7)
                {
                    samples.Add(Unavailable("NVIDIA_SAMPLE_INVALID"));
                    continue;
                }

                var index = ParseInt(fields[0]);
                var name = ParseText(fields[1]);
                var uuid = ParseText(fields[2]);
                var utilization = ParseDouble(fields[3]);
                var memoryUsed = ParseLong(fields[4]);
                var memoryTotal = ParseLong(fields[5]);
                var temperature = ParseDouble(fields[6]);
                var valid = index is >= 0 && name is not null && uuid is not null &&
                    InRange(utilization, 0, 100) &&
                    memoryUsed is >= 0 && memoryTotal is > 0 && memoryUsed <= memoryTotal &&
                    InRange(temperature, 0, 150);

                var sample = valid
                    ? new GpuTelemetrySample(DateTimeOffset.UtcNow, "READY", index, name, uuid,
                        utilization, memoryUsed, memoryTotal, temperature, "nvidia-smi", null)
                    : Unavailable("NVIDIA_SAMPLE_INVALID");
                samples.Add(sample);
            }

            if (samples.Count == 0) samples.Add(Unavailable("NVIDIA_SAMPLE_UNAVAILABLE"));
            foreach (var sample in samples) EmitSample(taskId, sample);
            return samples;
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            TryKill(process);
            throw;
        }
        catch (OperationCanceledException)
        {
            TryKill(process);
            var timeout = Unavailable("NVIDIA_QUERY_TIMEOUT");
            EmitSample(taskId, timeout);
            return [timeout];
        }
        catch (Exception ex) when (ex is IOException or InvalidOperationException or System.ComponentModel.Win32Exception)
        {
            TryKill(process);
            var failed = Unavailable("NVIDIA_QUERY_FAILED");
            EmitSample(taskId, failed);
            return [failed];
        }
    }

    public static string? ThermalHoldReason(GpuTelemetrySample sample, double thresholdC)
    {
        ArgumentNullException.ThrowIfNull(sample);
        if (sample.State != "READY" || sample.TemperatureC is null)
            return "GPU_TEMPERATURE_UNAVAILABLE";
        if (!double.IsFinite(thresholdC) || thresholdC is < 50 or > 95)
            throw new ArgumentOutOfRangeException(nameof(thresholdC));
        return sample.TemperatureC >= thresholdC ? "GPU_TEMPERATURE_LIMIT_EXCEEDED" : null;
    }

    private void EmitSample(string taskId, GpuTelemetrySample sample)
    {
        var message = sample.State == "READY"
            ? $"NVIDIA telemetry sampled for GPU {sample.Index}."
            : "NVIDIA telemetry is unavailable or invalid.";
        EventRaised?.Invoke(new GpuGuardianEvent(
            EventSchema, _runId, Guid.NewGuid().ToString("N"), "gpu.sample", taskId,
            "P04", "gpu_sample", sample.TimestampUtc, sample.State, sample.Source,
            message, sample.UtilizationPercent.HasValue ? (long?)Math.Round(sample.UtilizationPercent.Value) : null,
            sample.UtilizationPercent.HasValue ? 100L : null, false,
            Interlocked.Increment(ref _eventSequence), TemperatureC: sample.TemperatureC,
            GpuUtilizationPercent: sample.UtilizationPercent, MemoryUsedMiB: sample.MemoryUsedMiB,
            MemoryTotalMiB: sample.MemoryTotalMiB, GpuIndex: sample.Index, GpuName: sample.Name,
            ErrorCode: sample.ErrorCode));
    }

    internal void EmitWorker(string workerId, string eventType, string state, string message) =>
        EventRaised?.Invoke(new GpuGuardianEvent(
            EventSchema, _runId, Guid.NewGuid().ToString("N"), eventType, workerId,
            "P04", "gpu_worker", DateTimeOffset.UtcNow, state, "P04.GpuGuardian",
            message, null, null, false, Interlocked.Increment(ref _eventSequence)));

    private static GpuTelemetrySample Unavailable(string code) =>
        new(DateTimeOffset.UtcNow, "N_D", null, null, null, null, null, null,
            null, "nvidia-smi", code);

    private static async Task<string> ReadBoundedAsync(StreamReader reader, int maximumCharacters, CancellationToken token)
    {
        var buffer = new char[2048];
        var result = new System.Text.StringBuilder();
        while (true)
        {
            var read = await reader.ReadAsync(buffer.AsMemory(), token).ConfigureAwait(false);
            if (read == 0) return result.ToString();
            if (result.Length + read > maximumCharacters)
                throw new IOException("NVIDIA telemetry output exceeded its bound.");
            result.Append(buffer, 0, read);
        }
    }

    private static string? ResolveNvidiaSmi(string? explicitPath)
    {
        if (!OperatingSystem.IsWindows()) return null;
        if (!string.IsNullOrWhiteSpace(explicitPath))
            return Path.IsPathFullyQualified(explicitPath) && File.Exists(explicitPath)
                ? Path.GetFullPath(explicitPath)
                : null;

        var programFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        var candidates = new List<string>();
        if (!string.IsNullOrWhiteSpace(programFiles))
            candidates.Add(Path.Combine(programFiles, "NVIDIA Corporation", "NVSMI", "nvidia-smi.exe"));
        var systemRoot = Environment.GetFolderPath(Environment.SpecialFolder.Windows);
        if (!string.IsNullOrWhiteSpace(systemRoot))
            candidates.Add(Path.Combine(systemRoot, "System32", "nvidia-smi.exe"));
        foreach (var entry in (Environment.GetEnvironmentVariable("PATH") ?? string.Empty)
                     .Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            if (Path.IsPathFullyQualified(entry)) candidates.Add(Path.Combine(entry, "nvidia-smi.exe"));
        }
        return candidates.FirstOrDefault(File.Exists);
    }

    private static List<string> ParseCsv(string line)
    {
        var fields = new List<string>();
        var current = new System.Text.StringBuilder();
        var quoted = false;
        for (var i = 0; i < line.Length; i++)
        {
            var ch = line[i];
            if (ch == '"')
            {
                if (quoted && i + 1 < line.Length && line[i + 1] == '"')
                {
                    current.Append('"');
                    i++;
                }
                else quoted = !quoted;
            }
            else if (ch == ',' && !quoted)
            {
                fields.Add(current.ToString().Trim());
                current.Clear();
            }
            else current.Append(ch);
        }
        fields.Add(current.ToString().Trim());
        return fields;
    }

    private static string? ParseText(string value) =>
        string.IsNullOrWhiteSpace(value) || value.Equals("N/A", StringComparison.OrdinalIgnoreCase) ? null : value;
    private static int? ParseInt(string value) => int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out var n) ? n : null;
    private static long? ParseLong(string value) => long.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out var n) ? n : null;
    private static double? ParseDouble(string value) =>
        double.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out var n) && double.IsFinite(n) ? n : null;
    private static bool InRange(double? value, double min, double max) => value.HasValue && value.Value >= min && value.Value <= max;

    private static void TryKill(Process process)
    {
        try { if (!process.HasExited) process.Kill(entireProcessTree: true); }
        catch (InvalidOperationException) { }
        catch (System.ComponentModel.Win32Exception) { }
    }
}

/// <summary>Cooperative control contract for a worker started by this guardian.</summary>
public interface IGpuWorkerControl
{
    Task<bool> PauseAsync(CancellationToken cancellationToken);
    Task<bool> ResumeAsync(CancellationToken cancellationToken);
    Task<bool> RequestStopAsync(CancellationToken cancellationToken);
}

/// <summary>
/// Serializes GPU work and applies cooperative ECO/BALANCED/INTENSIVE pacing.
/// It queues work in-process; it does not alter hardware power settings.
/// </summary>
public sealed class GpuWorkQueue : IDisposable
{
    private readonly SemaphoreSlim _singleGpuSlot = new(1, 1);
    private int _disposed;

    public async Task<T> RunAsync<T>(GpuMode mode, Func<CancellationToken, Task<T>> operation,
        CancellationToken cancellationToken = default)
    {
        ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposed) != 0, this);
        ArgumentNullException.ThrowIfNull(operation);
        var policy = GpuModePolicy.For(mode);
        await _singleGpuSlot.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            ObjectDisposedException.ThrowIf(Volatile.Read(ref _disposed) != 0, this);
            if (policy.QueueStartDelay > TimeSpan.Zero)
                await Task.Delay(policy.QueueStartDelay, cancellationToken).ConfigureAwait(false);
            return await operation(cancellationToken).ConfigureAwait(false);
        }
        finally { _singleGpuSlot.Release(); }
    }

    public void Dispose()
    {
        // Do not dispose the semaphore while a queued/running operation still
        // owns it: RunAsync must always be able to Release from its finally.
        // SemaphoreSlim allocates no kernel handle unless WaitHandle is used.
        Interlocked.Exchange(ref _disposed, 1);
    }
}

/// <summary>Handle for only the child process created by GpuGuardian.</summary>
public sealed class ManagedGpuWorker : IAsyncDisposable
{
    private readonly Process _process;
    private readonly IGpuWorkerControl _control;
    private readonly Action<string, string, string> _emit;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private int _disposed;

    internal ManagedGpuWorker(string workerId, Process process, IGpuWorkerControl control,
        Action<string, string, string> emit)
    {
        WorkerId = workerId;
        _process = process;
        _control = control;
        _emit = emit;
    }

    public string WorkerId { get; }
    public int ProcessId => _process.Id;
    public bool HasExited => _process.HasExited;

    public async Task<bool> PauseAsync(CancellationToken cancellationToken = default) =>
        await InvokeControlAsync("PAUSED", "PauseAsync", cancellationToken).ConfigureAwait(false);

    public async Task<bool> ResumeAsync(CancellationToken cancellationToken = default) =>
        await InvokeControlAsync("RUNNING", "ResumeAsync", cancellationToken).ConfigureAwait(false);

    public async Task<bool> StopAsync(TimeSpan? timeout = null, CancellationToken cancellationToken = default)
    {
        ThrowIfDisposed();
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (_process.HasExited) return true;
            var acknowledged = await _control.RequestStopAsync(cancellationToken).ConfigureAwait(false);
            if (!acknowledged)
            {
                _emit("task.progress", "HOLD", "Worker did not acknowledge cooperative STOP.");
                return false;
            }
            try
            {
                await _process.WaitForExitAsync(cancellationToken)
                    .WaitAsync(timeout ?? TimeSpan.FromSeconds(30), cancellationToken).ConfigureAwait(false);
                _emit("model.stopped", "STOPPED", "Managed worker exited after STOP acknowledgement.");
                return true;
            }
            catch (TimeoutException)
            {
                _emit("task.progress", "HOLD", "Managed worker did not exit before timeout; no force kill was issued.");
                return false;
            }
        }
        finally { _gate.Release(); }
    }

    private async Task<bool> InvokeControlAsync(string state, string method, CancellationToken token)
    {
        ThrowIfDisposed();
        await _gate.WaitAsync(token).ConfigureAwait(false);
        try
        {
            if (_process.HasExited) return false;
            var acknowledged = method == "PauseAsync"
                ? await _control.PauseAsync(token).ConfigureAwait(false)
                : await _control.ResumeAsync(token).ConfigureAwait(false);
            _emit("task.progress", acknowledged ? state : "HOLD",
                acknowledged ? $"Worker acknowledged {state}." : $"Worker did not acknowledge {state}.");
            return acknowledged;
        }
        finally { _gate.Release(); }
    }

    private void ThrowIfDisposed()
    {
        if (Volatile.Read(ref _disposed) != 0) throw new ObjectDisposedException(nameof(ManagedGpuWorker));
    }

    public ValueTask DisposeAsync()
    {
        if (Interlocked.Exchange(ref _disposed, 1) == 0)
        {
            _process.Dispose();
            _gate.Dispose();
        }
        return ValueTask.CompletedTask;
    }
}

public static class GpuWorkerLauncher
{
    public static ManagedGpuWorker Start(GpuGuardian guardian, string workerId,
        ProcessStartInfo startInfo, IGpuWorkerControl control)
    {
        ArgumentNullException.ThrowIfNull(guardian);
        ArgumentException.ThrowIfNullOrWhiteSpace(workerId);
        ArgumentNullException.ThrowIfNull(startInfo);
        ArgumentNullException.ThrowIfNull(control);
        if (!OperatingSystem.IsWindows()) throw new PlatformNotSupportedException("NOX managed GPU workers require Windows.");
        if (!Path.IsPathFullyQualified(startInfo.FileName) || startInfo.UseShellExecute ||
            string.IsNullOrWhiteSpace(startInfo.WorkingDirectory) || !Path.IsPathFullyQualified(startInfo.WorkingDirectory))
            throw new ArgumentException("Worker executable and working directory must be absolute; shell launch is forbidden.", nameof(startInfo));

        var process = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
        if (!process.Start())
        {
            process.Dispose();
            throw new InvalidOperationException("Managed GPU worker did not start.");
        }
        guardian.EmitWorker(workerId, "task.started", "RUNNING", "NOX-managed GPU worker started.");
        return new ManagedGpuWorker(workerId, process, control,
            (eventType, state, message) => guardian.EmitWorker(workerId, eventType, state, message));
    }
}
