param([Parameter(Mandatory=$true)][string]$Source)
$ErrorActionPreference='Stop'
$s=[IO.File]::ReadAllText($Source)
$pre='    private bool uiSmokeFinished;'
if (!$s.Contains($pre) -or $s.Contains('pendingEmbeddedNavigation')) { throw 'NOX_NAV_PATCH_PREIMAGE_MISMATCH' }
$s=$s.Replace($pre,$pre + [Environment]::NewLine + '    private bool pendingEmbeddedNavigation;')
$start = $s.IndexOf('            Browser.CoreWebView2.NavigationStarting += (_, args) =>', [StringComparison]::Ordinal)
$tail = '            Browser.NavigateToString(await reader.ReadToEndAsync());'
$end = $s.IndexOf($tail, $start, [StringComparison]::Ordinal)
if ($start -lt 0 -or $end -le $start -or
    $s.LastIndexOf('            Browser.CoreWebView2.NavigationStarting += (_, args) =>', [StringComparison]::Ordinal) -ne $start) {
  throw 'NOX_NAV_PATCH_ANCHOR_NOT_FOUND'
}
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
$s=$s.Substring(0,$start)+$new+$s.Substring($end+$tail.Length)
$from='TraceUiSmokeStage(args.IsSuccess ? "NAVIGATION_COMPLETED" : "NAVIGATION_FAILED");'
$to='TraceUiSmokeStage(args.IsSuccess ? "NAVIGATION_COMPLETED" : "NAVIGATION_FAILED_" + args.WebErrorStatus);'
if (!$s.Contains($from)) { throw 'NOX_NAV_STATUS_ANCHOR_MISSING' }
$s=$s.Replace($from,$to)

$complete = '            lastGenerationCompleted = true;'
$persist = '            if (answer.Length > 0) PersistChat(prompt, answer.ToString());'
$begin = $s.IndexOf($complete, [StringComparison]::Ordinal)
$saveAt = $s.IndexOf($persist, $begin, [StringComparison]::Ordinal)
if ($begin -lt 0 -or $saveAt -le $begin -or $saveAt-$begin -gt 100) { throw 'NOX_STOP_COMMIT_ORDER_PREIMAGE_HOLD' }
$fix = @'
            // STOP received with the final token still prevents persistence.
            cancellation.Token.ThrowIfCancellationRequested();
            if (answer.Length > 0) PersistChat(prompt, answer.ToString());
            // Completion becomes true only after SQLite commit.
            lastGenerationCompleted = true;
'@
$s=$s.Substring(0,$begin)+$fix+$s.Substring($saveAt+$persist.Length)

[IO.File]::WriteAllText($Source,$s,[Text.UTF8Encoding]::new($false))
Write-Host "NOX_NAV_PATCH_APPLIED"
