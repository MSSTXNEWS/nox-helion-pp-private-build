using System.Net;

namespace Nox.P03;

/// <summary>
/// The existing NOX host must use this factory for its one Ollama HTTP adapter.
/// It never creates a second downloader, model registry, or application process.
/// </summary>
public static class OllamaLoopbackHttpClientFactory
{
    public static HttpClient Create(Uri endpoint)
    {
        ArgumentNullException.ThrowIfNull(endpoint);
        var canonical = ValidateAndCanonicalize(endpoint);
        // Default HttpClientHandler follows redirects and respects HTTP proxy
        // variables; both would allow an untrusted localhost HTTP peer to
        // redirect GGUF bytes or model requests beyond the user's computer.
        var handler = new SocketsHttpHandler
        {
            AllowAutoRedirect = false,
            UseProxy = false,
            UseCookies = false,
            ConnectTimeout = TimeSpan.FromSeconds(10),
            PooledConnectionLifetime = TimeSpan.FromMinutes(5)
        };
        return new HttpClient(handler, disposeHandler: true)
        {
            BaseAddress = canonical,
            Timeout = TimeSpan.FromMinutes(30)
        };
    }

    public static Uri ValidateAndCanonicalize(Uri endpoint)
    {
        if (!endpoint.IsAbsoluteUri || endpoint.Scheme != Uri.UriSchemeHttp ||
            !string.IsNullOrEmpty(endpoint.UserInfo) ||
            endpoint.AbsolutePath != "/" ||
            !string.IsNullOrEmpty(endpoint.Query) ||
            !string.IsNullOrEmpty(endpoint.Fragment))
            throw new InvalidOperationException("OLLAMA_ENDPOINT_MUST_BE_LOCAL_HTTP_ROOT");
        if (endpoint.Host.Equals("localhost", StringComparison.OrdinalIgnoreCase))
            return new UriBuilder(endpoint) { Host = IPAddress.Loopback.ToString() }.Uri;
        if (!IPAddress.TryParse(endpoint.Host, out var address) || !IPAddress.IsLoopback(address))
            throw new InvalidOperationException("OLLAMA_ENDPOINT_NOT_LOOPBACK");
        return endpoint;
    }
}
