// EV-B06 same WebView2 bridge source invariants; runtime E07 remains required.
const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const s=fs.readFileSync('stage/proposals/P01/C09/Bridge/P01WebView2NavigationBridge.cs','utf8');
for (const [name,re] of [
 ['native-only open',/internal bool TryOpenReviewedExternal\(/],
 ['native-only return',/internal bool ReturnToTrustedShell\(/],
 ['fresh gesture',/!verifiedNativeGesture/],
 ['IPC detached',/!nativeIpcDetached/],
 ['host objects removed',/!hostObjectsRemoved/],
 ['network isolation attested',/!networkIsolationAttested/],
 ['deny non-HTTPS',/Uri\.UriSchemeHttps/],
 ['deny IP literal',/IPAddress\.TryParse\(host, out _\)/],
 ['deny private/special DNS',/\.localhost.*\.local.*\.internal.*\.invalid/s],
 ['exact host equality',/string\.Equals\(candidate, host, StringComparison\.OrdinalIgnoreCase\)/],
 ['redirect check',/if \(!IsCurrentReviewedExternalUrl\(args.Uri\)\) args.Cancel = true;/],
 ['native IPC withheld on external documents',/_externalNavigationActive \|\| !IsTrustedSource\(args.Source\)/],
 ['native ACK withheld while external',/_externalNavigationActive \|\| _lifetime.IsCancellationRequested/],
 ['restored only after trusted ContentLoading',/if \(_returnToShellPending && IsTrustedSource\(_webView.Source\)\)/],
 ['single existing WebView2',/_webView.Navigate\(target.AbsoluteUri\)/],
 ['no unrestricted popup',/args.Handled = true;/]
]) test(name,()=>assert.match(s,re));
