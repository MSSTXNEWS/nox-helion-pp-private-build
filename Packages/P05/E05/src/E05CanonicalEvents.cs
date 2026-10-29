using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;

namespace NoxHelion.E05;

// Payload matches original R11/Contracts/events.v3.json. The host owns the
// actual EventV3Bridge and journal; this component has NO writer of its own.
public sealed record E05CanonicalEvent(
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
    [property: JsonPropertyName("evidence_verified")] bool EvidenceVerified);

public interface IE05HostEventV3Port
{
    // Implement ONLY by E06 using the existing bridge's atomic journal lock.
    ValueTask<bool> PublishAsync(E05CanonicalEvent payload, CancellationToken stop);
}

public static class E05CanonicalEventFactory
{
    public const string Schema = "NOX-INSTALLER-EVENT-v3";
    private static readonly HashSet<string> Allowed = new(StringComparer.Ordinal) {
        "task.started", "task.progress", "task.failed", "task.completed",
        "model.stopped", "gpu.sample", "training.step",
        "checkpoint.saved"
    };
    private static readonly HashSet<string> States = new(StringComparer.Ordinal) {
        "QUEUED", "RUNNING", "PAUSED", "COMPLETED", "ERROR",
        "STOPPED", "OFFLINE", "HOLD", "READY", "N_D"
    };
    public static bool IsCanonical(E05CanonicalEvent? e)
    {
        if (e is null || e.Schema != Schema || !Allowed.Contains(e.EventType) ||
            !States.Contains(e.State) || e.TimestampUtc.Offset != TimeSpan.Zero ||
            string.IsNullOrWhiteSpace(e.RunId) || e.RunId.Length > 128 ||
            string.IsNullOrWhiteSpace(e.EventId) || e.EventId.Length > 128 ||
            string.IsNullOrWhiteSpace(e.TaskId) || e.TaskId.Length > 128 ||
            e.PackageId is not ("P01" or "P02" or "P03" or "P04" or "P05" or "E06" or "E07") ||
            string.IsNullOrWhiteSpace(e.ActionId) || e.ActionId.Length > 128 ||
            string.IsNullOrWhiteSpace(e.Source) ||
            e.Source.Length > 120 || e.Message is null || e.Message.Length > 240 ||
            e.Message.Any(c => char.IsControl(c)) ||
            e.Source.Any(c => char.IsControl(c))) return false;
        // The original events.v3 schema scopes neural worker events to P04.
        // P05 may report observed hardware telemetry ONLY as an unverified
        // gpu_utilization sample; it cannot impersonate a P04 optimizer step.
        if (e.EventType is "training.step" or "checkpoint.saved" or "model.stopped")
            if (e.PackageId != "P04") return false;
        if (e.EventType == "gpu.sample" &&
            !(e.PackageId == "P04" || (e.PackageId == "P05" &&
              e.ActionId == "gpu_utilization" && e.Source == "P05.Hardware" &&
              e.State == "RUNNING" && !e.EvidenceVerified)))
            return false;
        if (e.Numerator.HasValue != e.Denominator.HasValue) return false;
        if (e.Denominator.HasValue && (e.Denominator <= 0 || e.Numerator < 0 || e.Numerator > e.Denominator)) return false;
        return true;
    }

    // A real GPU load sample may be exposed as gpu.sample. CPU/temperature/VRAM
    // have no approved event type in R11, so stay on the host's read-only DTO.
    public static E05CanonicalEvent? GpuUtilization(string runId, SensorPoint reading,
        DateTimeOffset now, string taskId = "E05-02")
    {
        if (string.IsNullOrWhiteSpace(runId) || reading.Key != "gpu.percent" ||
            reading.Status != "LIVE" || !reading.Value.HasValue ||
            !double.IsFinite(reading.Value.Value) ||
            reading.Value < 0 || reading.Value > 100 ||
            reading.ObservedAtUtc is null ||
            now - reading.ObservedAtUtc.Value < TimeSpan.Zero ||
            now - reading.ObservedAtUtc.Value > TimeSpan.FromSeconds(30)) return null;
        // Basis points from a real sampled percentage. Not an acceptance percentage.
        var numerator = (long)Math.Round(reading.Value.Value * 100,
            MidpointRounding.AwayFromZero);
        return new E05CanonicalEvent(Schema, runId, Guid.NewGuid().ToString("N"),
            "gpu.sample", taskId, "P05", "gpu_utilization",
            reading.ObservedAtUtc.Value.ToUniversalTime(), "RUNNING", "P05.Hardware",
            "GPU utilization sample", numerator, 10000, false);
    }

    public static string Serialize(E05CanonicalEvent e)
    {
        if (!IsCanonical(e)) throw new ArgumentException("Not a canonical events.v3 payload");
        return JsonSerializer.Serialize(e);
    }
}
