using System;
using System.Collections.Generic;
using System.IO;
using System.Globalization;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;

namespace NoxP05.Reporting;

/// <summary>
/// A bounded, redacted projection of one worker event. Producer claims are
/// retained separately from acceptance evidence; this reader never verifies a
/// checkpoint or upgrades product readiness.
/// </summary>
public sealed record InstallerRunEvent(
    string RunId,
    string EventId,
    string EventType,
    string TaskId,
    string PackageId,
    string ActionId,
    DateTimeOffset TimestampUtc,
    string State,
    string Source,
    string Message,
    long? Numerator,
    long? Denominator,
    string Category,
    bool ProducerClaimedEvidenceVerified,
    bool EvidenceVerified,
    double? TemperatureC,
    double? GpuUtilizationPercent,
    long? MemoryUsedMiB,
    long? MemoryTotalMiB,
    string? ErrorCode);

/// <summary>Streams NOX-INSTALLER-EVENT-v3 NDJSON into a safe report view.</summary>
public static partial class InstallerRunReport
{
    public const string EventSchema = "NOX-INSTALLER-EVENT-v3";
    public const int MaximumLineBytes = 256 * 1024;
    private const int MaximumEvents = 1_000_000;
    private static readonly HashSet<string> EventTypes = new(StringComparer.Ordinal)
    {
        "task.started", "task.progress", "training.step", "checkpoint.saved",
        "task.completed", "task.failed", "model.stopped", "gpu.sample"
    };

