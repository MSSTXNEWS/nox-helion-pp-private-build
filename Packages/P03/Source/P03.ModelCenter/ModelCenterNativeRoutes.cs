using System.Text.Json;

namespace Nox.P03;

/// <summary>Native routing over the existing P03 queue, worker and reviewed registry.
/// Browser data selects an ID only; it never supplies an artifact, rights or consent.</summary>
public sealed class ModelCenterNativeRoutes : IDisposable
{
    private readonly ModelDownloadQueueStore _queue;
    private readonly ModelDownloadQueueWorker _worker;
    private readonly Func<IReadOnlyCollection<ModelCatalogEntry>> _reviewed;
    private readonly HttpClient? _ownedHttp;
    private readonly Func<CancellationToken,Task<string?>>? _nativeGgufPicker;
    private CancellationTokenSource? _mergedImportStop;
    // Native UI requests must not wait for multi-GB Ollama transfers. Reuse
    // the ONE existing ModelDownloadQueueWorker; no second transport or queue.
    private readonly CancellationTokenSource _transferStop = new();
    private readonly object _transferGate = new();
    private readonly Dictionary<Guid, Task> _transferTasks = new();
    private bool _disposed;
    private readonly SemaphoreSlim _recoveryGate = new(1, 1);
    private bool _queueRecovered;
    public static readonly IReadOnlySet<string> Routes = new HashSet<string>(StringComparer.Ordinal)
    { "models.catalog", "models.licenses", "models.preflight", "models.queue",
      "models.pull", "models.gguf.import", "models.cancel", "models.retry" };

    public ModelCenterNativeRoutes(ModelDownloadQueueStore queue, ModelDownloadQueueWorker worker,
        Func<IReadOnlyCollection<ModelCatalogEntry>> reviewed,
        Func<CancellationToken,Task<string?>>? nativeGgufPicker=null)
    { _queue=queue; _worker=worker; _reviewed=reviewed; _nativeGgufPicker=nativeGgufPicker; }

    private ModelCenterNativeRoutes(string dataDirectory, IModelLifecycleEventSink sink,
        Func<IReadOnlyCollection<ModelCatalogEntry>> reviewed,
        Func<CancellationToken,Task<string?>>? nativeGgufPicker)
    {
        _nativeGgufPicker=nativeGgufPicker;
        _queue=new ModelDownloadQueueStore(dataDirectory);
        _ownedHttp=OllamaLoopbackHttpClientFactory.Create(new Uri("http://127.0.0.1:11434/"));
        var adapter=new OllamaModelAdapter(_ownedHttp, Path.Combine(dataDirectory,"receipts"));
        _worker=new ModelDownloadQueueWorker(_queue,adapter,new ModelLifecyclePublisher(sink));
        _reviewed=reviewed;
    }

    public static ModelCenterNativeRoutes Create(string dataDirectory, IModelLifecycleEventSink sink,
        Func<IReadOnlyCollection<ModelCatalogEntry>> reviewed,
        Func<CancellationToken,Task<string?>>? nativeGgufPicker=null) => new(dataDirectory,sink,reviewed,nativeGgufPicker);

    // Read-only view for the EXISTING OneHost Micro-WOW adapter. Neither the
    // page nor a second downloader may mutate the durable queue or its rights.
    public Task<IReadOnlyList<ModelJob>> ReadJobsAsync(CancellationToken ct) =>
        ReadJobsCoreAsync(ct);

    private async Task<IReadOnlyList<ModelJob>> ReadJobsCoreAsync(CancellationToken ct) =>
        await _queue.ReadAsync(ct);

    public IReadOnlyCollection<ModelCatalogEntry> ReadReviewed() => _reviewed();

