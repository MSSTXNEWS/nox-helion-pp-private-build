using System.Globalization;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Nox.P01.AutoUpdate;

/// <summary>
/// Read-only startup + periodic EXE update discovery. No installer is downloaded or started.
/// E06 owns the single Windows host and must supply a signed-feed URL and pinned public key.
/// </summary>
public sealed record UpdateConfiguration(
    Uri? FeedUri, string? PinnedP256PublicKeyPem,
    string CurrentVersion, string Channel = "stable", TimeSpan? Interval = null)
{
    public TimeSpan SafeInterval => Interval is { } x &&
        x >= TimeSpan.FromMinutes(15) && x <= TimeSpan.FromDays(7)
        ? x : TimeSpan.FromHours(6);
}
public sealed record VerifiedUpdate(string Status, string? Version, string? BuildId,
    Uri? InstallerUrl, string? Sha256, long? Bytes, string? Reason, DateTimeOffset CheckedAt)
{
    public bool HasUpdate => Status == "UPDATE_AVAILABLE_VERIFIED";
}
public sealed record SignedReleaseManifest(
    string Schema, string Channel, string Version, string BuildId,
    string InstallerUrl, string Sha256, long Bytes, string PublishedUtc,
    string ExpiresUtc, string Signature)
{
    public byte[] SignedBytes => Encoding.UTF8.GetBytes(string.Join("\n", [
        Schema, Channel, Version, BuildId, InstallerUrl, Sha256.ToLowerInvariant(),
        Bytes.ToString(CultureInfo.InvariantCulture), PublishedUtc, ExpiresUtc
    ]) + "\n");
}
public sealed class NoxUpdateDiscovery(HttpClient http)
{
    private static readonly Regex Hash = new("^[a-f0-9]{64}$", RegexOptions.IgnoreCase | RegexOptions.Compiled);
    private static readonly Regex Id = new("^[a-zA-Z0-9][a-zA-Z0-9._-]{2,127}$", RegexOptions.Compiled);
    public async Task<VerifiedUpdate> CheckAsync(UpdateConfiguration cfg, CancellationToken ct = default)
    {
        var now = DateTimeOffset.UtcNow;
        VerifiedUpdate Hold(string reason) => new("HOLD", null, null, null, null, null, reason, now);
        if (cfg.FeedUri is null || string.IsNullOrWhiteSpace(cfg.PinnedP256PublicKeyPem))
            return Hold("NO_SIGNED_FEED_CONFIGURED");
        if (cfg.FeedUri.Scheme != Uri.UriSchemeHttps ||
            cfg.FeedUri.UserInfo.Length > 0 || !string.IsNullOrEmpty(cfg.FeedUri.Fragment))
            return Hold("UNSAFE_FEED_URL");
        if (!Version.TryParse(cfg.CurrentVersion, out var current))
            return Hold("CURRENT_VERSION_INVALID");
        SignedReleaseManifest? m;
        try
        {
            using var request = new HttpRequestMessage(HttpMethod.Get, cfg.FeedUri);
            using var response = await http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
            if (!response.IsSuccessStatusCode)
                return Hold("FEED_HTTP_" + (int)response.StatusCode);
            if (response.RequestMessage?.RequestUri != cfg.FeedUri)
                return Hold("FEED_REDIRECT_DENIED");
            if (response.Content.Headers.ContentLength is > 65536)
                return Hold("FEED_TOO_LARGE");
            await using var stream = await response.Content.ReadAsStreamAsync(ct);
            var buffer = new byte[65537];
            var total = 0;
            while (total < buffer.Length)
            {
                var n = await stream.ReadAsync(buffer.AsMemory(total), ct);
                if (n == 0) break;
                total += n;
            }
            if (total > 65536) return Hold("FEED_TOO_LARGE");
            m = JsonSerializer.Deserialize<SignedReleaseManifest>(buffer.AsSpan(0, total),
                new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
        }
        catch (OperationCanceledException) when (ct.IsCancellationRequested) { throw; }
        catch (Exception ex) when (ex is HttpRequestException or IOException or JsonException or
                                   TimeoutException or TaskCanceledException)
        { return Hold("FEED_UNAVAILABLE"); }
        if (m is null || m.Schema != "NOX_SIGNED_RELEASE_V1" ||
            m.Channel != cfg.Channel || !Id.IsMatch(m.BuildId ?? "") ||
            !Hash.IsMatch(m.Sha256 ?? "") || m.Bytes is < 1 or > 8L * 1024 * 1024 * 1024 ||
            !Version.TryParse(m.Version, out var next) ||
            !DateTimeOffset.TryParse(m.PublishedUtc, CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal, out var pub) ||
            !DateTimeOffset.TryParse(m.ExpiresUtc, CultureInfo.InvariantCulture,
                DateTimeStyles.AssumeUniversal, out var exp) ||
            pub > now.AddMinutes(5) || exp < now || exp > now.AddDays(120))
            return Hold("INVALID_MANIFEST_FIELDS");
        if (!Uri.TryCreate(m.InstallerUrl, UriKind.Absolute, out var installer) ||
            installer.Scheme != Uri.UriSchemeHttps || installer.UserInfo.Length != 0 ||
            !string.IsNullOrEmpty(installer.Fragment) ||
            installer.Host != cfg.FeedUri.Host || !installer.AbsolutePath.EndsWith(".exe", StringComparison.OrdinalIgnoreCase))
            return Hold("UNSAFE_INSTALLER_URL");
        bool signatureValid;
        try
        {
            using var key = ECDsa.Create();
            key.ImportFromPem(cfg.PinnedP256PublicKeyPem);
            signatureValid = key.KeySize == 256 &&
                key.VerifyData(m.SignedBytes, Convert.FromBase64String(m.Signature),
                    HashAlgorithmName.SHA256);
        }
        catch (Exception ex) when (ex is FormatException or CryptographicException or ArgumentException)
        { signatureValid = false; }
        if (!signatureValid) return Hold("INVALID_SIGNATURE");
        if (next <= current)
            return new("UP_TO_DATE", m.Version, m.BuildId, null, null, null, null, now);
        return new("UPDATE_AVAILABLE_VERIFIED", m.Version, m.BuildId, installer,
            m.Sha256.ToLowerInvariant(), m.Bytes, null, now);
    }

    /// <summary>
    /// Call once from the approved existing native EXE startup. Searches immediately,
    /// then periodically. It NEVER downloads/installs/restarts and never edits user data.
    /// </summary>
    public async Task RunSearchLoopAsync(UpdateConfiguration cfg,
        Func<VerifiedUpdate, Task> publish, CancellationToken ct)
    {
        ArgumentNullException.ThrowIfNull(publish);
        await publish(await CheckAsync(cfg, ct));
        using var timer = new PeriodicTimer(cfg.SafeInterval);
        while (await timer.WaitForNextTickAsync(ct))
            await publish(await CheckAsync(cfg, ct));
    }
}
