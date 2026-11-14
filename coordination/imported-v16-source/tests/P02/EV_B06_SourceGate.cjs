// B06 security source gate for the existing P02 browser boundary.
// Node: node --test tests/P02/EV_B06_SourceGate.cjs
// SOURCE ONLY, NOT a WebView2/Windows native integration test.
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const source=fs.readFileSync('Packages/P02/worker-chat/SpaceBrowserBoundary.cs','utf8');
for(const [name,pattern] of [
  ['native gesture', /!freshNativeGesture/],
  ['native IPC detached', /!ipcDetached/],
  ['host objects removed', /!hostObjectsRemoved/],
  ['network isolation attested', /!networkIsolationAttested/],
  ['HTTPS only', /Uri\.UriSchemeHttps/],
  ['no credentials', /!string\.IsNullOrEmpty\(target\.UserInfo\)/],
  ['deny nondefault port', /!target\.IsDefaultPort/],
  ['literal exact-host compare', /string\.Equals\(host, approved, StringComparison\.OrdinalIgnoreCase\)/],
  ['IP literals denied', /IPAddress\.TryParse\(host, out _\)/],
  ['DNS only', /Uri\.CheckHostName\(host\) != UriHostNameType\.Dns/],
  ['special-use hosts denied', /"\.localhost".*"\.local".*"\.internal".*"\.invalid"/s],
  ['native actions tied to shell', /Classify\(webViewReportedSource\)!=SpaceOriginClass\.TrustedShell/],
  ['external host objects always denied', /MayExposeHostObjects\(Uri\? documentSource\) => false/],
]) test(name,()=>assert.match(source,pattern));
