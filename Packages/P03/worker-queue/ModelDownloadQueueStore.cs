#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using NoxHelion.P03.WorkerCatalog;

namespace NoxHelion.P03.WorkerQueue;

public enum ModelDownloadState
{
    Pending,
    Downloading,
    Paused,
    Failed,
    Completed,
    Cancelled
}

/// <summary>
/// Persisted job state only. Network transfer and STOP/cancellation execution
/// remain the responsibility of the existing host/downloader adapter.
/// </summary>
public sealed record ModelDownloadQueueItem(
    string QueueId,
    ModelArtifactEvidence Evidence,
    ModelDownloadState State,
    int AttemptCount,
    DateTimeOffset EnqueuedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    long CompletedBytes,
    long TotalBytes,
    string? FailureCode);

/// <summary>
/// Small durable queue store with fail-closed corruption handling, idempotent
/// enqueue by exact artifact identity, monotonic byte progress and atomic replace.
/// The supplied path must be in an application-private user-data directory.
/// </summary>
public sealed class ModelDownloadQueueStore
{
    private const int CurrentSchemaVersion = 1;
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
    {
        WriteIndented = true
    };

    private readonly string _filePath;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private PersistedQueueState _state;

    private ModelDownloadQueueStore(string filePath, PersistedQueueState state)
    {
        _filePath = filePath;
        _state = state;
    }

    public static async Task<ModelDownloadQueueStore> OpenAsync(
        string filePath,
        CancellationToken cancellationToken = default)
    {
        if (string.IsNullOrWhiteSpace(filePath))
            throw new ArgumentException("A private queue file path is required.", nameof(filePath));

        var fullPath = Path.GetFullPath(filePath);
        var directory = Path.GetDirectoryName(fullPath)
            ?? throw new ArgumentException("Queue path has no parent directory.", nameof(filePath));
        Directory.CreateDirectory(directory);

        if (!File.Exists(fullPath))
            return new ModelDownloadQueueStore(fullPath, new PersistedQueueState(CurrentSchemaVersion, new List<ModelDownloadQueueItem>()));

        try
        {
            await using var stream = new FileStream(fullPath, FileMode.Open, FileAccess.Read, FileShare.Read,
                16 * 1024, FileOptions.Asynchronous | FileOptions.SequentialScan);
            var loaded = await JsonSerializer.DeserializeAsync<PersistedQueueState>(stream, JsonOptions, cancellationToken)
                .ConfigureAwait(false);
            ValidateLoadedState(loaded);
            return new ModelDownloadQueueStore(fullPath, loaded!);
        }
        catch (JsonException exception)
        {
            throw new InvalidDataException("Queue JSON is corrupt; it was not reset or overwritten.", exception);
        }
    }

    public async Task<IReadOnlyList<ModelDownloadQueueItem>> SnapshotAsync(
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            return _state.Items.ToArray();
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<ModelDownloadQueueItem> EnqueueAsync(
        ModelArtifactEvidence evidence,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(evidence);
        var failures = evidence.GetProvenanceFailures();
        if (failures.Count != 0)
            throw new InvalidOperationException("Artifact is not queue-eligible; missing evidence: " + string.Join(",", failures));

        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var existing = _state.Items.FirstOrDefault(item =>
                string.Equals(item.Evidence.ArtifactIdentity, evidence.ArtifactIdentity, StringComparison.OrdinalIgnoreCase));
            if (existing is not null)
                return existing;

            var now = DateTimeOffset.UtcNow;
            var added = new ModelDownloadQueueItem(
                Guid.NewGuid().ToString("N"), evidence, ModelDownloadState.Pending, 0, now, now, 0, 0, null);
            _state = _state with { Items = _state.Items.Append(added).ToList() };
            await PersistLockedAsync(cancellationToken).ConfigureAwait(false);
            return added;
        }
        finally
        {
            _gate.Release();
        }
    }

