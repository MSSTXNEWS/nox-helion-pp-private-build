// Source gate only: real WPF/WebView2 native run remains required.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const bridge=fs.readFileSync('coordination/e06/OneHostP02WebView2Bridge.cs','utf8');
for (const [what,rx] of [
 ['single WebView2 owner',/CoreWebView2 existingCore/],
 ['native only method',/internal bool TryOpenReviewedExternal/],
 ['native return',/internal bool ReturnToReviewedShell/],
 ['native SID',/!NativeSidMatches\(\)/],
 ['native gesture',/!nativeGestureVerified/],
 ['detached IPC',/!ipcDetached/],
 ['removed objects',/!hostObjectsRemoved/],
 ['network isolation',/!networkIsolationAttested/],
 ['stop pending chat',/RevokeDocument\(\);\s*\/\/ Cancel stale model/],
 ['exact host',/string.Equals\(target.IdnHost, entry/],
 ['HTTPS only',/target.Scheme == Uri.UriSchemeHttps/],
 ['deny IP',/IPAddress.TryParse\(host, out _\)/],
 ['redirect guard',/if \(!IsApprovedExternal\(e.Uri\)\) e.Cancel = true;/],
 ['reject native messages',/_externalMode \|\|\s*!Trusted\(e.Source\)/],
 ['no native reply',/Volatile.Read\(ref _disposed\) == 0 && !_externalMode/],
 ['native shell recovery',/if \(_nativeReturnPending && Trusted\(_web.Source\)\)/],
]) test(what,()=>assert.match(bridge,rx));
