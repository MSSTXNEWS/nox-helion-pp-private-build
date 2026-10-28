using System.Net;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Nox.P03;

/// <summary>
/// One extension of the existing P03 Model Center / host queue for media weight packages.
/// Not exposed to WebView2 and never starts automatically. The host owns authentication,
/// user consent, disk quota, cancellation, manifest approvals and all progress publication.
/// </summary>
public sealed record MediaWeightFile(string RelativePath, long Bytes, string Sha256);
public sealed record MediaWeightPackage(string ModelId, string VariantId,
    string HuggingFaceRepo, string ImmutableRevision, string LicenseEvidenceUrl,
    IReadOnlyList<MediaWeightFile> Files, bool RightsReviewed)
{
    private static readonly Regex Id = new("^[a-z0-9][a-z0-9-]{2,64}$", RegexOptions.Compiled);
    private static readonly Regex Repo = new("^[A-Za-z0-9._-]{1,100}/[A-Za-z0-9._-]{1,100}$", RegexOptions.Compiled);
    private static readonly Regex Commit = new("^[a-fA-F0-9]{40}$", RegexOptions.Compiled);
    private static readonly Regex Sha = new("^[a-fA-F0-9]{64}$", RegexOptions.Compiled);
    public static bool SafeRelativePath(string? path) =>
        !string.IsNullOrEmpty(path) && path.Length <= 240 &&
        path.IndexOfAny(['\\', ':', '?', '#', '%', '\0']) < 0 &&
        path.Split('/').All(s => s.Length is >= 1 and <= 100 &&
            s != "." && s != ".." && s.All(c => char.IsAsciiLetterOrDigit(c) ||
            c is '-' or '_' or '.'));
    public bool IsApproved()
    {
        if (!RightsReviewed || !Id.IsMatch(ModelId ?? "") || !Id.IsMatch(VariantId ?? "") ||
            !Repo.IsMatch(HuggingFaceRepo ?? "") || !Commit.IsMatch(ImmutableRevision ?? "") ||
            !Uri.TryCreate(LicenseEvidenceUrl, UriKind.Absolute, out var license) ||
            license.Scheme != "https" || !string.IsNullOrEmpty(license.UserInfo) ||
            Files is null || Files.Count is < 1 or > 128) return false;
        long total = 0;
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var f in Files)
        {
            if (!SafeRelativePath(f.RelativePath) || !Sha.IsMatch(f.Sha256 ?? "") ||
                f.Bytes is < 1 or > 80L * 1024 * 1024 * 1024 ||
                !seen.Add(f.RelativePath)) return false;
            try { total = checked(total + f.Bytes); }
            catch (OverflowException) { return false; }
        }
        return total is > 0 and <= 120L * 1024 * 1024 * 1024;
    }
    public long TotalBytes => Files.Sum(f => f.Bytes);
}
public static class MediaWeightCommandContract
{
    public sealed record Command(string CommandId, string Action, string ModelId,
        string VariantId, Guid? JobId);
    public static bool TryParse(string? payload,
        IReadOnlyDictionary<string, MediaWeightPackage> approvedByVariant,
        bool canDownload, bool canCancel, out Command? command)
    {
        command = null;
        if (string.IsNullOrWhiteSpace(payload) || payload.Length > 1536 ||
            approvedByVariant is null) return false;
        try
        {
            using var doc = JsonDocument.Parse(payload);
            var root = doc.RootElement;
            if (root.ValueKind != JsonValueKind.Object ||
                !root.TryGetProperty("type", out var type) || type.GetString() != "p03.media.command.v1" ||
                !root.TryGetProperty("commandId", out var cid) || cid.ValueKind != JsonValueKind.String ||
                !root.TryGetProperty("modelId", out var mid) || mid.ValueKind != JsonValueKind.String ||
                !root.TryGetProperty("variantId", out var vid) || vid.ValueKind != JsonValueKind.String ||
                !root.TryGetProperty("action", out var action) || action.ValueKind != JsonValueKind.String)
                return false;
            var id = cid.GetString() ?? "";
            var modelId = mid.GetString() ?? "";
            var variantId = vid.GetString() ?? "";
            if (!Regex.IsMatch(id, "^[A-Za-z0-9_-]{3,64}$") ||
                !Regex.IsMatch(modelId, "^[a-z0-9][a-z0-9-]{2,64}$") ||
                !Regex.IsMatch(variantId, "^[a-z0-9][a-z0-9-]{2,64}$")) return false;
            if (action.GetString() == "download" && canDownload)
            {
                if (!root.TryGetProperty("licenseAcknowledged", out var ack) ||
                    ack.ValueKind != JsonValueKind.True) return false;
                if (!approvedByVariant.TryGetValue(variantId, out var pkg) ||
                    pkg.ModelId != modelId || !pkg.IsApproved()) return false;
                command = new(id, "download", modelId, variantId, null);
                return true;
            }
            if (action.GetString() == "cancel" && canCancel &&
                root.TryGetProperty("jobId", out var job) && job.ValueKind == JsonValueKind.String &&
                Guid.TryParse(job.GetString(), out var guid) && guid != Guid.Empty)
            {
                // Host must validate that job belongs to this model/variant AND current user.
                command = new(id, "cancel", modelId, variantId, guid);
                return true;
            }
            return false;
        }
        catch (JsonException) { return false; }
        catch (InvalidOperationException) { return false; }
    }
}
public sealed record MediaWeightProgress(string ModelId, string VariantId, long CompletedBytes,
    long TotalBytes, string Phase);