    public async Task<JsonElement> ExecuteAsync(string route, JsonElement payload,
        bool nativeConsent, CancellationToken ct)
    {
        if (!Routes.Contains(route) || payload.ValueKind != JsonValueKind.Object)
            throw new InvalidOperationException("P03_NATIVE_ROUTE_HOLD");
        // Exact owner fields only, no identity/path/approval forwarded from JavaScript.
        var allowed=route is "models.pull" or "models.gguf.import" ? new[]{"modelTag"} :
            route is "models.cancel" or "models.retry" ? new[]{"jobId"} : Array.Empty<string>();
        var fields=payload.EnumerateObject().ToArray();
        if (fields.Any(x=>!allowed.Contains(x.Name,StringComparer.Ordinal)) ||
            fields.Select(x=>x.Name).Distinct(StringComparer.Ordinal).Count()!=fields.Length)
            throw new UnauthorizedAccessException("P03_PAGE_AUTHORITY_DENIED");
        // Restore the SAME durable queue on first owner operation. Read-only
        // discovery and preflight remain usable even when local storage is HOLD.
        if (route is "models.queue" or "models.cancel" or "models.retry" or
                     "models.pull" or "models.gguf.import")
            await RecoverInterruptedOnceAsync(ct);
        object result;
        switch(route)
        {
            case "models.catalog":
            case "models.licenses":
                var reviewed=_reviewed();
                result=new { models=ModelCatalog.OfficialFamilies.Select(f=>{
                    var exact=reviewed.Where(x=>x.Id==f.Id && x.CanOfferOneClickPull).ToArray();
                    return new { id=f.Id,name=f.Name,source=f.OfficialLibraryPage.AbsoluteUri,
                        // The renderer may select a reviewed tag, never receive
                        // owner-only receipts, immutable locks or private evidence.
                        artifacts=exact.Select(a=>new {
                            tag=a.ExactTag, version=a.Version, license=a.License,
                            bytes=a.ArtifactBytes, requiredDiskBytes=a.RequiredDiskBytes,
                            recommendedRamBytes=a.RecommendedRamBytes,
                            recommendedVramBytes=a.RecommendedVramBytes,
                            licenseEvidenceUrl=a.LicenseEvidenceUri?.AbsoluteUri
                        }).ToArray(),downloadEligible=exact.Length>0,
                        status=exact.Length>0?"ARTIFACT_VERIFIED":"REVIEW_REQUIRED" }; }).ToArray() };
                break;
            case "models.preflight": result=WindowsHardwareFacts.Capture(); break;
            case "models.queue":
                result=new { jobs=(await _queue.ReadAsync(ct)).Select(PublicJob).ToArray() }; break;
            case "models.cancel":
                result=new { cancelled=await _worker.CancelAsync(JobId(payload),ct) }; break;
            case "models.retry":
                if (!nativeConsent) throw new UnauthorizedAccessException("P03_NATIVE_CONSENT_REQUIRED");
                var previous=(await _queue.ReadAsync(ct)).SingleOrDefault(x=>x.Id==JobId(payload))
                    ?? throw new InvalidOperationException("P03_EXISTING_JOB_REQUIRED");
                var retryModels=_reviewed().Where(x=>x.ExactTag==previous.ModelTag && x.CanOfferOneClickPull).ToArray();
                if (retryModels.Length!=1 ||
                    previous.Kind==ModelJobKind.OllamaPull && previous.ExpectedOllamaDigest!=retryModels[0].ExpectedManifestDigestSha256 ||
                    previous.Kind==ModelJobKind.GgufImport && previous.ExpectedLocalSha256!=retryModels[0].ExpectedSha256)
                    throw new InvalidOperationException("P03_RETRY_REVIEW_REQUIRED");
                RequireHardware(retryModels[0]);
                var retry=await _worker.RetryAsync(JobId(payload),ct)
                    ?? throw new InvalidOperationException("P03_JOB_NOT_RETRYABLE");
                StartQueuedTransfer(retry.Id);
                result=PublicJob((await _queue.ReadAsync(ct)).Single(x=>x.Id==retry.Id)); break;
            case "models.gguf.import":
                if (!nativeConsent || _nativeGgufPicker is null)
                    throw new UnauthorizedAccessException("P03_NATIVE_PICKER_CONSENT_REQUIRED");
                var importTag=payload.GetProperty("modelTag").GetString();
                var reviewedImports=_reviewed().Where(x=>x.ExactTag==importTag && x.CanOfferOneClickPull).ToArray();
                if (reviewedImports.Length!=1 || string.IsNullOrWhiteSpace(reviewedImports[0].ReviewedRightsReceiptId))
                    throw new InvalidOperationException("P03_GGUF_RIGHTS_SHA_REVIEW_REQUIRED");
                var importModel=reviewedImports[0];
                RequireHardware(importModel);
                // Native callback shows the file picker and confirms this chosen file.
                // No browser-supplied path, bytes, hash, license or rights are consumed.
                var selected=await _nativeGgufPicker(ct);
                if (string.IsNullOrWhiteSpace(selected))
                    throw new OperationCanceledException("P03_NATIVE_FILE_SELECTION_CANCELLED",ct);
                ct.ThrowIfCancellationRequested();
                // Re-read the native pinned registry after an interactive callback.
                if (!_reviewed().Any(x=>x==importModel))
                    throw new InvalidOperationException("P03_REVIEW_CHANGED_DURING_SELECTION");
                var imported=await _queue.EnqueueVerifiedGgufAsync(importTag!,selected,
                    importModel.ArtifactBytes!.Value,importModel.ExpectedSha256!,
                    importModel.ReviewedRightsReceiptId!,importModel.LicenseEvidenceUri!.AbsoluteUri,ct);
                StartQueuedTransfer(imported.Id);
                result=PublicJob((await _queue.ReadAsync(ct)).Single(x=>x.Id==imported.Id)); break;
            case "models.pull":
                if (!nativeConsent) throw new UnauthorizedAccessException("P03_NATIVE_CONSENT_REQUIRED");
                var tag=payload.GetProperty("modelTag").GetString();
                var artifacts=_reviewed().Where(x=>x.ExactTag==tag && x.CanOfferOneClickPull).ToArray();
                if (artifacts.Length!=1) throw new InvalidOperationException("P03_PINNED_ARTIFACT_REVIEW_REQUIRED");
                var model=artifacts[0];
                RequireHardware(model);
                var job=await _queue.EnqueueVerifiedPullAsync(model,true,ct);
                StartQueuedTransfer(job.Id);
                result=PublicJob((await _queue.ReadAsync(ct)).Single(x=>x.Id==job.Id)); break;
            default: throw new InvalidOperationException("P03_NATIVE_ROUTE_HOLD");
        }
        return JsonSerializer.SerializeToElement(result,new JsonSerializerOptions(JsonSerializerDefaults.Web));
    }

