// NOX V16 P02 — policy only; existing WebView2 is owned/wired by Integrator #6.
// No second browser engine. No permission can be granted by external page content.
using System;
using System.Collections.Generic;

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

    public static bool CanRenderInline(string mime) => mime switch
    {
        "image/png" or "image/jpeg" or "video/mp4" or "audio/mpeg" or "audio/wav" => true,
        _ => false // HTML, PDF active payloads, SVG, scripts go to safe external handler
    };
}