public sealed record MediaWeightReceipt(string ModelId, string VariantId, string Revision,
    long TotalBytes, IReadOnlyDictionary<string, string> FileSha256, string Status);

/// <summary>
/// Transfers every pinned file from the immutable Hugging Face revision.
/// No arbitrary URL input, no full repo sweep, no external manifest overrides.
/// To be called by the existing E06-owned queue scheduler only; no second daemon.
/// </summary>
public sealed class MediaWeightTransfer
{
    private readonly HttpClient _http;
    public MediaWeightTransfer(HttpClient? http = null)
    {
        if (http is not null) { _http = http; return; }
        // No automatic redirects, no bearer/auth credentials. Explicit host allowlist below.
        _http = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false,
            AutomaticDecompression = DecompressionMethods.None });
        _http.Timeout = TimeSpan.FromHours(4);
    }
    private static readonly HashSet<string> AllowedHosts = new(StringComparer.OrdinalIgnoreCase)
    {
        "huggingface.co", "cdn-lfs.huggingface.co", "cas-bridge.xethub.hf.co",
        "transfer.xethub.hf.co", "cas-server.xethub.hf.co"
    };
    public static bool IsApprovedSource(Uri u) => u.Scheme == Uri.UriSchemeHttps &&
        AllowedHosts.Contains(u.IdnHost) && string.IsNullOrEmpty(u.UserInfo) && u.Port == 443;
    public async Task<MediaWeightReceipt> DownloadAsync(MediaWeightPackage p, string privateRoot,
        IProgress<MediaWeightProgress>? progress, CancellationToken ct)
    {
        if (!p.IsApproved()) throw new InvalidDataException("PINNED_MEDIA_PACKAGE_REQUIRED");
        if (string.IsNullOrWhiteSpace(privateRoot)) throw new ArgumentException("PRIVATE_ROOT_REQUIRED");
        ModelLocalAttestation.RequirePrivateUnlinkedDirectory(privateRoot);
        var path = Path.Combine(Path.GetFullPath(privateRoot), p.ModelId, p.VariantId);
        ModelLocalAttestation.RequirePrivateUnlinkedDirectory(path);
        var disk = new DriveInfo(Path.GetPathRoot(path)!);
        if (disk.AvailableFreeSpace < p.TotalBytes + 1024 * 1024)
            throw new IOException("INSUFFICIENT_DISK_FOR_MEDIA_WEIGHTS");
        long complete = 0;
        var hashes = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (var f in p.Files)
        {
            ct.ThrowIfCancellationRequested();
            var dest = Path.Combine(path, f.RelativePath.Replace('/', Path.DirectorySeparatorChar));
            var parent = Path.GetDirectoryName(dest)!;
            ModelLocalAttestation.RequirePrivateUnlinkedDirectory(parent);
            ModelLocalAttestation.RequireNoExistingReparsePoint(dest);
            if (File.Exists(dest))
            {
                var info = new FileInfo(dest);
                await using var existingStream = File.OpenRead(dest);
                if (info.Length != f.Bytes || !string.Equals(
                    Convert.ToHexString(await SHA256.HashDataAsync(existingStream, ct)),
                    f.Sha256, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("EXISTING_WEIGHT_FILE_HASH_CONFLICT");
                complete += f.Bytes;
                hashes[f.RelativePath] = f.Sha256.ToLowerInvariant();
                progress?.Report(new(p.ModelId, p.VariantId, complete, p.TotalBytes, "Already verified"));
                continue;
            }
            var temp = dest + ".download-part";
            ModelLocalAttestation.RequireNoExistingReparsePoint(temp);
            if (File.Exists(temp)) throw new InvalidDataException("UNVERIFIED_PARTIAL_FILE_EXISTS");
            try
            {
                var url = new Uri("https://huggingface.co/" + p.HuggingFaceRepo + "/resolve/" +
                    p.ImmutableRevision + "/" + f.RelativePath);
                using var response = await GetAllowedResponseAsync(url, ct);
                using var input = await response.Content.ReadAsStreamAsync(ct);
                await using var output = new FileStream(temp, FileMode.CreateNew, FileAccess.Write,
                    FileShare.None, 128 * 1024, FileOptions.Asynchronous | FileOptions.WriteThrough);
                using var digest = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
                var buffer = ArrayPool<byte>.Shared.Rent(128 * 1024);
                long local = 0;
                try
                {
                    int count;
                    while ((count = await input.ReadAsync(buffer.AsMemory(0, buffer.Length), ct)) > 0)
                    {
                        local = checked(local + count);
                        if (local > f.Bytes) throw new InvalidDataException("WEIGHT_SIZE_EXCEEDS_PIN");
                        await output.WriteAsync(buffer.AsMemory(0, count), ct);
                        digest.AppendData(buffer, 0, count);
                        progress?.Report(new(p.ModelId, p.VariantId, complete + local,
                            p.TotalBytes, "Downloading"));
                    }
                }
                finally { ArrayPool<byte>.Shared.Return(buffer); }
                await output.FlushAsync(ct);
                if (local != f.Bytes || !string.Equals(Convert.ToHexString(
                    digest.GetHashAndReset()), f.Sha256, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("DOWNLOADED_WEIGHT_HASH_MISMATCH");
                // Close file handle before atomic rename.
                await output.DisposeAsync();
                ModelLocalAttestation.RequireNoExistingReparsePoint(dest);
                File.Move(temp, dest, overwrite: false);
                complete += local;
                hashes[f.RelativePath] = f.Sha256.ToLowerInvariant();
            }
            finally { if (File.Exists(temp)) File.Delete(temp); }
        }
        // Receipt is generated ONLY after verifying every member; not from HTTP success.
        return new(p.ModelId, p.VariantId, p.ImmutableRevision, complete,
            hashes, "INSTALLED_VERIFIED");
    }
    private async Task<HttpResponseMessage> GetAllowedResponseAsync(Uri url, CancellationToken ct)
    {
        for (int redirects = 0; redirects <= 5; redirects++)
        {
            if (!IsApprovedSource(url)) throw new HttpRequestException("MODEL_REDIRECT_HOST_DENIED");
            using var req = new HttpRequestMessage(HttpMethod.Get, url);
            var response = await _http.SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct);
            if ((int)response.StatusCode is 301 or 302 or 303 or 307 or 308)
            {
                var location = response.Headers.Location;
                response.Dispose();
                if (location is null || !location.IsAbsoluteUri)
                    throw new HttpRequestException("WEIGHT_REDIRECT_ABSOLUTE_REQUIRED");
                url = location;
                continue;
            }
            if (!response.IsSuccessStatusCode)
            {
                var status = response.StatusCode;
                response.Dispose();
                throw new HttpRequestException("MEDIA_DOWNLOAD_HTTP_" + (int)status);
            }
            return response;
        }
        throw new HttpRequestException("MEDIA_DOWNLOAD_REDIRECT_LIMIT");
    }
}
