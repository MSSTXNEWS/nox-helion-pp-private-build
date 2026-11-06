using System.Text.Json;
using System.Diagnostics;
using System.Text.RegularExpressions;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

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

    // Win32 BY_HANDLE_FILE_INFORMATION: hardlinks do not have ReparsePoint.
    // Test the same live file handle used by the subsequent JSON parser.
    [StructLayout(LayoutKind.Sequential)]
    private struct QueueFileTime { public uint Low; public uint High; }
    [StructLayout(LayoutKind.Sequential)]
    private struct QueueByHandleInfo
    {
        public uint Attributes;
        public QueueFileTime CreationTime;
        public QueueFileTime LastAccessTime;
        public QueueFileTime LastWriteTime;
        public uint VolumeSerialNumber;
        public uint FileSizeHigh;
        public uint FileSizeLow;
        public uint NumberOfLinks;
        public uint FileIndexHigh;
        public uint FileIndexLow;
    }
    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool GetFileInformationByHandle(
        SafeFileHandle file, out QueueByHandleInfo information);

    private static void RequireSingleLinkQueueSnapshot(SafeFileHandle file)
    {
        if (!OperatingSystem.IsWindows()) return;
        if (!GetFileInformationByHandle(file, out var info))
            throw new IOException("P03_QUEUE_FILE_IDENTITY_UNAVAILABLE_HOLD");
        if (info.NumberOfLinks != 1)
            throw new InvalidDataException("P03_QUEUE_HARDLINK_SNAPSHOT_HOLD");
    }

    // Snapshot only bytes from an owner-authorized, single-link OPEN HANDLE.
    // A path can be replaced with an NTFS hardlink between queue validation and
    // backup rotation or rollback. Path-only reparse checks cannot detect it.
    private static async Task SnapshotOwnedQueueAsync(string fromPath, string toPath,
        CancellationToken ct)
    {
        ModelLocalAttestation.RequireNoExistingReparsePoint(fromPath);
        await using var input = new FileStream(fromPath, FileMode.Open, FileAccess.Read,
            FileShare.Read, 65536, FileOptions.Asynchronous | FileOptions.SequentialScan);
        RequireSingleLinkQueueSnapshot(input.SafeFileHandle);
        if (input.Length <= 0 || input.Length > MaxQueueFileBytes)
            throw new InvalidDataException("P03_QUEUE_SNAPSHOT_SIZE_HOLD");
        await using var output = new FileStream(toPath, FileMode.CreateNew,
            FileAccess.Write, FileShare.None, 65536,
            FileOptions.Asynchronous | FileOptions.WriteThrough);
        await input.CopyToAsync(output, 65536, ct);
        await output.FlushAsync(ct);
        output.Flush(flushToDisk: true);
    }

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
        if (expectedBytes <= 4 || expectedSha256 is null || !ShaPattern.IsMatch(expectedSha256)
            || !HasReviewedGgufAuthority(rightsReceiptId, licenseSource))
            throw new InvalidDataException("REVIEW_REQUIRED: GGUF expected bytes/SHA-256/rights receipt.");
        if (string.IsNullOrWhiteSpace(localPath) ||
            // Relative or drive-relative paths depend on the process working directory:
            // never turn an unreviewed path into an owner-authorized absolute file.
            !Path.IsPathFullyQualified(localPath) ||
            !string.Equals(Path.GetExtension(localPath), ".gguf", StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("GGUF path and extension required.");
        var fullPath = Path.GetFullPath(localPath);
        ModelLocalAttestation.RequireRegularUnlinkedFile(fullPath);
        if (new FileInfo(fullPath).Length != expectedBytes)
            throw new InvalidDataException("GGUF_BYTES_DIFFER_FROM_REVIEWED_ARTIFACT");
        await _gate.WaitAsync(ct);
        try
        {
            using var lease = await AcquireFileLeaseAsync(ct);
            var jobs = (await ReadCoreAsync(ct)).ToList();
            if (jobs.Any(j => HasActiveTag(j, tag)))
                throw new InvalidOperationException("P03_ACTIVE_MODEL_TAG_CONFLICT_HOLD");
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
        // These are native P04-reviewed filesystem identities, not paths relative
        // to the caller's mutable process working directory. Reject both before
        // normalization or queue mutation, like reviewed GGUF imports.
        ArgumentNullException.ThrowIfNull(approval);
        if (string.IsNullOrWhiteSpace(approval.Directory) ||
            string.IsNullOrWhiteSpace(approval.TrainingReceiptPath) ||
            !Path.IsPathFullyQualified(approval.Directory) ||
            !Path.IsPathFullyQualified(approval.TrainingReceiptPath))
            throw new InvalidDataException("P03_P04_MERGE_OWNER_ABSOLUTE_PATH_HOLD");
        approval=approval with {Directory=Path.GetFullPath(approval.Directory),TrainingReceiptPath=Path.GetFullPath(approval.TrainingReceiptPath)};
        var files=await ModelSafetensorsImport.ValidateAsync(approval,ct);
        var id=Guid.NewGuid();var tag="nox-forge-"+approval.MergedPayloadSha256[..12]+":"+id.ToString("N");
        await _gate.WaitAsync(ct);
        try {
            using var lease=await AcquireFileLeaseAsync(ct);
            var jobs=(await ReadCoreAsync(ct)).ToList();var now=DateTimeOffset.UtcNow;
            if (jobs.Any(j => HasActiveTag(j, tag)))
                throw new InvalidOperationException("P03_ACTIVE_MODEL_TAG_CONFLICT_HOLD");
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
            string.IsNullOrWhiteSpace(model.ImmutableRevision) ||
            string.IsNullOrWhiteSpace(model.ReviewedRightsReceiptId) ||
            model.ReviewedRightsReceiptId.Length > 128 ||
            model.ReviewedRightsReceiptId.Any(char.IsControl))
            throw new InvalidOperationException("REVIEW_REQUIRED: exact artifact evidence is incomplete.");
        ValidateTag(model.ExactTag);
        var licenseUrl = model.LicenseEvidenceUri!.ToString();
        await _gate.WaitAsync(ct);
        try
        {
            using var lease = await AcquireFileLeaseAsync(ct);
            var jobs = (await ReadCoreAsync(ct)).ToList();
            // An active tag belongs to exactly one owner-reviewed transfer. Do not
            // recycle a live job after rights, licensed origin or immutable pins
            // change: that would turn an obsolete authorization into a new ACK.
            var active = jobs.Where(j => HasActiveTag(j, model.ExactTag)).ToArray();
            if (active.Length > 0)
            {
                // Never ACK a durable STOP-pending transfer as a new pull.
                if (active.Any(j => j.State == ModelJobState.Cancelling))
                    throw new InvalidOperationException("P03_ACTIVE_MODEL_STOP_PENDING_HOLD");
                if (active.Length != 1 || active[0].Kind != ModelJobKind.OllamaPull ||
                    !active[0].LicenseAcknowledged ||
                    !string.Equals(active[0].ModelTag, model.ExactTag, StringComparison.Ordinal) ||
                    !string.Equals(active[0].ExpectedOllamaDigest,
                        model.ExpectedManifestDigestSha256, StringComparison.OrdinalIgnoreCase) ||
                    !string.Equals(active[0].ImmutableRevision, model.ImmutableRevision,
                        StringComparison.Ordinal) ||
                    !string.Equals(active[0].RightsReceiptId, model.ReviewedRightsReceiptId,
                        StringComparison.Ordinal) ||
                    !string.Equals(active[0].LicenseSource, licenseUrl, StringComparison.Ordinal))
                    throw new InvalidOperationException("P03_ACTIVE_PULL_REVIEW_CHANGED_HOLD");
                return active[0];
            }
            var now = DateTimeOffset.UtcNow;
            var job = new ModelJob(Guid.NewGuid(), ModelJobKind.OllamaPull,
                model.ExactTag, null, true, licenseUrl, now, now,
                ExpectedOllamaDigest: model.ExpectedManifestDigestSha256!.ToLowerInvariant(),
                ImmutableRevision: model.ImmutableRevision,
                RightsReceiptId: model.ReviewedRightsReceiptId);
            jobs.Add(job);
            await SaveCoreAsync(jobs, ct);
            return job;
        }
        finally { _gate.Release(); }
    }

    // A tag is the mutable Ollama installation identity across ALL job kinds.
    private static bool HasActiveTag(ModelJob job, string tag) =>
        (job.State is ModelJobState.Queued or ModelJobState.Running or ModelJobState.Cancelling) &&
        string.Equals(job.ModelTag, tag, StringComparison.OrdinalIgnoreCase);

    // Historical on-disk Pull entries remain readable, but immutable owner
    // consent must be re-checked before claim, retry, or direct Ollama IO.
    internal static bool HasReviewedPullAuthority(ModelJob job)
    {
        var revision = job.ImmutableRevision;
        var pinned = revision is { Length: 64 } && ShaPattern.IsMatch(revision) ||
            revision is { Length: 71 } &&
            revision.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase) &&
            ShaPattern.IsMatch(revision[7..]);
        return job.Kind == ModelJobKind.OllamaPull &&
            job.ExpectedOllamaDigest is { Length: 64 } &&
            ShaPattern.IsMatch(job.ExpectedOllamaDigest) && pinned &&
            job.LicenseAcknowledged && !string.IsNullOrWhiteSpace(job.ModelTag) &&
            job.ModelTag.Length <= 160 && TagPattern.IsMatch(job.ModelTag) &&
            !job.ModelTag.Contains("..", StringComparison.Ordinal) &&
            !job.ModelTag.EndsWith(":latest", StringComparison.OrdinalIgnoreCase) &&
            HasReviewedGgufAuthority(job.RightsReceiptId, job.LicenseSource);
    }

    // GGUF owner's rights reference is durable review evidence, not arbitrary input.
    // Existing unsafe queue snapshots remain readable for explicit owner recovery;
    // enqueue, atomic claim and retry must refuse transferring them.
    internal static bool HasReviewedGgufAuthority(string? rightsReceiptId, string? licenseSource)
    {
        if (string.IsNullOrWhiteSpace(rightsReceiptId) || rightsReceiptId.Length > 128 ||
            rightsReceiptId.Any(char.IsControl) || string.IsNullOrWhiteSpace(licenseSource) ||
            !Uri.TryCreate(licenseSource, UriKind.Absolute, out var uri))
            return false;
        // External HTTPS evidence only. URL shape is not proof of licensed
        // rights: the existing native owner attestation remains mandatory.
        return uri.Scheme == Uri.UriSchemeHttps && uri.IsDefaultPort &&
            !uri.IsLoopback && !string.IsNullOrWhiteSpace(uri.Host) &&
            string.IsNullOrEmpty(uri.UserInfo) && string.IsNullOrEmpty(uri.Fragment) &&
            !uri.Host.Equals("localhost", StringComparison.OrdinalIgnoreCase) &&
            !uri.Host.EndsWith(".localhost", StringComparison.OrdinalIgnoreCase) &&
            !uri.Host.EndsWith(".local", StringComparison.OrdinalIgnoreCase) &&
            !uri.Host.EndsWith(".internal", StringComparison.OrdinalIgnoreCase);
    }


    // Preserve historical queue bytes, but bind the COMPLETE owner-reviewed
    // GGUF job on claim/retry/worker/direct adapter reentry before Ollama I/O.
    internal static bool HasReviewedGgufJobAuthority(ModelJob job)
    {
        var tag = job.ModelTag;
        var path = job.LocalPath;
        return job.Kind == ModelJobKind.GgufImport &&
            job.LicenseAcknowledged &&
            job.ExpectedLocalBytes is > 4 &&
            job.ExpectedLocalSha256 is { Length: 64 } &&
            ShaPattern.IsMatch(job.ExpectedLocalSha256) &&
            !string.IsNullOrWhiteSpace(tag) && tag.Length <= 160 &&
            TagPattern.IsMatch(tag) &&
            !tag.Contains("..", StringComparison.Ordinal) &&
            !tag.EndsWith(":latest", StringComparison.OrdinalIgnoreCase) &&
            !string.IsNullOrWhiteSpace(path) &&
            Path.IsPathFullyQualified(path) &&
            string.Equals(Path.GetExtension(path), ".gguf", StringComparison.OrdinalIgnoreCase) &&
            HasReviewedGgufAuthority(job.RightsReceiptId, job.LicenseSource);
    }


    // Persisted P04 approvals must still bind to this EXACT native job on
    // recovery, worker claim, explicit retry and direct adapter entry.
    // This is a structural authority gate; ValidateAsync additionally checks
    // the real files, pinned receipt SHA-256 and rights evidence before I/O.
    internal static bool HasReviewedMergedJobAuthority(ModelJob job)
    {
        var approval = job.MergedImport;
        if (job.Kind != ModelJobKind.SafetensorsImport || approval is null ||
            job.Id == Guid.Empty || !job.LicenseAcknowledged ||
            job.ExpectedLocalBytes is not > 4 || !approval.NativeRightsVerified ||
            approval.MergedPayloadSha256 is not { Length: 64 } ||
            !ShaPattern.IsMatch(approval.MergedPayloadSha256) ||
            !ShaPattern.IsMatch(approval.MergeReceiptSha256 ?? "") ||
            !ShaPattern.IsMatch(approval.TrainingReceiptSha256 ?? "") ||
            !ShaPattern.IsMatch(approval.RightsAttestationSha256 ?? "") ||
            string.IsNullOrWhiteSpace(approval.RightsAttestationId) ||
            approval.RightsAttestationId.Length > 128 ||
            approval.RightsAttestationId.Any(char.IsControl) ||
            string.IsNullOrWhiteSpace(approval.NativeApprovalId) ||
            approval.NativeApprovalId.Length > 200 ||
            string.IsNullOrWhiteSpace(approval.Directory) ||
            string.IsNullOrWhiteSpace(approval.TrainingReceiptPath) ||
            !Path.IsPathFullyQualified(approval.Directory) ||
            !Path.IsPathFullyQualified(approval.TrainingReceiptPath) ||
            !string.Equals(job.LocalPath, approval.Directory, StringComparison.Ordinal) ||
            !string.Equals(job.ExpectedLocalSha256, approval.MergedPayloadSha256, StringComparison.Ordinal) ||
            !string.Equals(job.RightsReceiptId, approval.RightsAttestationId, StringComparison.Ordinal) ||
            !string.Equals(job.LicenseSource, approval.LicenseSource, StringComparison.Ordinal) ||
            !string.Equals(job.ModelTag,
                "nox-forge-" + approval.MergedPayloadSha256[..12] + ":" + job.Id.ToString("N"),
                StringComparison.Ordinal) ||
            !Uri.TryCreate(approval.LicenseSource, UriKind.Absolute, out var license) ||
            license.Scheme != Uri.UriSchemeHttps || !string.IsNullOrEmpty(license.UserInfo))
            return false;
        return true;
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
            if (old.Kind == ModelJobKind.OllamaPull && !HasReviewedPullAuthority(old))
                throw new InvalidOperationException("REVIEW_REQUIRED: unpinned Pull cannot start.");
            if (old.Kind == ModelJobKind.GgufImport &&
                !HasReviewedGgufJobAuthority(old))
                throw new InvalidOperationException("REVIEW_REQUIRED: unreviewed GGUF cannot start.");
            if (old.Kind == ModelJobKind.SafetensorsImport &&
                !HasReviewedMergedJobAuthority(old))
                throw new InvalidOperationException("REVIEW_REQUIRED: unreviewed merged import cannot start.");
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
                // STOP is already durably requested. If its worker crashed after
                // relinquishing the OS execution lease, finish the cancellation;
                // recovery must never recast an acknowledged STOP as Failed.
                // A genuinely interrupted Running job still requires explicit retry.
                var stopWasPersisted = jobs[i].State == ModelJobState.Cancelling;
                jobs[i] = jobs[i] with {
                    State = stopWasPersisted ? ModelJobState.Cancelled : ModelJobState.Failed,
                    Status = stopWasPersisted ? "Cancelled after interrupted STOP" :
                        "Interrupted; explicit retry required",
                    Error = stopWasPersisted ? null : "INTERRUPTED_RETRY_REQUIRED",
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
            // Re-queueing a failed owner-reviewed pull must never start a second
            // transfer beside a newly approved active tag (or reuse stale rights).
            // The original owner approval remains required for any explicit retry.
            if (failed.Kind == ModelJobKind.OllamaPull && !HasReviewedPullAuthority(failed))
                throw new InvalidOperationException("REVIEW_REQUIRED: legacy/unreviewed pull cannot be retried.");
            if (failed.Kind == ModelJobKind.GgufImport &&
                !HasReviewedGgufJobAuthority(failed))
                throw new InvalidOperationException("REVIEW_REQUIRED: unreviewed GGUF cannot be retried.");
            if (failed.Kind == ModelJobKind.SafetensorsImport &&
                !HasReviewedMergedJobAuthority(failed))
                throw new InvalidOperationException("REVIEW_REQUIRED: unreviewed merged import cannot be retried.");
            bool SameApprovedPull(ModelJob job) =>
                string.Equals(job.ModelTag, failed.ModelTag, StringComparison.Ordinal) &&
                string.Equals(job.ExpectedOllamaDigest, failed.ExpectedOllamaDigest,
                    StringComparison.OrdinalIgnoreCase) &&
                string.Equals(job.ImmutableRevision, failed.ImmutableRevision, StringComparison.Ordinal) &&
                string.Equals(job.RightsReceiptId, failed.RightsReceiptId, StringComparison.Ordinal) &&
                string.Equals(job.LicenseSource, failed.LicenseSource, StringComparison.Ordinal) &&
                job.LicenseAcknowledged == failed.LicenseAcknowledged;
            var activeTagJobs = jobs.Where(j => HasActiveTag(j, failed.ModelTag)).ToArray();
            // Durable STOP cannot be reused as approval for a new retry.
            if (activeTagJobs.Any(j => j.State == ModelJobState.Cancelling))
                throw new InvalidOperationException("P03_RETRY_ACTIVE_STOP_PENDING_HOLD");
            if (activeTagJobs.Length > 0 &&
                (activeTagJobs.Length != 1 ||
                 activeTagJobs[0].Kind != failed.Kind ||
                 activeTagJobs[0].RetryOfJobId != failed.Id ||
                 (failed.Kind == ModelJobKind.OllamaPull && !SameApprovedPull(activeTagJobs[0]))))
                throw new InvalidOperationException(failed.Kind == ModelJobKind.OllamaPull
                    ? "P03_RETRY_ACTIVE_PULL_REVIEW_CHANGED_HOLD"
                    : "P03_RETRY_ACTIVE_TAG_CONFLICT_HOLD");
            var existingRetry = jobs.FirstOrDefault(j => j.RetryOfJobId == failed.Id &&
                (j.State is ModelJobState.Queued or ModelJobState.Running or ModelJobState.Cancelling or ModelJobState.Completed));
            if (existingRetry is not null)
            {
                // A Safetensors retry has a fresh tag, so the parent-tag check
                // above cannot observe its pending STOP; guard the retry itself.
                if (existingRetry.State == ModelJobState.Cancelling)
                    throw new InvalidOperationException("P03_RETRY_ACTIVE_STOP_PENDING_HOLD");
                if (failed.Kind == ModelJobKind.OllamaPull && !SameApprovedPull(existingRetry))
                    throw new InvalidOperationException("P03_RETRY_ACTIVE_PULL_REVIEW_CHANGED_HOLD");
                return existingRetry;
            }
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
            // Explicit rollback never replaces a live owner's transfer or erases
            // an acknowledged STOP in another NOX window. The cross-process
            // queue lease holds states stable through the restored publication.
            var liveJobs = await ReadCoreAsync(ct);
            if (liveJobs.Any(j => j.State is ModelJobState.Running or ModelJobState.Cancelling))
                throw new InvalidOperationException("P03_QUEUE_ACTIVE_RESTORE_HOLD");
            byte[] bytes;
            await using (var backupInput = new FileStream(backup, FileMode.Open,
                FileAccess.Read, FileShare.Read, 65536, FileOptions.Asynchronous))
            {
                // A foreign hardlink must not be read as owner-authorized backup.
                RequireSingleLinkQueueSnapshot(backupInput.SafeFileHandle);
                if (backupInput.Length <= 0 || backupInput.Length > MaxQueueFileBytes)
                    throw new InvalidDataException("Queue backup is invalid or too large.");
                bytes = new byte[checked((int)backupInput.Length)];
                await backupInput.ReadExactlyAsync(bytes, ct);
            }
            var snapshot = DeserializeStrictSnapshot(bytes);
            // A historical backup is not a live transfer lease or owner STOP grant.
            // Restoring RUNNING/CANCELLING would resurrect stale activity without
            // a worker, and could misrepresent an acknowledged native STOP.
            // Refuse before snapshot/publication; preserve both queue and backup.
            if (snapshot.Any(j => j.State is ModelJobState.Running or ModelJobState.Cancelling))
                throw new InvalidDataException("P03_QUEUE_BACKUP_ACTIVE_RESTORE_HOLD");
            var preserved = _path + ".pre_restore." + Guid.NewGuid().ToString("N");
            if (File.Exists(_path)) await SnapshotOwnedQueueAsync(_path, preserved, ct);
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


    // The Web JSON serializer resolves property names case-insensitively.
    // Never trust a durable job or backup if JSON fields have conflicting
    // spellings, escaped aliases or nested duplicates (last-wins ambiguity).
    // Preserve original bytes; caller holds the native cross-process lease.
    private static void RequireUnambiguousJson(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in element.EnumerateArray()) RequireUnambiguousJson(item);
        }
        else if (element.ValueKind == JsonValueKind.Object)
        {
            var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (var property in element.EnumerateObject())
            {
                if (!seen.Add(property.Name))
                    throw new InvalidDataException("P03_QUEUE_DUPLICATE_JSON_FIELD_HOLD");
                RequireUnambiguousJson(property.Value);
            }
        }
    }

    private static List<ModelJob> DeserializeStrictSnapshot(ReadOnlyMemory<byte> bytes)
    {
        using var document = JsonDocument.Parse(bytes, new JsonDocumentOptions
        {
            MaxDepth = 64, AllowTrailingCommas = false,
            CommentHandling = JsonCommentHandling.Disallow
        });
        if (document.RootElement.ValueKind != JsonValueKind.Array)
            throw new InvalidDataException("P03_QUEUE_JSON_ROOT_HOLD");
        RequireUnambiguousJson(document.RootElement);
        var jobs = JsonSerializer.Deserialize<List<ModelJob>>(bytes.Span, JsonOptions)
            ?? throw new InvalidDataException("Null queue is not a valid snapshot.");
        ValidateJobs(jobs);
        return jobs;
    }

    private async Task<IReadOnlyList<ModelJob>> ReadCoreAsync(CancellationToken ct)
    {
        ModelLocalAttestation.RequireNoExistingReparsePoint(_path);
        if (!File.Exists(_path)) return [];
        await using var input = new FileStream(_path, FileMode.Open, FileAccess.Read, FileShare.Read, 65536, true);
        RequireSingleLinkQueueSnapshot(input.SafeFileHandle);
        if (input.Length <= 0 || input.Length > MaxQueueFileBytes)
            throw new InvalidDataException("Queue is empty or exceeds its safety limit; original bytes preserved.");
        try
        {
            var bytes = new byte[checked((int)input.Length)];
            await input.ReadExactlyAsync(bytes, ct);
            return DeserializeStrictSnapshot(bytes);
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
        // All native job kinds mutate the same installed Ollama tag.
        // Refuse cross-kind active collisions, while retaining terminal history.
        var activeTags = jobs.Where(j => HasActiveTag(j, j.ModelTag))
            .Select(j => j.ModelTag).ToArray();
        if (activeTags.Distinct(StringComparer.OrdinalIgnoreCase).Count() != activeTags.Length)
            throw new InvalidDataException("P03_QUEUE_ACTIVE_TAG_ALIAS_HOLD");
    }

    private async Task SaveCoreAsync(IReadOnlyList<ModelJob> jobs, CancellationToken ct)
    {
        ValidateJobs(jobs); // Never persist a state that cannot be read back.
        var temp = _path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        // A backup can be a hardlink even when the reparse-point check passes.
        // Never copy onto its existing inode or modify unrelated owner data.
        var backupTemp = _path + "." + Guid.NewGuid().ToString("N") + ".bak.tmp";
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
            // A new private snapshot and directory-entry replacement avoid
            // writing through a hardlink at the fixed backup name.
            if (File.Exists(_path))
            {
                await SnapshotOwnedQueueAsync(_path, backupTemp, ct);
                ModelLocalAttestation.RequireNoExistingReparsePoint(_path + ".bak");
                File.Move(backupTemp, _path + ".bak", overwrite: true);
            }
            File.Move(temp, _path, overwrite: true);
        }
        finally
        {
            if (File.Exists(temp)) File.Delete(temp);
            if (File.Exists(backupTemp)) File.Delete(backupTemp);
        }
    }
}