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
    long? EventSequence,
    string State,
    string Source,
    string Message,
    long? Numerator,
    long? Denominator,
    string? MetricName,
    double? MetricValue,
    string Category,
    bool ProducerClaimedEvidenceVerified,
    bool EvidenceVerified,
    double? TemperatureC,
    double? GpuUtilizationPercent,
    long? MemoryUsedMiB,
    long? MemoryTotalMiB,
    long? GpuIndex,
    string? GpuName,
    string? ErrorCode);

/// <summary>Streams NOX-INSTALLER-EVENT-v3 NDJSON into a safe report view.</summary>
public static partial class InstallerRunReport
{
    public const string EventSchema = "NOX-INSTALLER-EVENT-v3";
    public const int MaximumLineBytes = 256 * 1024;
    private const int MaximumEvents = 1_000_000;
    private const int ReadBufferBytes = 16 * 1024;
    private static readonly UTF8Encoding StrictUtf8 = new(false, true);
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
        var lineNumber = 0L;
        await foreach (var boundedLine in ReadBoundedUtf8LinesAsync(input, cancellationToken).ConfigureAwait(false))
        {
            cancellationToken.ThrowIfCancellationRequested();
            lineNumber++;
            if (lineNumber > MaximumEvents)
            {
                onInvalidLine?.Invoke(lineNumber, "EVENT_COUNT_LIMIT_REACHED");
                yield break;
            }
            if (boundedLine.TooLarge)
            {
                onInvalidLine?.Invoke(lineNumber, "EVENT_LINE_TOO_LARGE");
                continue;
            }
            if (boundedLine.InvalidUtf8)
            {
                onInvalidLine?.Invoke(lineNumber, "EVENT_INVALID_UTF8");
                continue;
            }
            var line = boundedLine.Text ?? string.Empty;
            if (line.Length == 0) continue;

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

    private readonly record struct BoundedLine(string? Text, bool TooLarge, bool InvalidUtf8);

    /// <summary>
    /// Reads fixed-size byte chunks and caps each line before decoding it. This
    /// prevents ReadLineAsync from allocating an unbounded string for a hostile
    /// or corrupted event stream.
    /// </summary>
    private static async IAsyncEnumerable<BoundedLine> ReadBoundedUtf8LinesAsync(
        Stream input,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken)
    {
        var readBuffer = new byte[ReadBufferBytes];
        var lineBuffer = new byte[MaximumLineBytes + 1]; // extra byte permits CRLF normalization
        var lineLength = 0;
        var tooLarge = false;
        while (true)
        {
            var read = await input.ReadAsync(readBuffer.AsMemory(), cancellationToken).ConfigureAwait(false);
            if (read == 0) break;
            var segmentStart = 0;
            for (var index = 0; index < read; index++)
            {
                if (readBuffer[index] != (byte)'\n') continue;
                AppendSegment(readBuffer, segmentStart, index - segmentStart, lineBuffer, ref lineLength, ref tooLarge);
                yield return DecodeBoundedLine(lineBuffer, lineLength, tooLarge);
                lineLength = 0;
                tooLarge = false;
                segmentStart = index + 1;
            }
            if (segmentStart < read)
                AppendSegment(readBuffer, segmentStart, read - segmentStart, lineBuffer, ref lineLength, ref tooLarge);
        }

        if (lineLength > 0 || tooLarge)
            yield return DecodeBoundedLine(lineBuffer, lineLength, tooLarge);
    }

    private static void AppendSegment(byte[] source, int offset, int count, byte[] lineBuffer,
        ref int lineLength, ref bool tooLarge)
    {
        if (tooLarge) return;
        if (lineLength + count > lineBuffer.Length)
        {
            tooLarge = true;
            return;
        }
        Buffer.BlockCopy(source, offset, lineBuffer, lineLength, count);
        lineLength += count;
    }

    private static BoundedLine DecodeBoundedLine(byte[] lineBuffer, int lineLength, bool tooLarge)
    {
        if (tooLarge) return new BoundedLine(null, true, false);
        if (lineLength > 0 && lineBuffer[lineLength - 1] == (byte)'\r') lineLength--;
        if (lineLength > MaximumLineBytes) return new BoundedLine(null, true, false);
        try { return new BoundedLine(StrictUtf8.GetString(lineBuffer, 0, lineLength), false, false); }
        catch (System.Text.DecoderFallbackException) { return new BoundedLine(null, false, true); }
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
        if ((eventType is "training.step" or "checkpoint.saved" or "model.stopped" or "gpu.sample") && packageId != "P04")
            throw new InvalidDataException("EVENT_PACKAGE_MISMATCH");
        if (!root.TryGetProperty("timestamp_utc", out var timestampElement) || timestampElement.ValueKind != JsonValueKind.String ||
            timestampElement.GetString() is not string timestampText || !timestampText.Contains('T') ||
            !DateTimeOffset.TryParse(timestampText, CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out var timestamp))
            throw new InvalidDataException("EVENT_TIMESTAMP_INVALID");

        var sequence = ReadNullableNonNegativeInt64(root, "event_sequence");
        if (sequence is 0) throw new InvalidDataException("EVENT_SEQUENCE_INVALID");

        var message = root.TryGetProperty("message", out var messageElement) && messageElement.ValueKind == JsonValueKind.String
            ? Redact(messageElement.GetString() ?? string.Empty)
            : string.Empty;
        var producerClaim = root.TryGetProperty("evidence_verified", out var evidenceElement) &&
            evidenceElement.ValueKind is JsonValueKind.True or JsonValueKind.False && evidenceElement.GetBoolean();
        var numerator = ReadNullableNonNegativeInt64(root, "numerator");
        var denominator = ReadNullableNonNegativeInt64(root, "denominator");
        if (numerator.HasValue && denominator.HasValue && numerator.Value > denominator.Value)
            throw new InvalidDataException("EVENT_PROGRESS_RANGE_INVALID");
        string? metricName = null;
        if (root.TryGetProperty("metric_name", out var metricNameElement) && metricNameElement.ValueKind != JsonValueKind.Null)
        {
            if (metricNameElement.ValueKind != JsonValueKind.String || metricNameElement.GetString() is not string metricNameText ||
                metricNameText.Length > 64 || metricNameText.Any(char.IsControl))
                throw new InvalidDataException("EVENT_METRIC_NAME_INVALID");
            metricName = SafeToken(metricNameText, 64);
        }
        var metricValue = ReadNullableDouble(root, "metric_value", -double.MaxValue, double.MaxValue);
        var memoryUsed = ReadNullableNonNegativeInt64(root, "memory_used_mib");
        var memoryTotal = ReadNullableNonNegativeInt64(root, "memory_total_mib");
        if (memoryUsed.HasValue && memoryTotal.HasValue && memoryUsed.Value > memoryTotal.Value)
            throw new InvalidDataException("EVENT_GPU_MEMORY_RANGE_INVALID");
        var gpuIndex = ReadNullableNonNegativeInt64(root, "gpu_index");
        string? gpuNameValue = null;
        if (root.TryGetProperty("gpu_name", out var gpuName) && gpuName.ValueKind != JsonValueKind.Null)
        {
            if (gpuName.ValueKind != JsonValueKind.String || gpuName.GetString() is not string gpuNameText ||
                gpuNameText.Length > 256 || gpuNameText.Any(char.IsControl))
                throw new InvalidDataException("EVENT_GPU_NAME_INVALID");
            gpuNameValue = Redact(gpuNameText);
        }

        return new InstallerRunEvent(
            SafeToken(runId, 128), SafeToken(eventId, 128), eventType, SafeToken(taskId, 128), SafeToken(packageId, 64), SafeToken(actionId, 128), timestamp, sequence,
            SafeToken(state, 32), Redact(source), message,
            numerator, denominator, metricName, metricValue,
            Classify(eventType, actionId, metricName),
            producerClaim,
            EvidenceVerified: false,
            ReadNullableDouble(root, "temperature_c", 0, 150),
            ReadNullableDouble(root, "gpu_utilization_percent", 0, 100),
            memoryUsed, memoryTotal, gpuIndex, gpuNameValue,
            root.TryGetProperty("error_code", out var error) && error.ValueKind == JsonValueKind.String
                ? SafeIdentifier(error.GetString(), 128)
                : null);
    }

    private static string Classify(string eventType, string actionId, string? metricName)
    {
        if (metricName?.Contains("eval", StringComparison.OrdinalIgnoreCase) == true ||
            metricName?.Contains("validation", StringComparison.OrdinalIgnoreCase) == true ||
            actionId.Contains("eval", StringComparison.OrdinalIgnoreCase) ||
            actionId.Contains("validation", StringComparison.OrdinalIgnoreCase) ||
            actionId.Contains("baseline", StringComparison.OrdinalIgnoreCase)) return "evaluation";
        if (eventType == "training.step") return "training_step";
        if (eventType == "checkpoint.saved") return "checkpoint";
        if (eventType == "gpu.sample") return "gpu_telemetry";
        if (eventType == "model.stopped") return "training_stopped";
        if (eventType == "task.failed") return "task_failed";
        if (eventType == "task.completed") return "task_completed";
        if (eventType == "task.started") return "task_started";
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