    /// <summary>
    /// Stores byte counters supplied by the active transfer. It does not invent
    /// percentages and rejects regressions or counters without a known total.
    /// </summary>
    public async Task<ModelDownloadQueueItem> UpdateProgressAsync(
        string queueId,
        long completedBytes,
        long totalBytes,
        CancellationToken cancellationToken = default)
    {
        if (completedBytes < 0 || totalBytes <= 0 || completedBytes > totalBytes)
            throw new ArgumentOutOfRangeException(nameof(completedBytes), "Progress must contain real, bounded byte counters.");

        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var index = FindIndex(queueId);
            var current = _state.Items[index];
            if (current.State != ModelDownloadState.Downloading)
                throw new InvalidOperationException("Progress is accepted only while the job is Downloading.");
            if (completedBytes < current.CompletedBytes || totalBytes < current.TotalBytes)
                throw new InvalidOperationException("Progress counters must be monotonic for an aggregated transfer.");

            var updated = current with
            {
                CompletedBytes = completedBytes,
                TotalBytes = totalBytes,
                UpdatedAtUtc = DateTimeOffset.UtcNow
            };
            ReplaceAt(index, updated);
            await PersistLockedAsync(cancellationToken).ConfigureAwait(false);
            return updated;
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<ModelDownloadQueueItem> TransitionAsync(
        string queueId,
        ModelDownloadState nextState,
        string? failureCode = null,
        CancellationToken cancellationToken = default)
    {
        await _gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var index = FindIndex(queueId);
            var current = _state.Items[index];
            if (!CanTransition(current.State, nextState))
                throw new InvalidOperationException($"Illegal queue transition: {current.State} -> {nextState}.");
            if (nextState == ModelDownloadState.Failed && string.IsNullOrWhiteSpace(failureCode))
                throw new ArgumentException("A stable failure code is required.", nameof(failureCode));
            if (nextState == ModelDownloadState.Completed &&
                (current.TotalBytes <= 0 || current.CompletedBytes != current.TotalBytes))
                throw new InvalidOperationException("Completion requires an exact transfer byte receipt.");

            var updated = current with
            {
                State = nextState,
                AttemptCount = nextState == ModelDownloadState.Downloading
                    ? checked(current.AttemptCount + 1)
                    : current.AttemptCount,
                FailureCode = nextState == ModelDownloadState.Failed ? failureCode : null,
                UpdatedAtUtc = DateTimeOffset.UtcNow
            };
            ReplaceAt(index, updated);
            await PersistLockedAsync(cancellationToken).ConfigureAwait(false);
            return updated;
        }
        finally
        {
            _gate.Release();
        }
    }

    private int FindIndex(string queueId)
    {
        var index = _state.Items.FindIndex(item => string.Equals(item.QueueId, queueId, StringComparison.Ordinal));
        return index >= 0 ? index : throw new KeyNotFoundException("Queue item was not found.");
    }

    private void ReplaceAt(int index, ModelDownloadQueueItem item)
    {
        var items = _state.Items.ToList();
        items[index] = item;
        _state = _state with { Items = items };
    }

    private async Task PersistLockedAsync(CancellationToken cancellationToken)
    {
        var bytes = JsonSerializer.SerializeToUtf8Bytes(_state, JsonOptions);
        var temporaryPath = _filePath + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            await using (var stream = new FileStream(temporaryPath, FileMode.CreateNew, FileAccess.Write, FileShare.None,
                16 * 1024, FileOptions.Asynchronous | FileOptions.WriteThrough))
            {
                await stream.WriteAsync(bytes.AsMemory(), cancellationToken).ConfigureAwait(false);
                await stream.FlushAsync(cancellationToken).ConfigureAwait(false);
                stream.Flush(flushToDisk: true);
            }

            // Same-directory replacement keeps the prior valid file until the new
            // complete state is durable. The directory must be on one filesystem.
            File.Move(temporaryPath, _filePath, overwrite: true);
        }
        finally
        {
            if (File.Exists(temporaryPath))
                File.Delete(temporaryPath);
        }
    }

    private static bool CanTransition(ModelDownloadState current, ModelDownloadState next) => (current, next) switch
    {
        (ModelDownloadState.Pending, ModelDownloadState.Downloading or ModelDownloadState.Cancelled) => true,
        (ModelDownloadState.Downloading, ModelDownloadState.Paused or ModelDownloadState.Failed or ModelDownloadState.Completed or ModelDownloadState.Cancelled) => true,
        (ModelDownloadState.Paused, ModelDownloadState.Downloading or ModelDownloadState.Cancelled) => true,
        (ModelDownloadState.Failed, ModelDownloadState.Pending or ModelDownloadState.Cancelled) => true,
        _ => false
    };

    private static void ValidateLoadedState(PersistedQueueState? state)
    {
        if (state is null || state.SchemaVersion != CurrentSchemaVersion || state.Items is null)
            throw new InvalidDataException("Queue schema/version is not recognized; existing bytes were preserved.");
        if (state.Items.Any(item => item is null || string.IsNullOrWhiteSpace(item.QueueId)) ||
            state.Items.Select(item => item.QueueId).Distinct(StringComparer.Ordinal).Count() != state.Items.Count)
            throw new InvalidDataException("Queue contains invalid or duplicate job identities; existing bytes were preserved.");
        if (state.Items.Any(item => item.Evidence is null || item.Evidence.GetProvenanceFailures().Count != 0))
            throw new InvalidDataException("Queue contains an artifact without complete provenance; existing bytes were preserved.");
        if (state.Items.Any(item => !Enum.IsDefined(typeof(ModelDownloadState), item.State) || item.AttemptCount < 0 ||
                                    item.CompletedBytes < 0 || item.TotalBytes < 0 ||
                                    (item.TotalBytes > 0 && item.CompletedBytes > item.TotalBytes) ||
                                    (item.State == ModelDownloadState.Completed &&
                                     (item.TotalBytes <= 0 || item.CompletedBytes != item.TotalBytes))))
            throw new InvalidDataException("Queue contains invalid state or progress; existing bytes were preserved.");
    }

    private sealed record PersistedQueueState(int SchemaVersion, List<ModelDownloadQueueItem> Items);
}
