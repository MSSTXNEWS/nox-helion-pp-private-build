param([Parameter(Mandatory=$true)][string]$Source)
$ErrorActionPreference='Stop'
$s=[IO.File]::ReadAllText($Source)
$pre='    private bool uiSmokeFinished;'
if (!$s.Contains($pre) -or $s.Contains('pendingEmbeddedNavigation')) { throw 'NOX_NAV_PATCH_PREIMAGE_MISMATCH' }
$s=$s.Replace($pre,$pre + [Environment]::NewLine + '    private bool pendingEmbeddedNavigation;')
$old=@'
            Browser.CoreWebView2.NavigationStarting += (_, args) =>
            {
                if (!string.Equals(args.Uri, "about:blank", StringComparison.OrdinalIgnoreCase))
                    args.Cancel = true;
            };
            TraceUiSmokeStage("NAVIGATE_TO_STRING_PENDING");
            Browser.NavigateToString(await reader.ReadToEndAsync());
'@
$new=@'
            Browser.CoreWebView2.NavigationStarting += (_, args) =>
            {
                // Permit exactly one trusted application-initiated NavigateToString
                // transition, regardless of the internal URI scheme of WebView2.
                // Subsequent external navigations stay blocked.
                if (pendingEmbeddedNavigation)
                {
                    pendingEmbeddedNavigation = false;
                    TraceUiSmokeStage("EMBEDDED_NAVIGATION_START_" +
                        (Uri.TryCreate(args.Uri, UriKind.Absolute, out var u) ? u.Scheme : "unknown"));
                    return;
                }
                if (!string.Equals(args.Uri, "about:blank", StringComparison.OrdinalIgnoreCase))
                    args.Cancel = true;
            };
            pendingEmbeddedNavigation = true;
            TraceUiSmokeStage("NAVIGATE_TO_STRING_PENDING");
            Browser.NavigateToString(await reader.ReadToEndAsync());
'@
if (!$s.Contains($old)) { throw 'NOX_NAV_PATCH_ANCHOR_NOT_FOUND' }
$s=$s.Replace($old,$new)
$from='TraceUiSmokeStage(args.IsSuccess ? "NAVIGATION_COMPLETED" : "NAVIGATION_FAILED");'
$to='TraceUiSmokeStage(args.IsSuccess ? "NAVIGATION_COMPLETED" : "NAVIGATION_FAILED_" + args.WebErrorStatus);'
if (!$s.Contains($from)) { throw 'NOX_NAV_STATUS_ANCHOR_MISSING' }
$s=$s.Replace($from,$to)
[IO.File]::WriteAllText($Source,$s,[Text.UTF8Encoding]::new($false))
Write-Host "NOX_NAV_PATCH_APPLIED"