    /// <summary>
    /// Reads one event per line. Invalid or oversized lines are skipped and
    /// reported through <paramref name="onInvalidLine"/> without echoing input.
    /// </summary>
    public static async IAsyncEnumerable<InstallerRunEvent> ReadNdjsonAsync(
        Stream input,
        Action<long, string>? onInvalidLine = null,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(input);
        using var reader = new StreamReader(input, new UTF8Encoding(false, true), detectEncodingFromByteOrderMarks: false,
            bufferSize: 16 * 1024, leaveOpen: true);
        var lineNumber = 0L;
        var emitted = 0;
        while (true)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var line = await reader.ReadLineAsync(cancellationToken).ConfigureAwait(false);
            if (line is null) yield break;
            lineNumber++;
            if (line.Length == 0) continue;
            if (Encoding.UTF8.GetByteCount(line) > MaximumLineBytes)
            {
                onInvalidLine?.Invoke(lineNumber, "EVENT_LINE_TOO_LARGE");
                continue;
            }
            if (++emitted > MaximumEvents)
            {
                onInvalidLine?.Invoke(lineNumber, "EVENT_COUNT_LIMIT_REACHED");
                yield break;
            }

            InstallerRunEvent? parsed;
            try { parsed = ParseLine(line); }
            catch (Exception exception) when (exception is JsonException or InvalidDataException or FormatException or OverflowException)
            {
                onInvalidLine?.Invoke(lineNumber, "EVENT_INVALID_" + exception.GetType().Name.ToUpperInvariant());
                continue;
            }
            if (parsed is not null) yield return parsed;
        }
    }

    public static InstallerRunEvent? ParseLine(string line)
    {
        ArgumentNullException.ThrowIfNull(line);
        if (Encoding.UTF8.GetByteCount(line) > MaximumLineBytes)
            throw new InvalidDataException("EVENT_LINE_TOO_LARGE");
        using var document = JsonDocument.Parse(line, new JsonDocumentOptions { MaxDepth = 12, CommentHandling = JsonCommentHandling.Disallow });
        var root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object ||
            !TryString(root, "schema", 64, out var schema) || !string.Equals(schema, EventSchema, StringComparison.Ordinal))
            throw new InvalidDataException("EVENT_SCHEMA_INVALID");

        if (!TryString(root, "event_type", 64, out var eventType) || !EventTypes.Contains(eventType))
            throw new InvalidDataException("EVENT_TYPE_UNSUPPORTED");
        if (!TryString(root, "run_id", 128, out var runId) ||
            !TryString(root, "event_id", 128, out var eventId) ||
            !TryString(root, "task_id", 128, out var taskId) ||
            !TryString(root, "package_id", 64, out var packageId) ||
            !TryString(root, "action_id", 128, out var actionId) ||
            !TryString(root, "state", 32, out var state) ||
            !TryString(root, "source", 128, out var source))
            throw new InvalidDataException("EVENT_REQUIRED_FIELD_INVALID");
        if (!root.TryGetProperty("timestamp_utc", out var timestampElement) || timestampElement.ValueKind != JsonValueKind.String ||
            !DateTimeOffset.TryParse(timestampElement.GetString(), CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out var timestamp))
            throw new InvalidDataException("EVENT_TIMESTAMP_INVALID");

        var message = root.TryGetProperty("message", out var messageElement) && messageElement.ValueKind == JsonValueKind.String
            ? Redact(messageElement.GetString() ?? string.Empty)
            : string.Empty;
        var producerClaim = root.TryGetProperty("evidence_verified", out var evidenceElement) &&
            evidenceElement.ValueKind is JsonValueKind.True or JsonValueKind.False && evidenceElement.GetBoolean();

        return new InstallerRunEvent(
            SafeToken(runId, 128), SafeToken(eventId, 128), eventType, SafeToken(taskId, 128), SafeToken(packageId, 64), SafeToken(actionId, 128), timestamp,
            state, Redact(source), message,
            ReadNullableNonNegativeInt64(root, "numerator"), ReadNullableNonNegativeInt64(root, "denominator"),
            Classify(eventType, actionId),
            producerClaim,
            EvidenceVerified: false,
            ReadNullableDouble(root, "temperature_c", 0, 150),
            ReadNullableDouble(root, "gpu_utilization_percent", 0, 100),
            ReadNullableNonNegativeInt64(root, "memory_used_mib"),
            ReadNullableNonNegativeInt64(root, "memory_total_mib"),
            root.TryGetProperty("error_code", out var error) && error.ValueKind == JsonValueKind.String
                ? SafeIdentifier(error.GetString(), 128)
                : null);
    }

    private static string Classify(string eventType, string actionId)
    {
        if (eventType == "training.step") return "training_step";
        if (eventType == "checkpoint.saved") return "checkpoint";
        if (eventType == "gpu.sample") return "gpu_telemetry";
        if (eventType == "model.stopped") return "training_stopped";
        if (eventType == "task.failed") return "task_failed";
        if (eventType == "task.completed") return "task_completed";
        if (eventType == "task.started") return "task_started";
        if (actionId.Contains("eval", StringComparison.OrdinalIgnoreCase) ||
            actionId.Contains("baseline", StringComparison.OrdinalIgnoreCase)) return "evaluation";
        return "task_progress";
    }

    private static bool TryString(JsonElement root, string name, int maxLength, out string value)
    {
        value = string.Empty;
        if (!root.TryGetProperty(name, out var element) || element.ValueKind != JsonValueKind.String) return false;
        var candidate = element.GetString();
        if (string.IsNullOrWhiteSpace(candidate) || candidate.Length > maxLength || candidate.Any(char.IsControl)) return false;
        value = candidate;
        return true;
    }

    private static long? ReadNullableNonNegativeInt64(JsonElement root, string name)
    {
        if (!root.TryGetProperty(name, out var value) || value.ValueKind == JsonValueKind.Null) return null;
        if (value.ValueKind != JsonValueKind.Number || !value.TryGetInt64(out var number) || number < 0)
            throw new InvalidDataException("EVENT_INTEGER_FIELD_INVALID");
        return number;
    }

    private static double? ReadNullableDouble(JsonElement root, string name, double minimum, double maximum)
    {
        if (!root.TryGetProperty(name, out var value) || value.ValueKind == JsonValueKind.Null) return null;
        if (value.ValueKind != JsonValueKind.Number || !value.TryGetDouble(out var number) ||
            !double.IsFinite(number) || number < minimum || number > maximum)
            throw new InvalidDataException("EVENT_NUMBER_FIELD_INVALID");
        return number;
    }

    private static string? SafeIdentifier(string? input, int maximumLength)
    {
        if (string.IsNullOrWhiteSpace(input) || input.Length > maximumLength || input.Any(char.IsControl)) return null;
        return input;
    }

    private static string SafeToken(string input, int maximumLength)
    {
        if (input.Length > maximumLength || input.Any(character =>
                !(char.IsAsciiLetterOrDigit(character) || character is '.' or '_' or ':' or '-')))
            throw new InvalidDataException("EVENT_IDENTIFIER_INVALID");
        return input;
    }

    private static string Redact(string input)
    {
        var value = SecretPattern().Replace(input, "$1=[REDACTED]");
        value = QuotedWindowsPathPattern().Replace(value, "[LOCAL_PATH]");
        value = UnquotedWindowsPathPattern().Replace(value, "[LOCAL_PATH]");
        value = PosixPathPattern().Replace(value, "[LOCAL_PATH]");
        value = UrlPattern().Replace(value, "[URL]");
        value = ControlPattern().Replace(value, " ").Trim();
        return value.Length <= 512 ? value : value[..512];
    }

    [GeneratedRegex("(?i)(?<![A-Za-z0-9_])(?:\\\"|')?(authorization|proxy[_-]?authorization|x-api-key|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|token|password|secret|credential)(?:\\\"|')?\\s*[:=]\\s*(?:\\\"(?:\\\\.|[^\\\"\\\\])*\\\"|'(?:\\\\.|[^'\\\\])*'|(?:bearer\\s+)?[^\\s,;]+)", RegexOptions.CultureInvariant)]
    private static partial Regex SecretPattern();
    [GeneratedRegex("\\\"[A-Za-z]:\\\\[^\\\"\\r\\n]+\\\"", RegexOptions.CultureInvariant)]
    private static partial Regex QuotedWindowsPathPattern();
    [GeneratedRegex("(?<![A-Za-z0-9])[A-Za-z]:\\\\[^\\s<>\\\"']+", RegexOptions.CultureInvariant)]
    private static partial Regex UnquotedWindowsPathPattern();
    [GeneratedRegex("(?<![A-Za-z0-9._-])/(?:[^/\\s<>\\\"']+/)*[^/\\s<>\\\"']+", RegexOptions.CultureInvariant)]
    private static partial Regex PosixPathPattern();
    [GeneratedRegex("https?://[^\\s<>\\\"']+", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)]
    private static partial Regex UrlPattern();
    [GeneratedRegex("[\\x00-\\x1f\\x7f-\\x9f]+", RegexOptions.CultureInvariant)]
    private static partial Regex ControlPattern();
}
