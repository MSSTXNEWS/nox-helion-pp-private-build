using System.Text.Json;
using System.Diagnostics;
using System.Text.RegularExpressions;

namespace Nox.P03;

public enum ModelJobKind { OllamaPull, GgufImport, SafetensorsImport }
public enum ModelJobState { Queued, Running, Cancelling, Completed, Cancelled, Failed }

public sealed record ModelJob(
    Guid Id,
    ModelJobKind Kind,
    string ModelTag,
    string? LocalPath,
    bool LicenseAcknowledged,
    string LicenseSource,
    DateTimeOffset CreatedAtUtc,
    DateTimeOffset UpdatedAtUtc,
    ModelJobState State = ModelJobState.Queued,
    int Attempts = 0,
    string? Status = null,
    long? CompletedBytes = null,
    long? TotalBytes = null,
    string? ComputedSha256 = null,
    string? Error = null,
    string? ReceiptPath = null,
    long? ExpectedLocalBytes = null,
    string? ExpectedLocalSha256 = null,
    string? RightsReceiptId = null,
    string? ExpectedOllamaDigest = null,
    string? ImmutableRevision = null,
    Guid? RetryOfJobId = null,
    P04MergedImportApproval? MergedImport = null);

public sealed class ModelDownloadQueueStore
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web) { WriteIndented = true };
    private const long MaxQueueFileBytes = 16 * 1024 * 1024;
    private static readonly Regex ShaPattern = new("^[a-fA-F0-9]{64}$", RegexOptions.Compiled);
    private static readonly Regex TagPattern = new(@"^[a-zA-Z0-9][a-zA-Z0-9._-]*(/[a-zA-Z0-9][a-zA-Z0-9._-]*)?:[a-zA-Z0-9][a-zA-Z0-9._-]*$", RegexOptions.Compiled);
    private readonly string _path;
    private readonly string _leasePath;
    private readonly SemaphoreSlim _gate = new(1, 1);

    public ModelDownloadQueueStore(string dataDirectory)
    {
        if (string.IsNullOrWhiteSpace(dataDirectory))
            throw new ArgumentException("An application-private queue directory is required.", nameof(dataDirectory));
        // Do not create or write user-data through a junction or symbolic link.
        ModelLocalAttestation.RequireNoExistingReparsePoint(dataDirectory);
        Directory.CreateDirectory(dataDirectory);
        ModelLocalAttestation.RequireNoExistingReparsePoint(dataDirectory);
        _path = Path.Combine(Path.GetFullPath(dataDirectory), "p03-model-download-queue.json");
        ModelLocalAttestation.RequireNoExistingReparsePoint(_path);
        _leasePath = _path + ".lock";
        ModelLocalAttestation.RequireNoExistingReparsePoint(_leasePath);
    }

    public async Task<IReadOnlyList<ModelJob>> ReadAsync(CancellationToken ct = default)
    {
        await _gate.WaitAsync(ct);
        try
        {
            using var lease = await AcquireFileLeaseAsync(ct);
            return await ReadCoreAsync(ct);
        }
        finally { _gate.Release(); }
    }

    public Task<ModelJob> EnqueueAsync(ModelJobKind kind, string tag, string? localPath,
        bool licenseAcknowledged, string licenseSource, CancellationToken ct = default)
    {
        if (!licenseAcknowledged) throw new InvalidOperationException("Review the model license and explicitly acknowledge it before queueing.");
        if (string.IsNullOrWhiteSpace(licenseSource) || !Uri.TryCreate(licenseSource, UriKind.Absolute, out var source)
            || source.Scheme != Uri.UriSchemeHttps)
            throw new ArgumentException("A reviewed HTTPS license/source URL is required.", nameof(licenseSource));
        // Legacy path intentionally retained for binary compatibility, never usable
        // for network transfers without a reviewed pinned artifact.
        throw new InvalidOperationException("REVIEW_REQUIRED: use EnqueueVerifiedPullAsync or EnqueueVerifiedGgufAsync.");
    }

    /// <summary>Explicitly reviewed GGUF artifact; cannot enqueue a file with unknown
    /// expected bytes/digest or missing local-rights attestation.</summary>
    public async Task<ModelJob> EnqueueVerifiedGgufAsync(string tag, string localPath,
        long expectedBytes, string expectedSha256, string rightsReceiptId,
        string licenseSource, CancellationToken ct = default)
    {
        ValidateTag(tag);
        if (expectedBytes <= 4 || !ShaPattern.IsMatch(expectedSha256 ?? string.Empty)
            || string.IsNullOrWhiteSpace(rightsReceiptId))
            throw new InvalidDataException("REVIEW_REQUIRED: GGUF expected bytes/SHA-256/rights receipt.");
        if (string.IsNullOrWhiteSpace(localPath) ||
            !string.Equals(Path.GetExtension(localPath), ".gguf", StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("GGUF path and extension required.");
        if (!Uri.TryCreate(licenseSource, UriKind.Absolute, out var uri) || uri.Scheme != Uri.UriSchemeHttps)
            throw new InvalidDataException("Reviewed HTTPS license evidence required.");
        var fullPath = Path.GetFullPath(localPath);
        ModelLocalAttestation.RequireRegularUnlinkedFile(fullPath);
        if (new FileInfo(fullPath).Length != expectedBytes)
            throw new InvalidDataException("GGUF_BYTES_DIFFER_FROM_REVIEWED_ARTIFACT");
        await _gate.WaitAsync(ct);
        try
        {
            using var lease = await AcquireFileLeaseAsync(ct);
            var jobs = (await ReadCoreAsync(ct)).ToList();
            var now = DateTimeOffset.UtcNow;
            var job = new ModelJob(Guid.NewGuid(), ModelJobKind.GgufImport, tag.Trim(), fullPath,
                true, licenseSource, now, now, ExpectedLocalBytes: expectedBytes,
                ExpectedLocalSha256: expectedSha256.ToLowerInvariant(), RightsReceiptId: rightsReceiptId);
            jobs.Add(job);
            await SaveCoreAsync(jobs, ct);
            return job;
        }
        finally { _gate.Release(); }
    }

    /// <summary>Only an authenticated, verified P04 merge can enter this queue.
    /// Unique candidate tags never replace the previously active installed model.</summary>
    public async Task<ModelJob> EnqueueVerifiedMergedAsync(P04MergedImportApproval approval,
        bool nativeConsent,CancellationToken ct=default)
    {
        if (!nativeConsent)throw new UnauthorizedAccessException("P03_NATIVE_MERGE_IMPORT_CONSENT_REQUIRED");
        approval=approval with {Directory=Path.GetFullPath(approval.Directory),TrainingReceiptPath=Path.GetFullPath(approval.TrainingReceiptPath)};
        var files=await ModelSafetensorsImport.ValidateAsync(approval,ct);
        var id=Guid.NewGuid();var tag="nox-forge-"+approval.MergedPayloadSha256[..12]+":"+id.ToString("N");
        await _gate.WaitAsync(ct);
        try {
            using var lease=await AcquireFileLeaseAsync(ct);
            var jobs=(await ReadCoreAsync(ct)).ToList();var now=DateTimeOffset.UtcNow;
            var job=new ModelJob(id,ModelJobKind.SafetensorsImport,tag,Path.GetFullPath(approval.Directory),
                true,approval.LicenseSource,now,now,ExpectedLocalBytes:files.Sum(x=>x.SizeBytes),
                ExpectedLocalSha256:approval.MergedPayloadSha256,RightsReceiptId:approval.RightsAttestationId,
                MergedImport:approval);
            jobs.Add(job);await SaveCoreAsync(jobs,ct);return job;
        } finally {_gate.Release();}
    }

    /// <summary>Queue only one exact, approved catalog artifact; family discovery alone
    /// never authorizes a network pull. The host must additionally enforce user ACL.</summary>
    public async Task<ModelJob> EnqueueVerifiedPullAsync(ModelCatalogEntry model,
        bool licenseAcknowledged, CancellationToken ct = default)
    {
        ArgumentNullException.ThrowIfNull(model);
        if (!licenseAcknowledged || !model.CanOfferOneClickPull ||
            string.IsNullOrWhiteSpace(model.ExactTag) ||
            !ShaPattern.IsMatch(model.ExpectedSha256 ?? string.Empty) ||
            !ShaPattern.IsMatch(model.ExpectedManifestDigestSha256 ?? string.Empty) ||
            string.IsNullOrWhiteSpace(model.ImmutableRevision))
            throw new InvalidOperationException("REVIEW_REQUIRED: exact artifact evidence is incomplete.");
        ValidateTag(model.ExactTag);
        var licenseUrl = model.LicenseEvidenceUri!.ToString();
        await _gate.WaitAsync(ct);
        try
        {
            using var lease = await AcquireFileLeaseAsync(ct);
            var jobs = (await ReadCoreAsync(ct)).ToList();
            var prior = jobs.FirstOrDefault(j => j.Kind == ModelJobKind.OllamaPull &&
                (j.State is ModelJobState.Queued or ModelJobState.Running or ModelJobState.Cancelling) &&
                string.Equals(j.ModelTag, model.ExactTag, StringComparison.OrdinalIgnoreCase) &&
                string.Equals(j.ExpectedOllamaDigest, model.ExpectedManifestDigestSha256, StringComparison.OrdinalIgnoreCase) &&
                string.Equals(j.ImmutableRevision, model.ImmutableRevision, StringComparison.Ordinal));
            if (prior is not null) return prior;
            var now = DateTimeOffset.UtcNow;
            var job = new ModelJob(Guid.NewGuid(), ModelJobKind.OllamaPull,
                model.ExactTag, null, true, licenseUrl, now, now,
                ExpectedOllamaDigest: model.ExpectedManifestDigestSha256!.ToLowerInvariant(),
                ImmutableRevision: model.ImmutableRevision);
            jobs.Add(job);
            await SaveCoreAsync(jobs, ct);
            return job;
        }
        finally { _gate.Release(); }
    }

    private static void ValidateTag(string? tag)
    {
        if (tag is null || tag.Length > 160 || !TagPattern.IsMatch(tag) ||
            tag.Contains("..", StringComparison.Ordinal) ||
            tag.EndsWith(":latest", StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("A reviewed non-latest model tag is required.", nameof(tag));
    }

    /// <summary>
    /// Atomic claim: only one NOX process may transition a queued job into Running.
    /// A previous Running state must never count as a successful second claim.
    /// </summary>
    public async Task<ModelJob?> TryStartQueuedAsync(Guid id, CancellationToken ct = default)
    {
        await _gate.WaitAsync(ct);
        try
        {
            using var lease = await AcquireFileLeaseAsync(ct);
            var jobs = (await ReadCoreAsync(ct)).ToList();
            var index = jobs.FindIndex(j => j.Id == id);
            if (index < 0 || jobs[index].State != ModelJobState.Queued) return null;
            var old = jobs[index];
            if (old.Kind == ModelJobKind.OllamaPull &&
                (old.ExpectedOllamaDigest is not { Length: 64 } ||
                 !ShaPattern.IsMatch(old.ExpectedOllamaDigest) ||
                 string.IsNullOrWhiteSpace(old.ImmutableRevision)))
                throw new InvalidOperationException("REVIEW_REQUIRED: unpinned Pull cannot start.");
            var claimed = old with { State = ModelJobState.Running,
                Attempts = checked(old.Attempts + 1), Status = "Starting",
                UpdatedAtUtc = DateTimeOffset.UtcNow };
            jobs[index] = claimed;
            await SaveCoreAsync(jobs, ct);
            return claimed;
        }
        finally { _gate.Release(); }
    }

    public async Task<ModelJob?> UpdateAsync(Guid id, Func<ModelJob, ModelJob> update, CancellationToken ct = default)
    {
        await _gate.WaitAsync(ct);
        try
        {
            using var lease = await AcquireFileLeaseAsync(ct);
            var jobs = (await ReadCoreAsync(ct)).ToList();
            var index = jobs.FindIndex(x => x.Id == id);
            if (index < 0) return null;
            var previous = jobs[index];
            // A terminal receipt is immutable; late events or retries must not rewrite history.
            var candidate = update(previous);
            if (previous.State is ModelJobState.Completed or ModelJobState.Cancelled or ModelJobState.Failed)
            {
                if (candidate != previous)
                    throw new InvalidOperationException("TERMINAL_MODEL_JOB_IS_IMMUTABLE");
                return previous;
            }
            var proposed = candidate with { UpdatedAtUtc = DateTimeOffset.UtcNow };
            if (previous.State != proposed.State && ((previous.State, proposed.State) switch
                {
                    (ModelJobState.Queued, ModelJobState.Running or ModelJobState.Cancelled or ModelJobState.Failed) => false,
                    (ModelJobState.Running, ModelJobState.Cancelling or ModelJobState.Cancelled or ModelJobState.Completed or ModelJobState.Failed) => false,
                    (ModelJobState.Cancelling, ModelJobState.Cancelled or ModelJobState.Failed) => false,
                    _ => true
                }))
                throw new InvalidOperationException("ILLEGAL_MODEL_JOB_STATE_TRANSITION");
            if (proposed.Id != previous.Id || proposed.Kind != previous.Kind ||
                proposed.ModelTag != previous.ModelTag ||
                proposed.LicenseSource != previous.LicenseSource ||
                proposed.ExpectedOllamaDigest != previous.ExpectedOllamaDigest ||
                proposed.ImmutableRevision != previous.ImmutableRevision ||
                proposed.LicenseAcknowledged != previous.LicenseAcknowledged ||
                proposed.LocalPath != previous.LocalPath ||
                proposed.ExpectedLocalBytes != previous.ExpectedLocalBytes ||
                proposed.ExpectedLocalSha256 != previous.ExpectedLocalSha256 ||
                proposed.RightsReceiptId != previous.RightsReceiptId ||
                proposed.RetryOfJobId != previous.RetryOfJobId ||
                proposed.MergedImport != previous.MergedImport)
                throw new InvalidOperationException("Job identity/provenance is immutable.");
            if (proposed.CompletedBytes < 0 || proposed.TotalBytes < 0 ||
                (proposed.CompletedBytes is { } done && proposed.TotalBytes is { } total && done > total))
                throw new InvalidDataException("Invalid transfer counters.");
            // Ollama layer reports can be partial; absent/regressing counters do not
            // erase already persisted bytes (or imply a successful transfer).
            if (previous.CompletedBytes is { } earlier &&
                (proposed.CompletedBytes is not { } current || current < earlier))
                proposed = proposed with { CompletedBytes = earlier, TotalBytes = previous.TotalBytes };
            if (previous.TotalBytes is { } priorTotal &&
                (proposed.TotalBytes is not { } nextTotal || nextTotal < priorTotal))
                proposed = proposed with { TotalBytes = priorTotal };
            if (proposed.CompletedBytes is { } kept && proposed.TotalBytes is { } cap && kept > cap)
                throw new InvalidDataException("MODEL_PROGRESS_EXCEEDS_TOTAL");
            jobs[index] = proposed;
            await SaveCoreAsync(jobs, ct);
            return jobs[index];
        }
        finally { _gate.Release(); }
    }

    public async Task<bool> RequestCancelAsync(Guid id, CancellationToken ct = default)
    {
        var result = await UpdateAsync(id, job => job.State switch
        {
            ModelJobState.Queued => job with { State = ModelJobState.Cancelled },
            ModelJobState.Running => job with { State = ModelJobState.Cancelling },
            _ => job
        }, ct);
        return result?.State is ModelJobState.Cancelled or ModelJobState.Cancelling;
    }

    public async Task<bool> CancelQueuedAsync(Guid id, CancellationToken ct = default)
    {
        var changed = await UpdateAsync(id, j => j.State == ModelJobState.Queued
            ? j with { State = ModelJobState.Cancelled, Status = "Cancelled before start" }
            : j, ct);
        return changed?.State == ModelJobState.Cancelled;
    }

    /// <summary>Call once at host startup. Interrupted operations require explicit retry;
    /// retained byte counters do not prove that the remote operation completed.</summary>
    /// <summary>
    /// A job lease remains held for its entire transfer. It distinguishes a
    /// live download in another NOX window from an orphan left by a crash.
    /// Do not delete the lease file: replacing its inode would defeat the lock.
    /// </summary>
    public FileStream? TryAcquireExecutionLease(Guid jobId)
    {
        if (jobId == Guid.Empty) throw new ArgumentException("Valid job identity required.", nameof(jobId));
        var path = _path + ".running." + jobId.ToString("N") + ".lock";
        ModelLocalAttestation.RequireNoExistingReparsePoint(path);
        try
        {
            return new FileStream(path, FileMode.OpenOrCreate, FileAccess.ReadWrite,
                FileShare.None, 1, FileOptions.None);
        }
        catch (IOException)
        {
            return null; // Contention or inaccessible lock: fail closed.
        }
    }

    public async Task<int> RecoverInterruptedAsync(CancellationToken ct = default)
    {
        await _gate.WaitAsync(ct);
        try
        {
            using var lease = await AcquireFileLeaseAsync(ct);
            var jobs = (await ReadCoreAsync(ct)).ToList();
            var recovered = 0;
            for (var i = 0; i < jobs.Count; i++)
            {
                if (jobs[i].State is not (ModelJobState.Running or ModelJobState.Cancelling)) continue;
                // Recovery in a second window must NOT fail another window's
                // still-running worker. OS releases the lease after a crash.
                using var orphanLease = TryAcquireExecutionLease(jobs[i].Id);
                if (orphanLease is null) continue;
                jobs[i] = jobs[i] with { State = ModelJobState.Failed,
                    Status = "Interrupted; explicit retry required", Error = "INTERRUPTED_RETRY_REQUIRED",
                    UpdatedAtUtc = DateTimeOffset.UtcNow };
                recovered++;
            }
            if (recovered > 0) await SaveCoreAsync(jobs, ct);
            return recovered;
        }
        finally { _gate.Release(); }
    }

    public async Task<ModelJob?> RetryAsync(Guid id, CancellationToken ct = default)
    {
        await _gate.WaitAsync(ct);
        try
        {
            using var lease = await AcquireFileLeaseAsync(ct);
            var jobs = (await ReadCoreAsync(ct)).ToList();
            var failed = jobs.FirstOrDefault(x => x.Id == id && x.State is ModelJobState.Failed or ModelJobState.Cancelled);
            if (failed is null) return null;
            var existingRetry = jobs.FirstOrDefault(j => j.RetryOfJobId == failed.Id &&
                (j.State is ModelJobState.Queued or ModelJobState.Running or ModelJobState.Cancelling or ModelJobState.Completed));
            if (existingRetry is not null) return existingRetry;
            var now = DateTimeOffset.UtcNow;
            var retryId = Guid.NewGuid();
            var retry = failed with { Id = retryId,
                ModelTag = failed.Kind==ModelJobKind.SafetensorsImport
                    ? "nox-forge-"+failed.ExpectedLocalSha256![..12]+":"+retryId.ToString("N") : failed.ModelTag,
                State = ModelJobState.Queued, Attempts = 0,
                CreatedAtUtc = now, UpdatedAtUtc = now, Status = "Retry queued", Error = null,
                RetryOfJobId = failed.Id,
                CompletedBytes = null, TotalBytes = null, ComputedSha256 = null, ReceiptPath = null };
            if (retry.Kind == ModelJobKind.OllamaPull &&
                (retry.ExpectedOllamaDigest is not { Length: 64 } || string.IsNullOrWhiteSpace(retry.ImmutableRevision)))
                throw new InvalidOperationException("REVIEW_REQUIRED: legacy unpinned pull cannot be retried.");
            jobs.Add(retry);
            await SaveCoreAsync(jobs, ct);
            return retry;
        }
        finally { _gate.Release(); }
    }

    /// <summary>Explicit, confirmed restore. Snapshot of current queue retained for rollback.
    /// Never silently replaces a newer queue on application startup.</summary>
    public async Task RestoreBackupAsync(bool explicitlyConfirmed, CancellationToken ct = default)
    {
        if (!explicitlyConfirmed) throw new InvalidOperationException("Queue rollback requires explicit confirmation.");
        await _gate.WaitAsync(ct);
        try
        {
            using var lease = await AcquireFileLeaseAsync(ct);
            var backup = _path + ".bak";
            ModelLocalAttestation.RequireNoExistingReparsePoint(backup);
            ModelLocalAttestation.RequireNoExistingReparsePoint(_path);
            if (!File.Exists(backup)) throw new FileNotFoundException("No queue backup exists.", backup);
            var bytes = await File.ReadAllBytesAsync(backup, ct);
            if (bytes.Length == 0 || bytes.Length > MaxQueueFileBytes)
                throw new InvalidDataException("Queue backup is invalid or too large.");
            var snapshot = JsonSerializer.Deserialize<List<ModelJob>>(bytes, JsonOptions)
                ?? throw new InvalidDataException("Backup queue is null.");
            ValidateJobs(snapshot);
            var preserved = _path + ".pre_restore." + Guid.NewGuid().ToString("N");
            if (File.Exists(_path)) File.Copy(_path, preserved, overwrite: false);
            var temp = _path + ".restore." + Guid.NewGuid().ToString("N") + ".tmp";
            try
            {
                await File.WriteAllBytesAsync(temp, bytes, ct);
                File.Move(temp, _path, overwrite: true);
            }
            finally { if (File.Exists(temp)) File.Delete(temp); }
        }
        finally { _gate.Release(); }
    }

    /// <summary>
    /// Serializes queue writes across multiple app instances, not merely one object.
    /// The lock file stays permanently so no second inode can bypass an active lease.
    /// </summary>
    private async Task<FileStream> AcquireFileLeaseAsync(CancellationToken ct)
    {
        var elapsed = Stopwatch.StartNew();
        while (true)
        {
            ct.ThrowIfCancellationRequested();
            ModelLocalAttestation.RequireNoExistingReparsePoint(_leasePath);
            try
            {
                return new FileStream(_leasePath, FileMode.OpenOrCreate, FileAccess.ReadWrite,
                    FileShare.None, 1, FileOptions.None);
            }
            catch (IOException) when (elapsed.Elapsed < TimeSpan.FromSeconds(10))
            {
                await Task.Delay(40, ct);
            }
            catch (IOException ex)
            {
                throw new IOException("P03_QUEUE_LEASE_UNAVAILABLE: concurrent queue writer", ex);
            }
        }
    }

    private async Task<IReadOnlyList<ModelJob>> ReadCoreAsync(CancellationToken ct)
    {
        ModelLocalAttestation.RequireNoExistingReparsePoint(_path);
        if (!File.Exists(_path)) return [];
        await using var input = new FileStream(_path, FileMode.Open, FileAccess.Read, FileShare.Read, 65536, true);
        if (input.Length <= 0 || input.Length > MaxQueueFileBytes)
            throw new InvalidDataException("Queue is empty or exceeds its safety limit; original bytes preserved.");
        try
        {
            var jobs = await JsonSerializer.DeserializeAsync<List<ModelJob>>(input, JsonOptions, ct)
                ?? throw new InvalidDataException("Null queue is not a valid snapshot.");
            ValidateJobs(jobs);
            return jobs;
        }
        catch (JsonException ex)
        {
            throw new InvalidDataException("Queue is corrupt; original bytes preserved.", ex);
        }
    }

    private static void ValidateJobs(IReadOnlyList<ModelJob> jobs)
    {
            if (jobs.Any(j => j is null || j.Id == Guid.Empty || j.Attempts < 0 ||
                j.CompletedBytes < 0 || j.TotalBytes < 0 ||
                (j.CompletedBytes is { } c && j.TotalBytes is { } t && c > t)) ||
                jobs.Select(j => j.Id).Distinct().Count() != jobs.Count ||
                jobs.Any(j => !Enum.IsDefined(j.Kind) || !Enum.IsDefined(j.State) ||
                    string.IsNullOrWhiteSpace(j.ModelTag) || string.IsNullOrWhiteSpace(j.LicenseSource) ||
                    !j.LicenseAcknowledged ||
                    (j.ExpectedOllamaDigest is not null && !ShaPattern.IsMatch(j.ExpectedOllamaDigest)) ||
                    ((j.Kind is ModelJobKind.GgufImport or ModelJobKind.SafetensorsImport) &&
                     (j.ExpectedLocalBytes is not > 4 || !ShaPattern.IsMatch(j.ExpectedLocalSha256 ?? "") ||
                      string.IsNullOrWhiteSpace(j.RightsReceiptId))) ||
                (j.Kind==ModelJobKind.SafetensorsImport && (j.MergedImport is null ||
                    j.MergedImport.NativeRightsVerified is not true ||
                    j.MergedImport.MergedPayloadSha256!=j.ExpectedLocalSha256 ||
                    j.MergedImport.Directory!=j.LocalPath || j.MergedImport.RightsAttestationId!=j.RightsReceiptId))))
                throw new InvalidDataException("Queue contains duplicate/invalid jobs; original bytes preserved.");
    }

    private async Task SaveCoreAsync(IReadOnlyList<ModelJob> jobs, CancellationToken ct)
    {
        ValidateJobs(jobs); // Never persist a state that cannot be read back.
        var temp = _path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            await using (var output = new FileStream(temp, FileMode.CreateNew, FileAccess.Write,
                FileShare.None, 65536, FileOptions.WriteThrough | FileOptions.Asynchronous))
            {
                await JsonSerializer.SerializeAsync(output, jobs, JsonOptions, ct);
                await output.FlushAsync(ct);
                output.Flush(flushToDisk: true);
            }
            if (new FileInfo(temp).Length > MaxQueueFileBytes)
                throw new InvalidDataException("Queue limit exceeded; original bytes preserved.");
            // Backups and queue files must remain in the authorized private directory.
            ModelLocalAttestation.RequireNoExistingReparsePoint(_path);
            ModelLocalAttestation.RequireNoExistingReparsePoint(_path + ".bak");
            // Preserve the last valid state for operator-assisted rollback.
            if (File.Exists(_path)) File.Copy(_path, _path + ".bak", overwrite: true);
            File.Move(temp, _path, overwrite: true);
        }
        finally { if (File.Exists(temp)) File.Delete(temp); }
    }
}