    /// <summary>Native-only P04 bridge; never exposed as a browser authority payload.
    /// The private worker verifies merge/eval/rights before returning approval.</summary>
    public async Task<JsonElement> ImportMergedAsync(P04MergedImportApproval approval,
        bool nativeConsent,CancellationToken ct)
    {
        using var linked=CancellationTokenSource.CreateLinkedTokenSource(ct);
        if(Interlocked.CompareExchange(ref _mergedImportStop,linked,null) is not null)
            throw new InvalidOperationException("P03_MERGED_IMPORT_ALREADY_ACTIVE");
        try { return await ImportMergedCoreAsync(approval,nativeConsent,linked.Token); }
        finally { Interlocked.CompareExchange(ref _mergedImportStop,null,linked); }
    }

    public bool StopMergedImport()
    {
        var active=Volatile.Read(ref _mergedImportStop);
        if(active is null)return false;
        try {active.Cancel();return true;}catch(ObjectDisposedException){return false;}
    }

    private async Task<JsonElement> ImportMergedCoreAsync(P04MergedImportApproval approval,
        bool nativeConsent,CancellationToken ct)
    {
        if(!nativeConsent)throw new UnauthorizedAccessException("P03_NATIVE_MERGE_IMPORT_CONSENT_REQUIRED");
        var files=await ModelSafetensorsImport.ValidateAsync(approval,ct);
        var total=files.Sum(x=>x.SizeBytes);var hardware=WindowsHardwareFacts.Capture();
        if(hardware.AvailableMemoryBytes is not long ram || ram<total ||
            hardware.SystemDiskFreeBytes is not long free || free<checked(total*2))
            throw new InvalidOperationException("P03_MERGED_IMPORT_RESOURCE_HOLD");
        var job=await _queue.EnqueueVerifiedMergedAsync(approval,true,ct);
        await _worker.RunNextAsync(ct,job.Id);
        var actual=(await _queue.ReadAsync(ct)).Single(x=>x.Id==job.Id);
        if(actual.State!=ModelJobState.Completed || string.IsNullOrWhiteSpace(actual.ReceiptPath))
            throw new SafetensorsImportHold(actual.Error??"P03_MERGED_IMPORT_NOT_COMPLETED");
        ModelLocalAttestation.RequireRegularUnlinkedFile(actual.ReceiptPath);
        await using var input=new FileStream(actual.ReceiptPath,FileMode.Open,FileAccess.Read,FileShare.Read,8192,true);
        if(input.Length>ModelLocalAttestation.MaxReceiptBytes)throw new InvalidDataException("P03_IMPORT_RECEIPT_TOO_LARGE");
        var receipt=await JsonSerializer.DeserializeAsync<ModelInstallReceipt>(input,
            new JsonSerializerOptions(JsonSerializerDefaults.Web),ct);
        if(receipt is null || receipt.JobId!=job.Id || receipt.ModelTag!=job.ModelTag ||
            receipt.Operation!="safetensors-import" || receipt.MergedPayloadSha256!=approval.MergedPayloadSha256 ||
            receipt.MergeReceiptSha256!=approval.MergeReceiptSha256 ||
            receipt.TrainingReceiptSha256!=approval.TrainingReceiptSha256 ||
            receipt.RightsAttestationId!=approval.RightsAttestationId ||
            receipt.RightsAttestationSha256!=approval.RightsAttestationSha256 ||
            receipt.NativeApprovalId!=approval.NativeApprovalId || receipt.ImportedFiles is null ||
            !receipt.ImportedFiles.SequenceEqual(files))
            throw new InvalidDataException("P03_IMPORT_RECEIPT_BINDING_MISMATCH");
        await ModelLocalAttestation.VerifyReceiptAsync(actual.ReceiptPath,receipt,ct);
        return JsonSerializer.SerializeToElement(new {status="IMPORTED",jobId=job.Id,
            receiptPath=actual.ReceiptPath,receipt},new JsonSerializerOptions(JsonSerializerDefaults.Web));
    }

