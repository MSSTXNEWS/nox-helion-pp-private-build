using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace Nox.P03;

public sealed record OllamaStreamUpdate(string Status, long? Completed, long? Total, string? Digest, string? Error);
public sealed record ModelInstallReceipt(string Schema, Guid JobId, string ModelTag, string Operation,
    DateTimeOffset CompletedAtUtc, long? LocalBytes, string? LocalSha256, string? OllamaDigest,
    string LicenseSource, string OllamaEndpoint,
    string? MergedPayloadSha256=null, string? MergeReceiptSha256=null,
    string? TrainingReceiptSha256=null, string? RightsAttestationId=null,
    string? RightsAttestationSha256=null, string? NativeApprovalId=null,
    IReadOnlyList<ImportedModelFile>? ImportedFiles=null);

/// <summary>Thin adapter over the official Ollama HTTP API; no second downloader is implemented.</summary>
public sealed class OllamaModelAdapter(HttpClient http, string receiptDirectory)
{
    private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web);

    public async Task<string?> PullAsync(ModelJob job, Func<OllamaStreamUpdate, CancellationToken, ValueTask> progress,
        CancellationToken ct)
    {
        EnsureLocalOllama();
        if (job.Kind != ModelJobKind.OllamaPull) throw new ArgumentException("Job is not an Ollama pull.", nameof(job));
        if (job.ExpectedOllamaDigest is not { Length: 64 } ||
            !job.ExpectedOllamaDigest.All(Uri.IsHexDigit) ||
            string.IsNullOrWhiteSpace(job.ImmutableRevision))
            throw new InvalidDataException("REVIEW_REQUIRED: no immutable artifact digest/revision lock.");
        using var response = await SendStreamingJsonAsync("api/pull", new { model = job.ModelTag, stream = true }, ct);
        response.EnsureSuccessStatusCode();
        var layers = new Dictionary<string, (long Completed, long Total)>();
        var terminalSuccess = false;
        await foreach (var update in ReadEventsAsync(response, ct))
        {
            if (update.Error is not null) throw new InvalidOperationException(update.Error);
            if (string.Equals(update.Status, "success", StringComparison.OrdinalIgnoreCase)) terminalSuccess = true;
            if (update.Digest is not null && update.Total is > 0)
            {
                var nextDone = update.Completed ?? 0;
                if (nextDone < 0 || nextDone > update.Total.Value)
                    throw new InvalidDataException("Invalid Ollama layer counters.");
                if (layers.TryGetValue(update.Digest, out var old))
                {
                    if (update.Total.Value != old.Total) throw new InvalidDataException("Ollama layer size changed during transfer.");
                    layers[update.Digest] = (Math.Max(nextDone, old.Completed), old.Total);
                }
                else layers[update.Digest] = (nextDone, update.Total.Value);
            }
            else if (layers.Count == 1 && update.Completed is not null)
            {
                var key = layers.Keys.First();
                if (update.Completed.Value < 0 || update.Completed.Value > layers[key].Total)
                    throw new InvalidDataException("Invalid aggregate Ollama progress.");
                layers[key] = (Math.Max(update.Completed.Value, layers[key].Completed), layers[key].Total);
            }
            var completed = layers.Count == 0 ? update.Completed : checked(layers.Values.Sum(x => x.Completed));
            var total = layers.Count == 0 ? update.Total : checked(layers.Values.Sum(x => x.Total));
            await progress(update with { Completed = completed, Total = total }, ct);
        }
        if (!terminalSuccess) throw new InvalidDataException("OLLAMA_PULL_STREAM_TRUNCATED_NO_SUCCESS");
        var local = RequireOllamaDigest(await GetLocalModelDigestAsync(job.ModelTag, ct));
        if (!string.Equals(local.Replace("sha256:", "", StringComparison.OrdinalIgnoreCase),
            job.ExpectedOllamaDigest, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("OLLAMA_PULL_PINNED_DIGEST_MISMATCH");
        await WriteReceiptAsync(new ModelInstallReceipt("NOX_P03_INSTALL_RECEIPT_V1", job.Id,
            job.ModelTag, "ollama-pull", DateTimeOffset.UtcNow, null, null, local,
            job.LicenseSource, http.BaseAddress?.ToString() ?? "http://localhost:11434/"), ct);
        return local;
    }

    public async Task<(long Bytes, string Sha256)> ImportGgufAsync(ModelJob job,
        Func<OllamaStreamUpdate, CancellationToken, ValueTask> progress, CancellationToken ct)
    {
        EnsureLocalOllama();
        if (job.ExpectedLocalBytes is not > 4 || job.ExpectedLocalSha256 is not { Length: 64 } ||
            !job.ExpectedLocalSha256.All(Uri.IsHexDigit) || string.IsNullOrWhiteSpace(job.RightsReceiptId))
            throw new InvalidDataException("REVIEW_REQUIRED: independent GGUF bytes/SHA/rights proof required.");
        if (job.Kind != ModelJobKind.GgufImport || string.IsNullOrWhiteSpace(job.LocalPath))
            throw new ArgumentException("Job must contain a local GGUF path.", nameof(job));
        var path = Path.GetFullPath(job.LocalPath);
        ModelLocalAttestation.RequireRegularUnlinkedFile(path);
        if (!File.Exists(path) || !string.Equals(Path.GetExtension(path), ".gguf", StringComparison.OrdinalIgnoreCase))
            throw new FileNotFoundException("Select an existing .gguf file.", path);

        // Hash and upload the same open file handle to prevent path replacement between hashing and upload.
        await using var file = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 20,
            FileOptions.Asynchronous | FileOptions.SequentialScan);
        var bytes = file.Length;
        if (bytes < 4 || bytes != job.ExpectedLocalBytes)
            throw new InvalidDataException("GGUF size differs from reviewed evidence.");
        var header = new byte[4];
        if (!(await TryReadGgufHeaderAsync(file, header, ct)) || Encoding.ASCII.GetString(header) != "GGUF")
            throw new InvalidDataException("GGUF header missing.");
        file.Position = 0;
        var hashBytes = await SHA256.HashDataAsync(file, ct);
        var sha = Convert.ToHexString(hashBytes).ToLowerInvariant();
        if (!sha.Equals(job.ExpectedLocalSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("GGUF SHA-256 differs from reviewed evidence.");
        var digest = "sha256:" + sha;
        file.Position = 0;

        using (var presence = await http.SendAsync(new HttpRequestMessage(HttpMethod.Head, "api/blobs/" + digest), ct))
        {
            if (presence.StatusCode == System.Net.HttpStatusCode.NotFound)
            {
                using var upload = new StreamContent(file);
                using var uploaded = await http.PostAsync("api/blobs/" + digest, upload, ct);
                uploaded.EnsureSuccessStatusCode();
            }
            else presence.EnsureSuccessStatusCode();
        }

        using (var verifiedBlob = await http.SendAsync(new HttpRequestMessage(HttpMethod.Head, "api/blobs/" + digest), ct))
            verifiedBlob.EnsureSuccessStatusCode();

        var payload = new { model = job.ModelTag, files = new Dictionary<string, string> { [Path.GetFileName(path)] = digest }, stream = true };
        using var create = await SendStreamingJsonAsync("api/create", payload, ct);
        create.EnsureSuccessStatusCode();
        var createSuccess = false;
        await foreach (var update in ReadEventsAsync(create, ct))
        {
            if (update.Error is not null) throw new InvalidOperationException(update.Error);
            if (string.Equals(update.Status, "success", StringComparison.OrdinalIgnoreCase)) createSuccess = true;
            await progress(update, ct);
        }
        if (!createSuccess) throw new InvalidDataException("OLLAMA_CREATE_STREAM_TRUNCATED_NO_SUCCESS");
        var ollamaDigest = RequireOllamaDigest(await GetLocalModelDigestAsync(job.ModelTag, ct));
        await WriteReceiptAsync(new ModelInstallReceipt("NOX_P03_INSTALL_RECEIPT_V1", job.Id,
            job.ModelTag, "gguf-import", DateTimeOffset.UtcNow, bytes, sha, ollamaDigest,
            job.LicenseSource, http.BaseAddress?.ToString() ?? "http://localhost:11434/"), ct);
        return (bytes, sha);
    }

    /// <summary>Import only P04's attested MERGED Safetensors snapshot through
    /// this existing Ollama HTTP client. Unsupported architectures remain HOLD.</summary>
    public async Task<string> ImportMergedSafetensorsAsync(ModelJob job,
        Func<OllamaStreamUpdate,CancellationToken,ValueTask> progress,CancellationToken ct)
    {
        EnsureLocalOllama();
        if(job.Kind!=ModelJobKind.SafetensorsImport || job.MergedImport is not { } approval ||
            job.LocalPath!=approval.Directory || job.ExpectedLocalSha256!=approval.MergedPayloadSha256 ||
            job.ModelTag!="nox-forge-"+approval.MergedPayloadSha256[..12]+":"+job.Id.ToString("N"))
            throw new SafetensorsImportHold("P03_MERGED_JOB_BINDING_INVALID");
        var files=await ModelSafetensorsImport.ValidateAsync(approval,ct);
        if(files.Sum(x=>x.SizeBytes)!=job.ExpectedLocalBytes)
            throw new SafetensorsImportHold("P03_MERGED_BYTES_MISMATCH");
        if(await GetLocalModelDigestAsync(job.ModelTag,ct) is not null)
            throw new SafetensorsImportHold("P03_CANDIDATE_TAG_ALREADY_EXISTS");
        var mappings=new Dictionary<string,string>(StringComparer.Ordinal);
        long uploadedBytes=0;var total=files.Sum(x=>x.SizeBytes);
        foreach(var item in files)
        {
            ct.ThrowIfCancellationRequested();var path=Path.Combine(approval.Directory,item.Path);
            ModelLocalAttestation.RequireRegularUnlinkedFile(path);
            await using var file=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read,1<<20,true);
            var hash=Convert.ToHexString(await SHA256.HashDataAsync(file,ct)).ToLowerInvariant();
            if(hash!=item.Sha256 || file.Length!=item.SizeBytes)
                throw new SafetensorsImportHold("P03_MERGED_FILE_CHANGED");
            file.Position=0;var digest="sha256:"+hash;
            using(var presence=await http.SendAsync(new HttpRequestMessage(HttpMethod.Head,"api/blobs/"+digest),ct))
            {
                if(presence.StatusCode==System.Net.HttpStatusCode.NotFound)
                {
                    using var body=new StreamContent(file);
                    using var upload=await http.PostAsync("api/blobs/"+digest,body,ct);
                    if(!upload.IsSuccessStatusCode)throw new SafetensorsImportHold("P03_SAFETENSORS_BLOB_UPLOAD_FAILED");
                }
                else presence.EnsureSuccessStatusCode();
            }
            using(var proof=await http.SendAsync(new HttpRequestMessage(HttpMethod.Head,"api/blobs/"+digest),ct))
                proof.EnsureSuccessStatusCode();
            mappings.Add(item.Path,digest);uploadedBytes=checked(uploadedBytes+item.SizeBytes);
            await progress(new OllamaStreamUpdate("copying layer",uploadedBytes,total,digest,null),ct);
        }
        // Verify every original byte/proof again before creating a model. The
        // previously selected tag is untouched, even if create later fails.
        await ModelSafetensorsImport.ValidateAsync(approval,ct);
        if(await GetLocalModelDigestAsync(job.ModelTag,ct) is not null)
            throw new SafetensorsImportHold("P03_CANDIDATE_TAG_ALREADY_EXISTS");
        using var create=await SendStreamingJsonAsync("api/create",new {model=job.ModelTag,files=mappings,stream=true},ct);
        if(!create.IsSuccessStatusCode)
            throw new SafetensorsImportHold("P03_SAFETENSORS_CREATE_HTTP_"+(int)create.StatusCode);
        var done=false;
        await foreach(var update in ReadEventsAsync(create,ct))
        {
            if(update.Error is not null)
                throw new SafetensorsImportHold(update.Error.Contains("architecture",StringComparison.OrdinalIgnoreCase)
                    && update.Error.Contains("support",StringComparison.OrdinalIgnoreCase)
                    ? "P03_SAFETENSORS_ARCHITECTURE_UNSUPPORTED" : "P03_SAFETENSORS_CREATE_REJECTED");
            if(update.Status.Equals("success",StringComparison.OrdinalIgnoreCase))done=true;
            await progress(update,ct);
        }
        if(!done)throw new SafetensorsImportHold("P03_SAFETENSORS_CREATE_TRUNCATED");
        ct.ThrowIfCancellationRequested();
        var installed=RequireOllamaDigest(await GetLocalModelDigestAsync(job.ModelTag,ct));
        await WriteReceiptAsync(new ModelInstallReceipt("NOX_P03_INSTALL_RECEIPT_V1",job.Id,
            job.ModelTag,"safetensors-import",DateTimeOffset.UtcNow,total,approval.MergedPayloadSha256,
            installed,job.LicenseSource,http.BaseAddress!.ToString(),approval.MergedPayloadSha256,
            approval.MergeReceiptSha256,approval.TrainingReceiptSha256,approval.RightsAttestationId,
            approval.RightsAttestationSha256,approval.NativeApprovalId,files),ct);
        return installed;
    }

    // C41 source semantics re-bound to C40. A success event is not install proof.
    private static string RequireOllamaDigest(string? digest)
    {
        if (digest is not { Length: 71 } || !digest.StartsWith("sha256:", StringComparison.OrdinalIgnoreCase)
            || !digest.AsSpan(7).ToArray().All(Uri.IsHexDigit))
            throw new InvalidDataException("OLLAMA_LOCAL_MANIFEST_DIGEST_MISSING_OR_INVALID");
        return digest.ToLowerInvariant();
    }

    private static async Task<bool> TryReadGgufHeaderAsync(Stream file, byte[] header, CancellationToken ct)
    {
        try { await file.ReadExactlyAsync(header, ct); return true; }
        catch (EndOfStreamException) { return false; }
    }

    private void EnsureLocalOllama()
    {
        var uri = http.BaseAddress ?? throw new InvalidOperationException("Local Ollama endpoint not configured.");
        var host = uri.Host;
        if (uri.Scheme != Uri.UriSchemeHttp ||
            !string.IsNullOrEmpty(uri.UserInfo) ||
            !(host.Equals("localhost", StringComparison.OrdinalIgnoreCase) ||
              (System.Net.IPAddress.TryParse(host, out var ip) && System.Net.IPAddress.IsLoopback(ip))))
            throw new InvalidOperationException("Only local Ollama loopback endpoints are allowed.");
    }

    private Task<string?> GetLocalModelDigestAsync(string model, CancellationToken ct) =>
        ModelLocalAttestation.ReadUnambiguousDigestAsync(http, model, ct);

    private async IAsyncEnumerable<OllamaStreamUpdate> ReadEventsAsync(HttpResponseMessage response,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken ct)
    {
        await using var stream = await response.Content.ReadAsStreamAsync(ct);
        using var reader = new StreamReader(stream, Encoding.UTF8);
        await foreach (var update in ModelLocalAttestation.ReadValidatedStreamAsync(reader, ct))
            yield return update;
    }

    private async Task<HttpResponseMessage> SendStreamingJsonAsync(string relativeUrl, object payload, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, relativeUrl)
        {
            Content = JsonContent.Create(payload, options: JsonOptions)
        };
        return await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
    }

    public string ReceiptPathFor(Guid id) => Path.Combine(receiptDirectory, $"{id:N}.json");

    private Task WriteReceiptAsync(ModelInstallReceipt receipt, CancellationToken ct) =>
        ModelLocalAttestation.WriteNewReceiptAsync(receiptDirectory, receipt, ct);
}