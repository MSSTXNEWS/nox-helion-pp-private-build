// NOX V16 P02 — policy only; existing WebView2 is owned/wired by Integrator #6.
// No second browser engine. No permission can be granted by external page content.
using System;
using System.Collections.Generic;
using System.Net;

namespace NoxHelion.P02;

public enum SpaceOriginClass { TrustedShell, ExternalWeb, Blocked }

public sealed class SpaceBrowserBoundary
{
    // Reserved invalid TLD: the integrator must map this origin to packaged, pinned UI bytes.
    // Failure to configure WebView2 virtual host mapping means trusted shell is not available.
    public static readonly Uri ShellOrigin = new("https://nox.invalid/");
    private static readonly HashSet<string> Operations = new(StringComparer.Ordinal)
    {
        "chat.send", "chat.stop", "model.select", "attachment.pick",
        "attachment.read", "history.list", "history.delete"
    };

    public static SpaceOriginClass Classify(Uri? url)
    {
        if(url is null || !url.IsAbsoluteUri || !string.IsNullOrEmpty(url.UserInfo))
            return SpaceOriginClass.Blocked;
        if(url.Scheme.Equals(Uri.UriSchemeHttps,StringComparison.OrdinalIgnoreCase) &&
            url.Host.Equals(ShellOrigin.Host,StringComparison.OrdinalIgnoreCase) &&
            url.IsDefaultPort) return SpaceOriginClass.TrustedShell;
        // External web/media is navigable in the EXISTING engine, not a native capability.
        if(url.Scheme.Equals(Uri.UriSchemeHttps,StringComparison.OrdinalIgnoreCase) &&
            !url.Host.Equals(ShellOrigin.Host,StringComparison.OrdinalIgnoreCase))
            return SpaceOriginClass.ExternalWeb;
        return SpaceOriginClass.Blocked; // file:, data:, javascript:, http:, custom schemes
    }

    /// <summary>Call from the native WebMessageReceived handler, using the WebView2
    /// supplied document/frame source, not a JSON-provided origin. The native host must
    /// additionally validate payload, principal/ACL, user gesture and state transition.</summary>
    public static bool MayInvokeNative(string operation,Uri? webViewReportedSource,
        bool isMainFrame,bool hostHasVerifiedUserConsent)
    {
        if(!isMainFrame || Classify(webViewReportedSource)!=SpaceOriginClass.TrustedShell)
            return false;
        if(!Operations.Contains(operation)) return false;
        if(operation is "history.delete" or "attachment.pick")
            return hostHasVerifiedUserConsent;
        return true;
    }

    /// <summary>External websites must not inherit host objects, script-to-native
    /// mappings, custom privileges, cookies, app-storage IDs or the chat principal.
    /// Host #6 must explicitly disable privileges for all external navigations/iframes.</summary>
    public static bool MayExposeHostObjects(Uri? documentSource) => false;

    /// <summary>
    /// Native-owner reviewed navigation policy for the ONE existing WebView2.
    /// The caller must first detach every host object and native IPC bridge,
    /// attest an isolated network boundary, and verify a fresh native gesture.
    /// It must reapply this policy on EVERY redirect. This method never opens
    /// a browser, mints consent, or trusts DOM-supplied allowlists.
    /// </summary>
    public static bool MayNavigateReviewedExternal(
        Uri? target, IReadOnlyCollection<string>? nativeApprovedHttpsHosts,
        bool freshNativeGesture, bool ipcDetached, bool hostObjectsRemoved,
        bool networkIsolationAttested)
    {
        if (!freshNativeGesture || !ipcDetached || !hostObjectsRemoved ||
            !networkIsolationAttested || target is null ||
            !target.IsAbsoluteUri || !target.IsDefaultPort ||
            !string.IsNullOrEmpty(target.UserInfo) ||
            !string.Equals(target.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase) ||
            Classify(target) != SpaceOriginClass.ExternalWeb ||
            nativeApprovedHttpsHosts is null || nativeApprovedHttpsHosts.Count == 0)
            return false;

        var host = target.IdnHost;
        if (!IsReviewedPublicDnsHost(host)) return false;
        foreach (var approved in nativeApprovedHttpsHosts)
        {
            if (IsReviewedPublicDnsHost(approved) &&
                string.Equals(host, approved, StringComparison.OrdinalIgnoreCase))
                return true;
        }
        return false;
    }

    private static bool IsReviewedPublicDnsHost(string? host)
    {
        if (string.IsNullOrWhiteSpace(host) || host.Length > 253 ||
            host.StartsWith(".", StringComparison.Ordinal) ||
            host.EndsWith(".", StringComparison.Ordinal) ||
            host.Contains("..", StringComparison.Ordinal) ||
            host.IndexOf('.') < 1 || IPAddress.TryParse(host, out _))
            return false;
        if (Uri.CheckHostName(host) != UriHostNameType.Dns) return false;
        string[] reserved = { ".localhost", ".local", ".internal", ".invalid",
            ".test", ".example", ".onion", ".arpa", ".lan", ".home" };
        foreach (var suffix in reserved)
            if (host.EndsWith(suffix, StringComparison.OrdinalIgnoreCase))
                return false;
        return true;
    }

    public static bool CanRenderInline(string mime) => mime switch
    {
        "image/png" or "image/jpeg" or "video/mp4" or "audio/mpeg" or "audio/wav" => true,
        _ => false // HTML, PDF active payloads, SVG, scripts go to safe external handler
    };
}