    private async Task RecoverInterruptedOnceAsync(CancellationToken ct)
    {
        await _recoveryGate.WaitAsync(ct);
        try
        {
            if (_queueRecovered) return;
            // Existing store holds an OS lease: another live NOX window's
            // transfer must NOT be marked crashed. No auto-requeue/download.
            await _queue.RecoverInterruptedAsync(ct);
            _queueRecovered = true;
        }
        finally { _recoveryGate.Release(); }
    }

    private void StartQueuedTransfer(Guid jobId)
    {
        Task pending;
        lock (_transferGate)
        {
            if (_disposed) throw new ObjectDisposedException(nameof(ModelCenterNativeRoutes));
            // One durable queue and one worker: the UI receives the job receipt
            // immediately, while the existing worker serializes all transfers.
            if (_transferTasks.ContainsKey(jobId)) return;
            var token = _transferStop.Token;
            pending = Task.Run(() => _worker.RunNextAsync(token, jobId),
                CancellationToken.None);
            _transferTasks.Add(jobId, pending);
        }
        // Register completion AFTER the job is entered in the dictionary and
        // AFTER releasing its gate. ExecuteSynchronously can otherwise observe
        // an already-completed task before Add and leave a permanently stale job.
        _ = pending.ContinueWith(completed =>
        {
            if (completed.IsFaulted)
                System.Diagnostics.Trace.TraceError(
                    "P03_BACKGROUND_TRANSFER_FAILED job={0} exception={1}",
                    jobId, completed.Exception?.GetBaseException().GetType().Name);
            lock (_transferGate)
            {
                _transferTasks.Remove(jobId);
                if (_disposed && _transferTasks.Count == 0)
                {
                    _transferStop.Dispose();
                    _ownedHttp?.Dispose();
                }
            }
        }, CancellationToken.None, TaskContinuationOptions.ExecuteSynchronously,
           TaskScheduler.Default);
    }

    private static void RequireHardware(ModelCatalogEntry model)
    {
        var hardware=WindowsHardwareFacts.Capture();
        var ramReady=model.RecommendedRamBytes is long ram && ram>0 &&
            hardware.AvailableMemoryBytes is long actual && actual>=ram;
        if (model.RequiredDiskBytes is not long disk || hardware.SystemDiskFreeBytes is not long free || free<disk || !ramReady)
            // Sufficient measured RAM admits CPU fallback. A GPU-only profile
            // needs actual VRAM evidence and stays HOLD, never a fake sensor.
            throw new InvalidOperationException("P03_HARDWARE_PREFLIGHT_HOLD");
    }

    private static Guid JobId(JsonElement payload) =>
        payload.TryGetProperty("jobId",out var id) && id.ValueKind==JsonValueKind.String &&
        Guid.TryParse(id.GetString(),out var value) && value!=Guid.Empty ? value :
        throw new ArgumentException("P03_EXISTING_JOB_ID_REQUIRED");
    private static object PublicJob(ModelJob job) => new { job.Id,job.ModelTag,
        state=job.State.ToString(),job.Status,job.CompletedBytes,job.TotalBytes,job.Attempts,job.Error };
    public void Dispose()
    {
        lock (_transferGate)
        {
            if (_disposed) return;
            _disposed = true;
            // Owner STOP precedes disposal. The HTTP client remains alive
            // until the last already-admitted transfer has terminated.
            _transferStop.Cancel();
            if (_transferTasks.Count == 0)
            {
                _transferStop.Dispose();
                _ownedHttp?.Dispose();
            }
        }
        StopMergedImport();
    }
}
